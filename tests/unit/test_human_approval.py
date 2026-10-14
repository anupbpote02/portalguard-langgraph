"""Human in the loop: the graph pauses before the report, and --auto-approve skips the pause."""

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from portalguard.agents import RunContext
from portalguard.graph import build_graph
from portalguard.llm import make_model


def start_at_approval(tmp_path, auto_approve: bool):
    """Jump straight to the end of triage (no browser), with nothing left to heal."""
    app = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": f"t-{auto_approve}"}}
    state = {"run_id": "t", "run_dir": str(tmp_path), "baseline_url": "http://localhost:8000/good/",
             "release_url": "http://localhost:8000/buggy/", "mock": True, "auto_approve": auto_approve,
             "todos": [], "tests": {}, "files": {}, "tasks": [], "round": 1}
    app.update_state(config, state, as_node="triage")
    return app, config, RunContext(model=make_model(True))


def test_pauses_for_approval_and_records_a_rejection(tmp_path):
    app, config, ctx = start_at_approval(tmp_path, auto_approve=False)
    paused = app.invoke(None, config, context=ctx)
    assert paused["__interrupt__"][0].value["question"] == "Publish this QE report?"
    assert not (tmp_path / "report.md").exists()  # nothing published before the human decides

    done = app.invoke(Command(resume={"approved": False, "note": "needs a second look"}), config, context=ctx)
    assert done["approval"]["approved"] is False
    assert "REJECTED" in (tmp_path / "report.md").read_text(encoding="utf-8")


def test_auto_approve_skips_the_pause(tmp_path):
    app, config, ctx = start_at_approval(tmp_path, auto_approve=True)
    done = app.invoke(None, config, context=ctx)
    assert "__interrupt__" not in done
    assert done["approval"] == {"approved": True, "by": "--auto-approve"}
