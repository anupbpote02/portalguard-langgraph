"""LangChain tools. The model sees only the arguments it may choose; everything else is an
InjectedToolArg that the graph binds (output folders, and which release tests run against).

Each tool returns a short summary; the full data stays on disk (runs/<id>/...).
"""

from pathlib import Path
from typing import Annotated, Literal, Optional

from langchain_core.tools import InjectedToolArg, tool
from pydantic import Field

from portalguard import browser

Journey = Literal["sign_in", "wrong_password", "appointments", "lab_results", "download_pdf", "diff_check"]
Filename = Annotated[str, Field(pattern=r"^test_[a-z0-9_]{1,60}\.py$", description="test_<words>.py, no folders")]
Label = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")]


@tool
def snapshot_page(url: Annotated[str, Field(max_length=200)], label: Label,
                  snapshot_dir: Annotated[str, InjectedToolArg]) -> dict:
    """Sign in to a portal release (localhost only) and save aria snapshots of the sign-in page and
    the dashboard, including every iframe. Returns per-frame headings, buttons, textboxes and links."""
    return browser.take_snapshot(url, label, Path(snapshot_dir))


@tool
def compare_snapshots(baseline: Label, new: Label, snapshot_dir: Annotated[str, InjectedToolArg]) -> dict:
    """Diff two saved snapshots by label. Returns REMOVED / ADDED / CHANGED lines per page and frame,
    flags controls with no accessible name, and new JS errors."""
    return browser.diff_snapshots(baseline, new, Path(snapshot_dir))


@tool
def write_test(filename: Filename, code: Annotated[str, Field(max_length=20_000)], journey: Journey,
               tests_dir: Annotated[str, InjectedToolArg]) -> dict:
    """Write a pytest + Playwright test file. One journey per file; journey says what it tests
    (diff_check = a test written for a snapshot diff)."""
    tests = browser.check_test_code(code)
    path = Path(tests_dir) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    existed = path.exists()
    path.write_text(code, encoding="utf-8", newline="\n")
    return {"written": browser.rel(path), "overwrote": existed, "journey": journey, "tests": tests}


@tool
def run_tests(filename: Optional[Filename] = None, *, base_url: Annotated[str, InjectedToolArg],
              tests_dir: Annotated[str, InjectedToolArg], results_dir: Annotated[str, InjectedToolArg]) -> dict:
    """Run generated tests against the release under test (omit filename to run all).
    Returns pass/fail per test with a one-line failure reason."""
    return browser.run_pytest(base_url, Path(tests_dir), Path(results_dir), filename)


SUBAGENT_TOOLS = [write_test, run_tests]
TOOLS_BY_NAME = {t.name: t for t in (snapshot_page, compare_snapshots, write_test, run_tests)}
