"""Triage: what does each failing test mean? Deterministic code, not the model.

The last good release is the oracle. For each test that fails on the release:
  1. run it on the baseline:  fails there too       -> broken_test (the test is wrong: heal it, max 3 tries)
  2. rerun it on the release: passes now            -> flaky       (recorded, not reported)
  3. passes on baseline, fails on release 2/2 runs  -> real_bug    (if it matches a snapshot diff or a journey)
                                                    -> unconfirmed (no supporting evidence: human review)
Ported from the original PortalGuard. State is plain dicts so the LangGraph checkpointer can store it.
"""

import ast
import hashlib
import re
from typing import Callable

from portalguard.config import JOURNEYS, MAX_HEAL_ATTEMPTS

FLAKY_RERUNS = 1
DECIDED = ("real_bug", "flaky", "unconfirmed")
LOCATOR_NAME = re.compile(r'name=\\?"([^"\\]+)')
QUOTED = re.compile(r'"([^"\n]{3,})"|\'([^\'\n]{3,})\'')
FAILING_LINE = re.compile(r"^line (\d+):")

# (base_url, filename, test_name) -> one result {"outcome", "message"}
RunOne = Callable[[str, str, str], dict]


def split_test_id(test_id: str) -> tuple[str, str]:
    """'test_x.py::test_y[chromium]' -> ('test_x.py', 'test_y')"""
    filename, name = test_id.split("::", 1)
    return filename, name.split("[", 1)[0]


def functions(code: str) -> dict[str, str]:
    """Top-level test functions -> normalized AST (ignores comments and formatting)."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {}
    return {n.name: ast.dump(n, include_attributes=False) for n in tree.body if isinstance(n, ast.FunctionDef)}


def function_hash(code: str, name: str) -> str:
    source = functions(code).get(name)
    return hashlib.sha256(source.encode()).hexdigest()[:12] if source else ""


def lock_violation(old_code: str, new_code: str, locked_tests: list[str]) -> str | None:
    """Baseline-as-oracle lock: a test that proved a real bug must stay exactly as it was."""
    old, new = functions(old_code), functions(new_code)
    for name in locked_tests:
        if new.get(name) != old.get(name):
            return (f"refused: {name} is evidence of a confirmed bug (passes on baseline, fails on release). "
                    "Keep it unchanged; you may change the other tests in the file.")
    return None


def diff_evidence(error: str, code: str, diff: dict | None) -> list[str]:
    """Snapshot diff lines mentioning an accessible name the failing check was about.

    Names come from the failure (name="..." in the locator) and quoted strings on the test's FAILING
    LINE only, not the whole test: a test that clicks "Sign in" then fails on download isn't BUG-1.
    """
    names = set(LOCATOR_NAME.findall(error))
    line_number = FAILING_LINE.match(error)
    source_lines = code.splitlines()
    if line_number and 0 < int(line_number[1]) <= len(source_lines):
        names |= {a or b for a, b in QUOTED.findall(source_lines[int(line_number[1]) - 1])}
    if not names or not diff:
        return []
    return [f"{where}: {line}" for where, lines in diff.get("changes", {}).items()
            for line in lines if any(f'"{n}"' in line for n in names)]


def triage_run(release_run: dict, files: dict, tests: dict, diff: dict | None, run_one: RunOne,
               baseline_url: str, release_url: str) -> list[dict]:
    """Triage one release run_tests result. Updates `tests` in place; returns trace events.

    files: filename -> {"journey", "code", "heal_attempts"}. tests: "file::name" -> record.
    """
    events = []

    def decide(record: dict, verdict: str, why: str):
        record["verdict"], record["why"] = verdict, why
        record["history"].append(verdict)
        events.append({"test": record["test"], "verdict": verdict, "why": why})

    for result in release_run.get("results", []):
        filename, name = split_test_id(result["test"])
        info = files.get(filename, {})
        code = info.get("code", "")
        record = tests.setdefault(f"{filename}::{name}", {
            "test": f"{filename}::{name}", "file": filename, "name": name, "verdict": None,
            "code_hash": None, "first_error": None, "history": [], "healed": False})
        code_hash = function_hash(code, name)
        was_broken = record["verdict"] in ("broken_test", "gave_up")
        if record["code_hash"] == code_hash and record["verdict"] in DECIDED:
            continue  # same code, already decided: no more runs
        record["code_hash"] = code_hash
        record["heal_attempts"] = info.get("heal_attempts", 0)

        if result["outcome"] == "passed":
            record["healed"] = record["healed"] or was_broken
            decide(record, "passed", "healed: now passes" if was_broken else "passes on release")
            continue

        record["first_error"] = record["first_error"] or result.get("message")
        record["release_error"] = result.get("message")

        # 1. Baseline first: a test that can't pass on the last good release is wrong.
        baseline = run_one(baseline_url, filename, name)
        if baseline["outcome"] != "passed":
            record["baseline_error"] = baseline.get("message")
            if record["heal_attempts"] >= MAX_HEAL_ATTEMPTS:
                decide(record, "gave_up", f"still fails on the baseline after {MAX_HEAL_ATTEMPTS} heal attempts")
            else:
                decide(record, "broken_test", "fails on the baseline (last good release) too, so the test is wrong")
            continue

        # 2. Rerun on the release to rule out flakiness.
        runs = ["failed"]
        for _ in range(FLAKY_RERUNS):
            runs.append(run_one(release_url, filename, name)["outcome"])
            if runs[-1] == "passed":
                break
        if runs[-1] == "passed":
            decide(record, "flaky", f"failed, then passed on rerun ({' -> '.join(runs)}); not reported")
            continue

        # 3. A regression: passes on the baseline, fails on the release every time.
        record["healed"] = record["healed"] or was_broken
        record["release_runs"] = runs
        record["diff_evidence"] = diff_evidence(record["release_error"] or "", code, diff)
        record["journey"] = JOURNEYS.get(info.get("journey"))
        record["category"] = "accessibility" if record["diff_evidence"] else "functional"
        if record["diff_evidence"] or record["journey"]:
            decide(record, "real_bug", f"passes on baseline, fails on release {len(runs)}/{len(runs)} runs")
        else:
            decide(record, "unconfirmed", "regression with no matching snapshot diff or journey; needs review")
    return events


def group_bugs(tests: dict) -> list[dict]:
    """One bug per piece of evidence: tests that hit the same diff line are the same bug."""
    groups: dict[tuple, dict] = {}
    for record in tests.values():
        if record["verdict"] != "real_bug":
            continue
        key = tuple(record["diff_evidence"]) or (record["test"],)
        groups.setdefault(key, {"evidence": record["diff_evidence"], "records": []})["records"].append(record)
    order = {name: i for i, name in enumerate(JOURNEYS.values()) if name}
    bugs = []
    for group in sorted(groups.values(), key=lambda g: order.get(g["records"][0]["journey"], len(order))):
        first = group["records"][0]
        if group["evidence"]:
            where, change = group["evidence"][0].split(": ", 1)
            title = f"{change} ({where})"
        else:
            title = f"{first['journey']} journey broken ({first['test']})"
        bugs.append({"title": title, "category": first["category"], "journey": first["journey"],
                     "diff_evidence": group["evidence"], "tests": [r["test"] for r in group["records"]],
                     "errors": [r["release_error"] for r in group["records"]], "file": first["file"]})
    return bugs
