"""CLI: run the PortalGuard QE graph on one release.

    python -m portalguard.main --mock                    # fake chat model, $0, no key (default)
    python -m portalguard.main --real --release buggy    # gpt-4.1-mini, key from .env
    python -m portalguard.main --release good --auto-approve

    python -m portalguard.main --resume <run_id>         # finish a run paused at the approval step

Without --auto-approve the graph pauses (LangGraph interrupt) before the report for a human decision.
Exit codes: 0 done, 1 error / missing key, 2 portal not reachable, 3 budget stop,
4 paused for approval, 5 report rejected by the reviewer.
"""

import argparse
import functools
import http.server
import sqlite3
import sys
import threading
import urllib.request
from datetime import datetime
from typing import Callable, Optional
from urllib.error import URLError

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from portalguard.agents import RunContext
from portalguard.config import BUGGY_URL, CHECKPOINT_DB, GOOD_URL, MAX_PARALLEL, PORT, PORTAL_DIR, RUNS_DIR
from portalguard.graph import build_graph
from portalguard.llm import make_model
from portalguard.safety import Budget, check_url
from portalguard.tracing import flush, run_config, setup_tracing

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


Approver = Callable[[dict], Optional[dict]]  # interrupt payload -> {"approved", "note"}, or None = decide later


def _drive(app, config: dict, context: RunContext, first_input, approver: Optional[Approver]) -> dict:
    """Invoke the graph; on each interrupt ask the approver and resume. Stops early if nobody decides."""
    state = app.invoke(first_input, config, context=context)
    while state.get("__interrupt__"):
        decision = approver(state["__interrupt__"][0].value) if approver else None
        if decision is None:
            return state  # paused; the checkpoint keeps it (resume with --resume <run_id>)
        state = app.invoke(Command(resume=decision), config, context=context)
    return state


def run_qe(release_url: str, mock: bool = True, baseline_url: str = GOOD_URL, auto_approve: bool = True,
           approver: Optional[Approver] = None, run_id: str | None = None, retry_backoff: bool = True) -> dict:
    """Run the graph end to end. With auto_approve=False, approver decides at the interrupt."""
    check_url(baseline_url)
    check_url(release_url)
    run_id = run_id or f"{datetime.now():%Y%m%d-%H%M%S}-{'mock' if mock else 'real'}"
    keep_awake()
    context = RunContext(model=make_model(mock), budget=Budget(), retry_backoff=retry_backoff)
    config = {"configurable": {"thread_id": run_id}, "max_concurrency": MAX_PARALLEL,
              **run_config(run_id, release_url, mock)}
    first = {"run_id": run_id, "run_dir": str(RUNS_DIR / run_id), "baseline_url": baseline_url,
             "release_url": release_url, "mock": mock, "auto_approve": auto_approve}
    return _drive(build_graph(checkpointer()), config, context, first, approver)


def resume_qe(run_id: str, approver: Approver) -> dict:
    """Pick up a run paused at the approval interrupt, from the SQLite checkpoint (even after a restart)."""
    app = build_graph(checkpointer())
    config = {"configurable": {"thread_id": run_id}, "max_concurrency": MAX_PARALLEL}
    saved = app.get_state(config)
    if not saved.next:
        raise ValueError(f"run {run_id} is not waiting for approval (no checkpoint, or already finished)")
    values = saved.values
    config |= run_config(run_id, values["release_url"], values["mock"])
    context = RunContext(model=make_model(values["mock"]), budget=Budget(used=values.get("usage")))
    return _drive(app, config, context, Command(resume=approver(saved.tasks[0].interrupts[0].value)), approver)


def ask_human(payload: dict) -> Optional[dict]:
    """Terminal approval prompt. No terminal (CI) -> None, so the run stays paused instead of guessing."""
    print(f"\n=== Approval needed: run {payload['run_id']} on {payload['release_url']} ===")
    print(f"Bugs to report ({len(payload['bugs'])}):")
    for bug in payload["bugs"]:
        print(f"  - [{bug['type']}] {bug['title']}")
    print(f"Healed tests: {len(payload['healed'])}. Needs human review: {len(payload['needs_review'])}")
    for test in payload["needs_review"]:
        print(f"  - {test}")
    try:
        answer = input(f"{payload['question']} [y/N] ").strip().lower()
        note = input("Note for the report (optional): ").strip() if answer else ""
    except EOFError:
        return None
    return {"approved": answer in ("y", "yes"), "note": note}


def print_summary(state: dict) -> None:
    if state.get("__interrupt__"):
        print(f"\nRun {state['run_id']} is paused for approval. Resume with: "
              f"python -m portalguard.main --resume {state['run_id']}")
        return
    usage, approval = state.get("usage", {}), state.get("approval", {})
    print(f"\nRun {state['run_id']}: {state.get('stop_reason')}"
          + (f" | {'approved' if approval.get('approved') else 'REJECTED'} by {approval.get('by')}" if approval else ""))
    print(f"Bugs found: {len(state.get('bugs', []))}")
    for bug in state.get("bugs", []):
        print(f"  - [{bug['category']}] {bug['title']}")
    print(f"LLM steps {usage.get('steps', 0)}, tokens {usage.get('tokens', 0):,}, "
          f"cost ${usage.get('cost_usd', 0):.4f}, harness test runs {state.get('harness_runs', 0)}")
    print(f"Report: {state.get('report')}")


def exit_code(state: dict) -> int:
    if state.get("__interrupt__"):
        return 4
    reason = state.get("stop_reason") or ""
    if reason.startswith("portal_unreachable"):
        return 2
    if reason.startswith("budget"):
        return 3
    return 0 if state.get("approval", {}).get("approved", True) else 5


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--mock", action="store_true", default=True, help="scripted fake chat model (default)")
    mode.add_argument("--real", action="store_true", help="gpt-4.1-mini via OPENAI_API_KEY in .env")
    parser.add_argument("--release", default="buggy", help="good, buggy, or a localhost URL")
    parser.add_argument("--auto-approve", action="store_true", help="skip the human approval step (CI, evals)")
    parser.add_argument("--resume", metavar="RUN_ID", help="resume a run paused at the approval step")
    args = parser.parse_args()

    print(setup_tracing())
    try:
        if args.resume:
            print(f"Portal: {ensure_portal()}. Resuming {args.resume}")
            state = resume_qe(args.resume, ask_human)
        else:
            release_url = RELEASES.get(args.release, args.release)
            check_url(release_url)
            print(f"Portal: {ensure_portal()}. Mode: {'real' if args.real else 'mock'}. Release: {release_url}")
            state = run_qe(release_url, mock=not args.real, auto_approve=args.auto_approve, approver=ask_human)
    except (RuntimeError, ValueError) as e:  # missing API key, URL not allowed, nothing to resume
        print(e)
        return 1
    finally:
        flush()
    print_summary(state)
    return exit_code(state)


if __name__ == "__main__":
    sys.exit(main())
