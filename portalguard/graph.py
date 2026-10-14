"""The QE loop as a LangGraph StateGraph.

    snapshot -> compare -> planner -> journey sub-agents -> triage --(broken tests left?)--> heal (journeys again)
                                                                  \\--> report

State is plain JSON-able dicts so the checkpointer can store every step. The model, the budget
and the retry settings are per-invocation dependencies (Runtime context), not state.
"""

import copy
import operator
from pathlib import Path
from typing import Annotated, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from portalguard import browser
from portalguard.agents import RunContext, default_plan, run_journey
from portalguard.config import MAX_HEAL_ATTEMPTS
from portalguard.report import write_report
from portalguard.safety import check_url
from portalguard.tools import compare_snapshots, snapshot_page
from portalguard.triage import group_bugs, triage_run


class QEState(TypedDict, total=False):
    run_id: str
    run_dir: str
    baseline_url: str
    release_url: str
    mock: bool
    auto_approve: bool
    snapshots: dict                   # label -> snapshot_page summary (full data on disk)
    diff: dict                        # compare_snapshots result
    todos: list[dict]                 # the planner's to-do list
    round: int                        # 0 = first pass, 1.. = heal rounds
    tasks: list[dict]                 # what the journey node works on this round
    journey_results: Annotated[list[dict], operator.add]  # sub-agents append (parallel-safe)
    files: dict                       # filename -> {"journey", "code", "heal_attempts"}
    tests: dict                       # "file::test" -> triage record
    events: Annotated[list[dict], operator.add]
    harness_runs: int                 # test runs triage did itself (baseline + reruns)
    usage: dict                       # budget snapshot: steps, tokens, cost_usd
    stop_reason: Optional[str]
    bugs: list[dict]
    report: str


# ---------------------------------------------------------------- nodes

def snapshot(state: QEState) -> dict:
    snapshot_dir = str(Path(state["run_dir"]) / "snapshots")
    snapshots = {}
    for label, url in (("baseline", state["baseline_url"]), ("release", state["release_url"])):
        check_url(url)  # allowlist, before any browser opens
        snapshots[label] = snapshot_page.invoke({"url": url, "label": label, "snapshot_dir": snapshot_dir})
        if snapshots[label]["error"]:
            return {"snapshots": snapshots, "stop_reason": f"portal_unreachable: {snapshots[label]['error']}"}
    return {"snapshots": snapshots}


def compare(state: QEState) -> dict:
    return {"diff": compare_snapshots.invoke({"baseline": "baseline", "new": "release",
                                              "snapshot_dir": str(Path(state["run_dir"]) / "snapshots")})}


def planner(state: QEState, runtime: Runtime[RunContext]) -> dict:
    todos = default_plan()
    return {"todos": todos, "round": 0, "tasks": [{**t, "round": 0} for t in todos]}


def journeys(state: QEState, runtime: Runtime[RunContext]) -> dict:
    """Sequential for now: one sub-agent per task, one after another."""
    results = [run_journey(task, runtime.context, state["snapshots"], state.get("diff"),
                           state["release_url"], Path(state["run_dir"])) for task in state["tasks"]]
    return {"journey_results": results}


def triage(state: QEState, runtime: Runtime[RunContext]) -> dict:
    """Deterministic: verdict per failing test (baseline = oracle), then decide what to heal."""
    files, tests = copy.deepcopy(state.get("files", {})), copy.deepcopy(state.get("tests", {}))
    run_dir = Path(state["run_dir"])
    runs = {"count": state.get("harness_runs", 0)}

    def run_one(base_url: str, filename: str, name: str) -> dict:
        runs["count"] += 1
        result = browser.run_pytest(base_url, run_dir / "tests", run_dir / "test-results", filename, name)
        return (result.get("results") or [{"outcome": "error", "message": result.get("error", "no result")}])[0]

    events, stop_reason = [], state.get("stop_reason")
    this_round = [r for r in state.get("journey_results", []) if r["round"] == state["round"]]
    for result in this_round:
        if result["error"] and result["error"].startswith("budget"):
            stop_reason = "budget_exceeded"
        if result["code"] is None:
            continue
        info = files.setdefault(result["filename"], {"journey": result["journey"], "heal_attempts": 0})
        info["code"] = result["code"]
        if result["run"] and not result["run"].get("error"):
            events += triage_run(result["run"], files, tests, state.get("diff"), run_one,
                                 state["baseline_url"], state["release_url"])

    # Heal tasks: files with a broken test and attempts left (and budget left).
    tasks = []
    if not stop_reason:
        todos = {t["filename"]: t for t in state["todos"]}
        for filename, info in files.items():
            broken = [r for r in tests.values() if r["file"] == filename and r["verdict"] == "broken_test"]
            if not broken or info["heal_attempts"] >= MAX_HEAL_ATTEMPTS:
                continue
            info["heal_attempts"] += 1
            tasks.append({**todos[filename], "round": state["round"] + 1, "heal_attempt": info["heal_attempts"],
                          "previous_code": info["code"], "baseline_error": broken[0].get("baseline_error"),
                          "locked": [r["name"] for r in tests.values()
                                     if r["file"] == filename and r["verdict"] == "real_bug"]})
    return {"files": files, "tests": tests, "events": events, "harness_runs": runs["count"],
            "tasks": tasks, "round": state["round"] + 1, "usage": runtime.context.budget.snapshot(),
            "stop_reason": stop_reason}


def report(state: QEState, runtime: Runtime[RunContext]) -> dict:
    bugs = group_bugs(state.get("tests", {}))
    path = write_report(state, bugs, runtime.context.model_name, runtime.context.budget.snapshot())
    return {"bugs": bugs, "report": browser.rel(path), "usage": runtime.context.budget.snapshot(),
            "stop_reason": state.get("stop_reason") or "done"}


# ---------------------------------------------------------------- edges

def after_snapshot(state: QEState) -> str:
    return "report" if state.get("stop_reason") else "compare"


def after_triage(state: QEState) -> str:
    """Triage as a conditional edge: heal broken tests, or move on."""
    return "journeys" if state.get("tasks") else "report"


def build_graph(checkpointer=None):
    graph = StateGraph(QEState, context_schema=RunContext)
    for name, node in (("snapshot", snapshot), ("compare", compare), ("planner", planner),
                       ("journeys", journeys), ("triage", triage), ("report", report)):
        graph.add_node(name, node)
    graph.add_edge(START, "snapshot")
    graph.add_conditional_edges("snapshot", after_snapshot, ["compare", "report"])
    graph.add_edge("compare", "planner")
    graph.add_edge("planner", "journeys")
    graph.add_edge("journeys", "triage")
    graph.add_conditional_edges("triage", after_triage, ["journeys", "report"])
    graph.add_edge("report", END)
    return graph.compile(checkpointer=checkpointer)
