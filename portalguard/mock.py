"""Scripted replies for the fake chat model (--mock). Behaves like a reasonable model would:

- planner: one to-do per journey plus one diff check;
- journey sub-agent: write_test, then run_tests, then a one-line summary;
- the lab results test starts with a wrong iframe selector ("#labs-frame") so healing is visible:
  heal 1 is still wrong ("#lab_results_frame"), heal 2 uses the id from baseline_has.
"""

import json
import re
import uuid

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

JOURNEY_TESTS = {
    "sign_in": '''\
from playwright.sync_api import Page, expect


def test_sign_in_with_valid_credentials(page: Page, base_url: str, patient: dict):
    page.goto(base_url + "index.html")
    page.get_by_label("Email").fill(patient["email"])
    page.get_by_label("Password").fill(patient["password"])
    page.get_by_role("button", name="Sign in").click()
    expect(page).to_have_url(base_url + "dashboard.html")
    expect(page.get_by_role("heading", name=f"Welcome, {patient['name']}")).to_be_visible()
''',
    "wrong_password": '''\
from playwright.sync_api import Page, expect


def test_wrong_password_shows_alert(page: Page, base_url: str, patient: dict):
    page.goto(base_url + "index.html")
    page.get_by_label("Email").fill(patient["email"])
    page.get_by_label("Password").fill("wrong-password")
    page.get_by_label("Password").press("Enter")
    expect(page.get_by_role("alert")).to_have_text("Incorrect email or password. Please try again.")
    expect(page).to_have_url(base_url + "index.html")
''',
    "appointments": '''\
from playwright.sync_api import Page, expect


def test_upcoming_appointments_listed(signed_in: Page):
    expect(signed_in.get_by_role("heading", name="Upcoming appointments")).to_be_visible()
    expect(signed_in.get_by_role("listitem")).to_have_count(2)
''',
    "lab_results": '''\
from playwright.sync_api import Page, expect


def test_lab_results_shown_in_iframe(signed_in: Page, patient: dict):
    lab = signed_in.frame_locator("#lab-results-frame")
    expect(lab.get_by_role("heading", name="Lab results")).to_be_visible()
    expect(lab.get_by_role("row")).to_have_count(4)  # header + 3 results
    expect(lab.get_by_role("cell", name=patient["labResults"][0]["test"])).to_be_visible()
''',
    "download_pdf": '''\
from playwright.sync_api import Page, expect


def test_download_lab_results_pdf(signed_in: Page, patient: dict):
    lab = signed_in.frame_locator("#lab-results-frame")
    with signed_in.expect_download() as download_info:
        lab.get_by_role("button", name="Download PDF").click()
    assert download_info.value.suggested_filename == f"lab-results-{patient['mrn']}.pdf"
    expect(lab.get_by_role("status")).to_have_text("Download started")
''',
    "diff_check": '''\
from playwright.sync_api import Page, expect


def test_sign_in_button_has_accessible_name(page: Page, base_url: str):
    page.goto(base_url + "index.html")
    expect(page.get_by_role("button", name="Sign in")).to_be_visible()
''',
}
LAB_FRAME_ATTEMPTS = ["#labs-frame", "#lab_results_frame", "#lab-results-frame"]  # first try, heal 1, heal 2


def _call(name: str, args: dict) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call_{uuid.uuid4().hex[:8]}"}])


def _field(text: str, name: str) -> str | None:
    match = re.search(rf"^{name}: (.+)$", text, re.M)
    return match[1].strip() if match else None


def plan(messages) -> AIMessage:
    todos = [{"journey": j, "goal": f"Test the {j.replace('_', ' ')} journey"}
             for j in ("sign_in", "wrong_password", "appointments", "lab_results", "download_pdf")]
    todos.append({"journey": "diff_check", "goal": 'Check the "Sign in" button still has an accessible name'})
    return _call("write_todos", {"todos": todos})


def journey_turn(messages) -> AIMessage:
    task = messages[1].content
    journey, filename = _field(task, "Journey"), _field(task, "Filename")
    heal = int(_field(task, "Heal attempt") or 0)
    last = messages[-1]
    if isinstance(last, ToolMessage) and last.name == "write_test" and last.status != "error":
        return _call("run_tests", {"filename": filename})
    if isinstance(last, ToolMessage) and last.name == "run_tests":
        result = json.loads(last.content)
        return AIMessage(content=f"Ran {filename}: {result.get('passed', 0)} passed, {result.get('failed', 0)} failed.")
    code = JOURNEY_TESTS[journey]
    if journey == "lab_results":
        code = code.replace('"#lab-results-frame"', f'"{LAB_FRAME_ATTEMPTS[min(heal, 2)]}"')
    return _call("write_test", {"filename": filename, "code": code, "journey": journey})


def respond(messages) -> AIMessage:
    system = messages[0].content if messages and isinstance(messages[0], SystemMessage) else ""
    return plan(messages) if "PortalGuard planner" in system else journey_turn(messages)
