"""runs/<id>/report.md, built from graph state (triage records, budgets), never from the model's text."""

from pathlib import Path

from portalguard.config import MAX_HEAL_ATTEMPTS
from portalguard.coverage import missing_journeys


def _one_line(text) -> str:
    return str(text or "").replace("\n", " ")


def _cell(text) -> str:
    return _one_line(text).replace("|", "\\|")


def write_report(state: dict, bugs: list[dict], model: str, usage: dict) -> Path:
    run_dir = Path(state["run_dir"])
    tests = list(state.get("tests", {}).values())
    by = lambda verdict: [r for r in tests if r["verdict"] == verdict]
    healed = [r for r in tests if r.get("healed")]
    review = by("unconfirmed") + by("gave_up") + by("broken_test")
    covered = {info["journey"] for info in state.get("files", {}).values()}
    missing = missing_journeys(covered)
    approval = state.get("approval") or {}
    release = state["release_url"]

    lines = [
        f"# PortalGuard report: run {state['run_id']}",
        "",
        f"- **Release under test:** {release}",
        f"- **Baseline (last good release):** {state['baseline_url']}",
        f"- **Model:** {model}  |  **Stop reason:** `{state.get('stop_reason') or 'done'}`",
    ]
    if approval:
        verdict = "approved" if approval.get("approved") else "REJECTED (draft, not for release)"
        lines.append(f"- **Human approval:** {verdict} by {approval.get('by', 'reviewer')}"
                     + (f": {approval['note']}" if approval.get("note") else ""))
    lines += [
        "- Synthetic test data only. Verdicts come from Playwright runs by the harness (release, rerun,"
        " baseline), not from the model.",
        "",
        "## Summary",
        "",
        "| Real bugs | Healed tests | Flaky (not reported) | Needs review | LLM steps | Tokens | Cost | Harness test runs |",
        "|---|---|---|---|---|---|---|---|",
        f"| {len(bugs)} | {len(healed)} | {len(by('flaky'))} | {len(review)} | {usage['steps']} | "
        f"{usage['tokens']:,} | ${usage['cost_usd']:.4f} | {state.get('harness_runs', 0)} |",
        "",
        "## Bugs found",
        "",
    ]
    if not bugs:
        lines += ["No real bugs found.", ""]
    for number, bug in enumerate(bugs, 1):
        lines += [f"### {number}. {bug['title']}", "",
                  f"- **Type:** {bug['category']}" + (f"  |  **Journey:** {bug['journey']}" if bug["journey"] else ""),
                  "- **Evidence:**"]
        for test, error in zip(bug["tests"], bug["errors"]):
            lines += [f"  - Test `{test}`: passed on baseline, failed on release 2/2 runs",
                      f"  - Failure: `{_one_line(error)}`"]
        lines += [f"  - Snapshot diff: `{line}`" for line in bug["diff_evidence"]] or \
                 ["  - Snapshot diff: no change in the accessibility tree (functional bug)"]
        lines += [f"- **Reproduce:** `python -m pytest runs/{state['run_id']}/tests/{bug['file']} -p portalguard.fixtures "
                  f"--base-url {release}`", ""]

    lines += ["## Healed tests", ""]
    if healed:
        lines += ["| Test | Attempts | Original error (on baseline) | Now |", "|---|---|---|---|"]
        for r in healed:
            now = {"passed": "passes on release", "real_bug": "valid; fails on release (bug above)"}.get(
                r["verdict"], r["verdict"])
            lines.append(f"| `{r['test']}` | {r.get('heal_attempts', 0)}/{MAX_HEAL_ATTEMPTS} | "
                         f"`{_cell(r['first_error'])}` | {now} |")
    else:
        lines.append("None.")
    lines += ["", "## Flaky tests (not reported as bugs)", ""]
    lines += [f"- `{r['test']}`: {r['why']}" for r in by("flaky")] or ["None."]
    lines += ["", "## Needs human review", ""]
    lines += [f"- `{r['test']}` ({r['verdict']}): {r['why']}. Error: `{_one_line(r.get('release_error'))}`"
              for r in review] or ["None."]

    lines += ["", "## Plan and journey coverage", ""]
    lines += [f"- [{'x' if t['filename'] in state.get('files', {}) else ' '}] `{t['filename']}` "
              f"({t['journey']}{', added by harness' if t.get('source') == 'harness' else ''}): {t['goal']}"
              for t in state.get("todos", [])]
    lines += [f"- Plan note: {note}" for note in state.get("plan_notes", [])]
    lines += ["", f"- Missing journeys: {', '.join(missing) or 'none'}"
              + (" (no accepted test, so bugs there could be missed)" if missing else "")]
    errors = [r for r in state.get("journey_results", []) if r.get("error")]
    lines += [f"- Sub-agent `{r['filename']}` (round {r['round']}) stopped: {r['error']}" for r in errors]

    lines += ["", "## Snapshot diff (baseline -> release)", ""]
    changes = (state.get("diff") or {}).get("changes", {})
    for where, items in changes.items():
        lines += [f"- **{where}**"] + [f"  - `{item}`" for item in items]
    if not changes:
        lines.append("No changes." if state.get("diff") else "No snapshot diff recorded.")
    lines.append("")

    path = run_dir / "report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return path
