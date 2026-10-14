"""The LLM parts: the planner (writes the to-do list) and the journey sub-agent (one per to-do).

Deep-agent pattern: the planner only plans; each sub-agent gets a fresh, small context (its to-do,
the baseline summary, the diff) instead of one long conversation, and works through files on disk.
The safety rules live here, in code that runs between the model and the tools.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from pydantic import ValidationError

from portalguard import browser
from portalguard.config import MAX_SUBAGENT_STEPS, REQUIRED_JOURNEYS
from portalguard.coverage import check_journey
from portalguard.llm import model_name, usage_cost, with_api_retries
from portalguard.safety import Budget, BudgetExceeded
from portalguard.tools import SUBAGENT_TOOLS, run_tests, write_test
from portalguard.triage import lock_violation

MAX_TOOL_RESULT_CHARS = 6_000


@dataclass
class RunContext:
    """Per-invocation dependencies (LangGraph Runtime context): not part of the checkpointed state."""
    model: BaseChatModel
    budget: Budget = field(default_factory=Budget)
    retry_backoff: bool = True

    @property
    def model_name(self) -> str:
        return model_name(self.model)

    def call_model(self, runnable, messages):
        """Budget check BEFORE the call, API retries around it, usage added after it."""
        self.budget.check()
        reply = with_api_retries(runnable, backoff=self.retry_backoff).invoke(messages)
        self.budget.add(*usage_cost(reply, self.model_name))
        return reply


def todo(journey: str, goal: str, index: int = 0) -> dict:
    filename = f"test_{journey}.py" if journey != "diff_check" else f"test_diff_check_{index}.py"
    return {"id": filename.removesuffix(".py").removeprefix("test_"), "journey": journey,
            "filename": filename, "goal": goal}


def default_plan() -> list[dict]:
    return [todo(j, f"Test the {j.replace('_', ' ')} journey on the baseline spec") for j in REQUIRED_JOURNEYS]


# ---------------------------------------------------------------- journey sub-agent

SUBAGENT_PROMPT = """You are a PortalGuard journey sub-agent testing the Harbor General patient portal.
All data is synthetic. You own exactly ONE test file (given below). Do this:
1. write_test that file, with the given journey argument.
2. run_tests on that file (it runs against the release under test). Then stop.
If write_test is rejected, read the reason, fix the code and call write_test again.
Do not try to make a test pass on the release: tests describe the BASELINE (last good release),
so a failure on the release may be a real bug. The harness decides what failures mean.

Test rules: Python, pytest + Playwright sync API, only import from playwright.sync_api / pytest / re / json.
Fixtures: page, base_url (ends with "/"), patient (dict: email, password, name, mrn, appointments,
labResults), signed_in (page already on the dashboard). The sign-in page is base_url + "index.html".
Use get_by_role / get_by_label locators with names from the baseline summary; don't guess them.
Pass name as a keyword: get_by_role("button", name="Sign in").
Assert with expect(...) (it waits), e.g. expect(locator).to_be_visible(), expect(page).to_have_url(...).
Never assert locator.is_visible(): it does not wait.
Lab results are inside page.frame_locator("#lab-results-frame"). Check downloads with
page.expect_download() and suggested_filename == f"lab-results-{patient['mrn']}.pdf".
Use signed_in unless the test is about signing in, so each test fails for one reason only.
Journey tests must exercise the journey: sign_in / wrong_password fill in and submit the form;
appointments / lab_results check the items (to_have_count / to_have_text); download_pdf clicks,
waits with expect_download() and checks suggested_filename. diff_check tests check one snapshot diff."""


def task_brief(task: dict, snapshots: dict, diff: dict | None) -> str:
    baseline = snapshots.get("baseline", {}).get("pages", {})
    names = {f"{page} / {frame}": {k: v for k, v in info.items() if k != "nodes" and v}
             for page, frames in baseline.items() for frame, info in frames.items()}
    lines = [f"Journey: {task['journey']}", f"Filename: {task['filename']}", f"Goal: {task['goal']}"]
    if task.get("heal_attempt"):
        lines += [
            f"Heal attempt: {task['heal_attempt']}",
            "Your previous test FAILS ON THE BASELINE too, so the test is wrong. Fix it.",
            f"Failure on the baseline: {task['baseline_error']}",
            f"Previous code:\n```python\n{task['previous_code']}```",
        ]
        if task.get("locked"):
            lines.append(f"Keep these tests unchanged (they prove real bugs): {', '.join(task['locked'])}")
    lines += ["", "Baseline accessible names per page / frame (tests must pass on the baseline):",
              json.dumps(names, indent=1),
              "", "Snapshot diff baseline -> release:", json.dumps((diff or {}).get("changes", {}), indent=1)]
    return "\n".join(lines)


def _error(text: str) -> tuple[str, str]:
    return json.dumps({"error": text}), "error"


def _validation_message(error: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors())


def execute_tool(call: dict, task: dict, paths: dict, release_url: str, state: dict) -> tuple[str, str]:
    """Run one tool call for a sub-agent after the safety checks. Never raises.

    state (mutable, per sub-agent): "code" = last accepted code, "run" = last run_tests result.
    """
    args = dict(call.get("args") or {})
    if call["name"] == "write_test":
        # Argument validation: the sub-agent may only write its own file, for its own journey.
        if args.get("filename") != task["filename"]:
            return _error(f"you may only write {task['filename']}")
        if args.get("journey") != task["journey"]:
            return _error(f"journey must be '{task['journey']}' for this file")
        code = args.get("code") if isinstance(args.get("code"), str) else ""
        refusal = check_journey(code, task["journey"]) or \
            lock_violation(task.get("previous_code", ""), code, task.get("locked", []))
        if refusal:
            return _error(refusal)
        try:
            result = write_test.invoke({**args, "tests_dir": paths["tests"]})
        except ValidationError as e:
            return _error(f"invalid arguments: {_validation_message(e)}")
        except ValueError as e:
            return _error(str(e))
        state["code"] = code
        return json.dumps(result), "success"

    if call["name"] == "run_tests":
        if args.get("filename", task["filename"]) != task["filename"] or set(args) - {"filename"}:
            return _error(f"run_tests only takes filename, and only {task['filename']}")
        if state.get("code") is None:
            return _error("write_test first")
        try:
            result = run_tests.invoke({"filename": task["filename"], "base_url": release_url,
                                       "tests_dir": paths["tests"], "results_dir": paths["results"]})
        except (ValidationError, ValueError) as e:
            return _error(str(e))
        state["run"] = result
        return json.dumps(result)[:MAX_TOOL_RESULT_CHARS], "success" if not result.get("error") else "error"

    return _error(f"unknown tool '{call['name']}'; available: write_test, run_tests")


def run_journey(task: dict, ctx: RunContext, snapshots: dict, diff: dict | None, release_url: str,
                run_dir: Path) -> dict:
    """One sub-agent: write_test then run_tests for one file, in its own short conversation."""
    paths = {"tests": str(run_dir / "tests"), "results": str(run_dir / "test-results")}
    model = ctx.model.bind_tools(SUBAGENT_TOOLS)
    messages = [SystemMessage(SUBAGENT_PROMPT), HumanMessage(task_brief(task, snapshots, diff))]
    state: dict = {"code": None, "run": None}
    error, llm_calls, refusals = None, 0, 0

    for _ in range(MAX_SUBAGENT_STEPS):
        try:
            reply = ctx.call_model(model, messages)
        except BudgetExceeded as e:
            error = f"budget: {e}"
            break
        except Exception as e:  # API down after retries, bad response: stop this sub-agent, not the run
            error = f"llm_error: {type(e).__name__}: {e}"
            break
        llm_calls += 1
        messages.append(reply)
        if not reply.tool_calls:
            break
        for call in reply.tool_calls:
            content, status = execute_tool(call, task, paths, release_url, state)
            refusals += status == "error"
            messages.append(ToolMessage(content, tool_call_id=call["id"], name=call["name"], status=status))
        if state["run"] is not None:
            break  # written and run: the harness takes it from here

    if state["code"] is not None and state["run"] is None:
        # The model wrote a test but never ran it: the harness runs it, so triage still sees it.
        state["run"] = browser.run_pytest(release_url, Path(paths["tests"]), Path(paths["results"]),
                                          task["filename"])
    return {"todo": task["id"], "journey": task["journey"], "filename": task["filename"],
            "round": task.get("round", 0), "heal_attempt": task.get("heal_attempt", 0),
            "code": state["code"], "run": state["run"], "error": error,
            "llm_calls": llm_calls, "refusals": refusals}
