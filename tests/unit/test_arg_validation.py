"""Safety rule: tool arguments are validated (schema, sub-agent scope, AST checks) before anything runs."""

import json

import pytest
from pydantic import ValidationError

from portalguard.agents import execute_tool
from portalguard.mock import JOURNEY_TESTS
from portalguard.tools import write_test

TASK = {"id": "sign_in", "journey": "sign_in", "filename": "test_sign_in.py", "goal": "g"}


def call(name, **args):
    return {"name": name, "args": args, "id": "c1"}


def run(tmp_path, tool_call, state=None):
    paths = {"tests": str(tmp_path / "tests"), "results": str(tmp_path / "results")}
    content, status = execute_tool(tool_call, TASK, paths, "http://localhost:8000/buggy/", state or {"code": None, "run": None})
    return json.loads(content), status


@pytest.mark.parametrize("args", [
    {"filename": "../conftest.py", "code": JOURNEY_TESTS["sign_in"], "journey": "sign_in"},
    {"filename": "test_x.py", "code": JOURNEY_TESTS["sign_in"], "journey": "delete_everything"},
])
def test_tool_schema_rejects_bad_arguments(tmp_path, args):
    with pytest.raises(ValidationError):
        write_test.invoke({**args, "tests_dir": str(tmp_path)})


def test_model_never_sees_harness_arguments():
    assert set(write_test.tool_call_schema.model_json_schema()["properties"]) == {"filename", "code", "journey"}


@pytest.mark.parametrize("code, reason", [
    ("import os\ndef test_x(page):\n    os.remove('x')\n", "import 'os' not allowed"),
    ("def test_x(page):\n    eval('1')\n", "'eval' not allowed"),
    ("def test_x(page):\n    page.__class__\n", "dunder"),
    ("def helper():\n    pass\n", "top-level test_"),
])
def test_unsafe_test_code_rejected(tmp_path, code, reason):
    with pytest.raises(ValueError, match=reason):
        write_test.invoke({"filename": "test_x.py", "code": code, "journey": "diff_check", "tests_dir": str(tmp_path)})


def test_sub_agent_may_only_touch_its_own_file_and_journey(tmp_path):
    other_file = call("write_test", filename="test_other.py", code=JOURNEY_TESTS["sign_in"], journey="sign_in")
    other_journey = call("write_test", filename="test_sign_in.py", code=JOURNEY_TESTS["sign_in"], journey="diff_check")
    assert "only write test_sign_in.py" in run(tmp_path, other_file)[0]["error"]
    assert "journey must be 'sign_in'" in run(tmp_path, other_journey)[0]["error"]
    assert "unknown tool" in run(tmp_path, call("delete_everything"))[0]["error"]
    run_other = call("run_tests", filename="test_other.py")
    assert "only test_sign_in.py" in run(tmp_path, run_other, {"code": "x", "run": None})[0]["error"]


def test_run_tests_cannot_choose_the_release(tmp_path):
    result, status = run(tmp_path, call("run_tests", filename="test_sign_in.py", base_url="https://evil.example.com/"),
                         {"code": "x", "run": None})
    assert status == "error" and "only takes filename" in result["error"]
