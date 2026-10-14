"""CLI: run the PortalGuard QE graph on one release.

    python -m portalguard.main --mock                    # fake chat model, $0, no key (default)
    python -m portalguard.main --real --release buggy    # gpt-4.1-mini, key from .env
    python -m portalguard.main --release good --auto-approve

Exit codes: 0 done, 1 error / missing key, 2 portal not reachable, 3 budget stop.
"""

import argparse
import functools
import http.server
import sqlite3
import sys
import threading
import urllib.request
from datetime import datetime
from urllib.error import URLError

from dotenv import load_dotenv
from langgraph.checkpoint.sqlite import SqliteSaver

from portalguard.agents import RunContext
from portalguard.config import BUGGY_URL, CHECKPOINT_DB, GOOD_URL, MAX_PARALLEL, PORT, PORTAL_DIR, REPO_ROOT, RUNS_DIR
from portalguard.graph import build_graph
from portalguard.llm import make_model
from portalguard.safety import Budget, check_url

RELEASES = {"good": GOOD_URL, "buggy": BUGGY_URL}


def ensure_portal() -> str:
    """Use the running portal, or serve portal/ on a background thread (handy in CI and evals)."""
    try:
        urllib.request.urlopen(GOOD_URL, timeout=2)
        return "already running"
    except URLError:
        pass

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    handler = functools.partial(Quiet, directory=str(PORTAL_DIR))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return "started on a background thread"


def keep_awake() -> None:
    """Windows: keep the machine (and display: Modern Standby ignores the system flag alone) awake
    while a run is in progress, so idle sleep cannot freeze browsers mid-test. Ends with the process."""
    if sys.platform == "win32":
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED, ES_DISPLAY_REQUIRED = 0x80000000, 0x00000001, 0x00000002
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)


def checkpointer() -> SqliteSaver:
    RUNS_DIR.mkdir(exist_ok=True)
    return SqliteSaver(sqlite3.connect(CHECKPOINT_DB, check_same_thread=False))


def run_qe(release_url: str, mock: bool = True, baseline_url: str = GOOD_URL, auto_approve: bool = True,
           run_id: str | None = None, retry_backoff: bool = True) -> dict:
    """Run the graph once, end to end. Returns the final state."""
    check_url(baseline_url)
    check_url(release_url)
    run_id = run_id or f"{datetime.now():%Y%m%d-%H%M%S}-{'mock' if mock else 'real'}"
    run_dir = RUNS_DIR / run_id
    keep_awake()
    context = RunContext(model=make_model(mock), budget=Budget(), retry_backoff=retry_backoff)
    config = {"configurable": {"thread_id": run_id}, "max_concurrency": MAX_PARALLEL}
    app = build_graph(checkpointer())
    return app.invoke({"run_id": run_id, "run_dir": str(run_dir), "baseline_url": baseline_url,
                       "release_url": release_url, "mock": mock, "auto_approve": auto_approve},
                      config, context=context)


def print_summary(state: dict) -> None:
    usage = state.get("usage", {})
    print(f"\nRun {state['run_id']}: {state.get('stop_reason')}")
    print(f"Bugs found: {len(state.get('bugs', []))}")
    for bug in state.get("bugs", []):
        print(f"  - [{bug['category']}] {bug['title']}")
    print(f"LLM steps {usage.get('steps', 0)}, tokens {usage.get('tokens', 0):,}, "
          f"cost ${usage.get('cost_usd', 0):.4f}, harness test runs {state.get('harness_runs', 0)}")
    print(f"Report: {state.get('report')}")


def exit_code(state: dict) -> int:
    reason = state.get("stop_reason") or ""
    return 2 if reason.startswith("portal_unreachable") else 3 if reason.startswith("budget") else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--mock", action="store_true", default=True, help="scripted fake chat model (default)")
    mode.add_argument("--real", action="store_true", help="gpt-4.1-mini via OPENAI_API_KEY in .env")
    parser.add_argument("--release", default="buggy", help="good, buggy, or a localhost URL")
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / ".env")
    release_url = RELEASES.get(args.release, args.release)
    try:
        check_url(release_url)
    except ValueError as e:
        print(e)
        return 1
    print(f"Portal: {ensure_portal()}. Mode: {'real' if args.real else 'mock'}. Release: {release_url}")
    try:
        state = run_qe(release_url, mock=not args.real)
    except RuntimeError as e:  # missing API key
        print(e)
        return 1
    print_summary(state)
    return exit_code(state)


if __name__ == "__main__":
    sys.exit(main())
