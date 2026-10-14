"""Playwright and pytest work behind the tools (ported from the original PortalGuard tools.py).

Big data goes to disk; callers get short summaries (short-term memory: the model never sees a full
aria snapshot or pytest log). Bad arguments raise ValueError; environment problems (server down,
timeout) come back in an "error" field.
"""

import ast
import difflib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from portalguard.config import REPO_ROOT, TEST_USERS_FILE
from portalguard.safety import check_url

PAGE_TIMEOUT_MS = 10_000
MAX_CHANGES_PER_FRAME = 20
TEST_FILENAME = re.compile(r"test_[a-z0-9_]{1,60}\.py")
LABEL = re.compile(r"[A-Za-z0-9_-]{1,40}")
MAX_TEST_BYTES = 20_000
ALLOWED_IMPORTS = {"re", "json", "pytest", "playwright.sync_api"}
BLOCKED_CALLS = {"exec", "eval", "compile", "__import__", "open", "getattr", "setattr", "delattr",
                 "globals", "locals", "vars", "breakpoint", "input"}
TEST_RUN_TIMEOUT_S = 120
MAX_ERROR_CHARS = 400
LOCATOR_REPR = re.compile(r"<Locator frame=<Frame name=[^>]*> selector='([^']*)'>")

# Lines like:  - heading "Lab results" [level=1]   or   - button
ARIA_LINE = re.compile(r'^\s*- (?P<role>[a-z]+)(?: "(?P<name>[^"]*)")?')
NEEDS_NAME = {"button", "link", "textbox", "checkbox", "combobox", "iframe", "img"}
SUMMARY_ROLES = {"heading": "headings", "button": "buttons", "textbox": "textboxes", "link": "links"}


def rel(path: Path) -> str:
    path = Path(path)
    return (path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path).as_posix()


def load_test_users() -> list[dict]:
    return json.loads(TEST_USERS_FILE.read_text(encoding="utf-8"))["users"]


def release_base(url: str) -> str:
    """'http://localhost:8000/buggy/index.html' -> 'http://localhost:8000/buggy/'"""
    if url.endswith(".html"):
        url = url.rsplit("/", 1)[0]
    return url.rstrip("/") + "/"


# ---------------------------------------------------------------- snapshots

def _stable_aria(frame, tries: int = 6, pause_ms: int = 250) -> str:
    """Take aria snapshots until two in a row match, so JS-rendered content has settled."""
    previous = None
    for _ in range(tries):
        current = frame.locator("body").aria_snapshot()
        if current == previous:
            return current
        previous = current
        frame.page.wait_for_timeout(pause_ms)
    return previous


def _frame_key(frame) -> str:
    """Name a frame by its iframe's id (stable across releases), else title, else file name."""
    element = frame.frame_element()
    return element.get_attribute("id") or element.get_attribute("title") or frame.url.rsplit("/", 1)[-1]


def _snapshot_all_frames(page) -> dict[str, str]:
    """Aria snapshot of the main page body AND every iframe (the body snapshot only shows '- iframe')."""
    page.wait_for_load_state("networkidle")
    frames = {"main": _stable_aria(page.main_frame)}
    for frame in page.main_frame.child_frames:
        frame.wait_for_load_state("load")
        frames[_frame_key(frame)] = _stable_aria(frame)
    return frames


def summarize_frame(aria: str) -> dict:
    """Accessible names per role: what a test can use with get_by_role(...) / get_by_label(...)."""
    summary = {"nodes": len(aria.splitlines()), **{key: [] for key in SUMMARY_ROLES.values()}}
    for line in aria.splitlines():
        match = ARIA_LINE.match(line)
        if match and match["role"] in SUMMARY_ROLES:
            summary[SUMMARY_ROLES[match["role"]]].append(match["name"] if match["name"] is not None else "(no name)")
    return summary


def _capture(base: str, user: dict) -> tuple[dict, list[str], str | None]:
    js_errors: list[str] = []
    pages: dict[str, dict[str, str]] = {}
    error = None
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_default_timeout(PAGE_TIMEOUT_MS)
        page.on("pageerror", lambda e: js_errors.append(str(e)))
        try:
            response = page.goto(base + "index.html")
            if response is None or not response.ok:
                raise PlaywrightError(f"HTTP {response.status if response else 'no response'}")
            pages["sign-in"] = _snapshot_all_frames(page)
            # Navigate by stable ids + Enter (not role/name), so an a11y bug such as a nameless
            # "Sign in" button can't stop us from capturing the pages behind it.
            page.fill("#email", user["email"])
            page.fill("#password", user["password"])
            page.press("#password", "Enter")
            page.wait_for_url("**/dashboard.html")
            pages["dashboard"] = _snapshot_all_frames(page)
        except PlaywrightError as e:  # timeouts, connection refused, etc.
            error = f"Failed on {page.url}: {str(e).splitlines()[0]}"
        finally:
            browser.close()
    return pages, js_errors, error


def take_snapshot(url: str, label: str, snapshot_dir: Path) -> dict:
    """Sign in to a release; save aria snapshots of 'sign-in' and 'dashboard' (with every iframe)."""
    check_url(url)
    if not LABEL.fullmatch(label):
        raise ValueError("label must be 1-40 letters, digits, '-' or '_'")
    base = release_base(url)
    user = load_test_users()[0]
    for _attempt in range(2):  # one retry: a stalled page load shouldn't cost us the whole baseline
        pages, js_errors, error = _capture(base, user)
        if not error:
            break
    snapshot_dir = Path(snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    path = snapshot_dir / f"{label}.json"
    path.write_text(json.dumps({
        "label": label, "url": base, "signed_in_as": user["email"],
        "taken_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "error": error, "js_errors": js_errors, "pages": pages,
    }, indent=2), encoding="utf-8")
    return {
        "saved": rel(path), "label": label, "error": error, "js_errors": js_errors,
        "pages": {name: {frame: summarize_frame(aria) for frame, aria in frames.items()}
                  for name, frames in pages.items()},
    }


def _describe(line: str) -> str:
    """'    - button' -> 'button (no accessible name)'; otherwise just strip the YAML dash."""
    text = line.strip().removeprefix("- ")
    match = ARIA_LINE.match(line)
    if match and match["role"] in NEEDS_NAME and not match["name"]:
        text += " (no accessible name)"
    return text


def diff_snapshots(baseline: str, new: str, snapshot_dir: Path) -> dict:
    """Diff two saved snapshots by label, page by page and frame by frame."""
    def load(label):
        if not LABEL.fullmatch(label):
            raise ValueError("snapshot label must be 1-40 letters, digits, '-' or '_'")
        path = Path(snapshot_dir) / f"{label}.json"
        if not path.exists():
            raise ValueError(f"no snapshot with label '{label}'; take it with snapshot_page first")
        return json.loads(path.read_text(encoding="utf-8"))

    old_data, new_data = load(baseline), load(new)
    changes: dict[str, list[str]] = {}
    unchanged: list[str] = []
    page_names = list(old_data["pages"]) + [p for p in new_data["pages"] if p not in old_data["pages"]]
    for page_name in page_names:
        old_frames, new_frames = old_data["pages"].get(page_name), new_data["pages"].get(page_name)
        if old_frames is None or new_frames is None:
            changes[page_name] = ["PAGE MISSING in " + ("baseline" if old_frames is None else "new release")]
            continue
        for frame in sorted(set(old_frames) | set(new_frames), key=lambda f: (f != "main", f)):
            where = f"{page_name} / {frame}"
            if frame not in new_frames:
                changes[where] = ["FRAME MISSING in new release"]
                continue
            if frame not in old_frames:
                changes[where] = ["NEW FRAME (not in baseline)"]
                continue
            old_lines, new_lines = old_frames[frame].splitlines(), new_frames[frame].splitlines()
            found = []
            matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
            for op, a1, a2, b1, b2 in matcher.get_opcodes():
                if op == "delete":
                    found += [f"REMOVED: {_describe(line)}" for line in old_lines[a1:a2]]
                elif op == "insert":
                    found += [f"ADDED: {_describe(line)}" for line in new_lines[b1:b2]]
                elif op == "replace":
                    found += [f"CHANGED: {_describe(o)}  ->  {_describe(n)}"
                              for o, n in zip(old_lines[a1:a2], new_lines[b1:b2])]
                    found += [f"REMOVED: {_describe(line)}" for line in old_lines[a1 + (b2 - b1):a2]]
                    found += [f"ADDED: {_describe(line)}" for line in new_lines[b1 + (a2 - a1):b2]]
            if found:
                extra = len(found) - MAX_CHANGES_PER_FRAME
                changes[where] = found[:MAX_CHANGES_PER_FRAME] + ([f"... {extra} more"] if extra > 0 else [])
            else:
                unchanged.append(where)

    return {
        "baseline": old_data["label"], "new": new_data["label"],
        "total_changes": sum(len(c) for c in changes.values()),
        "changes": changes, "unchanged": unchanged,
        "new_js_errors": [e for e in new_data["js_errors"] if e not in old_data["js_errors"]],
        "new_release_error": new_data["error"],
    }


# ---------------------------------------------------------------- tests

def check_test_code(code: str) -> list[str]:
    """Static checks on model-written test code (a guardrail, not a sandbox). Returns test names."""
    if len(code.encode("utf-8")) > MAX_TEST_BYTES:
        raise ValueError(f"test code is over {MAX_TEST_BYTES} bytes")
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise ValueError(f"syntax error on line {e.lineno}: {e.msg}") from None
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = [node.module or ""]
        else:
            modules = []
        for module in modules:
            if module not in ALLOWED_IMPORTS:
                raise ValueError(f"import '{module}' not allowed; allowed: {sorted(ALLOWED_IMPORTS)}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in BLOCKED_CALLS:
            raise ValueError(f"call to '{node.func.id}' not allowed in tests")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ValueError(f"dunder attribute '{node.attr}' not allowed in tests")
    tests = [n.name for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
    if not tests:
        raise ValueError("file must define at least one top-level test_* function")
    return tests


def _short_failure(element) -> str:
    """One line the model can act on: 'line 14: AssertionError: ... | waiting for get_by_role(...)'."""
    text = LOCATOR_REPR.sub(r"locator(\1)", element.text or element.get("message", ""))
    lines, waiting_for, in_call_log = [], None, False
    for line in text.splitlines():
        if not line.startswith("E "):
            continue
        detail = line[1:].strip().replace("playwright._impl._errors.", "")
        if detail.startswith(("Call log", "=====")):
            in_call_log = True
        elif in_call_log:
            if waiting_for is None and detail.lstrip("- ").startswith("waiting for "):
                waiting_for = detail.lstrip("- ")
        elif detail:
            lines.append(detail)
    if waiting_for and not any(waiting_for.removeprefix("waiting for ") in line for line in lines):
        lines.append(waiting_for)
    location = re.search(r"(test_[a-z0-9_]+\.py):(\d+):", text)  # first frame = the test's own line
    prefix = f"line {location[2]}: " if location else ""
    return (prefix + (" | ".join(lines) or element.get("message", "failed")))[:MAX_ERROR_CHARS]


def run_pytest(base_url: str, tests_dir: Path, results_dir: Path, filename: str | None = None,
               test_name: str | None = None) -> dict:
    """Run generated tests against one release; pass/fail from pytest's JUnit XML, never from the LLM."""
    check_url(base_url)
    base_url = release_base(base_url)
    tests_dir = Path(tests_dir)
    if filename is not None:
        if not TEST_FILENAME.fullmatch(filename):
            raise ValueError("filename must look like test_<lowercase_words>.py")
        if not (tests_dir / filename).exists():
            raise ValueError(f"no such test file: {filename}")
    if test_name is not None and (filename is None or not re.fullmatch(r"test_\w{1,80}", test_name)):
        raise ValueError("test_name needs a filename and must look like test_<words>")
    target = str(tests_dir / filename) if filename else str(tests_dir)
    if test_name:
        target += f"::{test_name}"

    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    stamp = f"{datetime.now():%H%M%S-%f}-{(filename or 'all').removesuffix('.py')}"
    junit_path = results_dir / f"junit-{stamp}.xml"
    log_path = results_dir / f"pytest-{stamp}.log"
    # -p portalguard.fixtures: the human-written fixtures + localhost route guard for generated tests.
    # --output per run: pytest-playwright empties its output folder, which parallel runs must not share.
    command = [sys.executable, "-m", "pytest", target, "--base-url", base_url, "-q",
               "-p", "no:cacheprovider", "-p", "portalguard.fixtures", "--import-mode=importlib",
               f"--output={results_dir / ('pw-' + stamp)}", f"--junitxml={junit_path}"]
    try:
        proc = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=TEST_RUN_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {"error": f"test run timed out after {TEST_RUN_TIMEOUT_S}s", "base_url": base_url}
    log_path.write_text(proc.stdout + proc.stderr, encoding="utf-8")
    if not junit_path.exists():
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-3:]
        return {"error": "pytest did not run: " + " | ".join(tail), "base_url": base_url}

    results = []
    for case in ET.parse(junit_path).getroot().iter("testcase"):
        file = case.get("classname", "").rsplit(".", 1)[-1] + ".py"
        result = {"test": f"{file}::{case.get('name')}", "outcome": "passed"}
        for tag in ("failure", "error", "skipped"):
            element = case.find(tag)
            if element is not None:
                result["outcome"] = "failed" if tag == "failure" else tag
                result["message"] = _short_failure(element)
                break
        results.append(result)
    return {
        "base_url": base_url,
        "passed": sum(r["outcome"] == "passed" for r in results),
        "failed": sum(r["outcome"] != "passed" for r in results),
        "results": results,
        "log": rel(log_path),
    }
