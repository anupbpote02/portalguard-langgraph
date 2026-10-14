"""Safety rule: a journey test must exercise its journey, and the plan must cover every journey."""

import json

from portalguard.agents import execute_tool
from portalguard.coverage import check_journey, missing_journeys, missing_steps
from portalguard.mock import JOURNEY_TESTS

VISIBLE_ONLY = (
    "def test_download_button(signed_in):\n"
    '    expect(signed_in.frame_locator("#lab-results-frame").get_by_role("button", name="Download PDF")).to_be_visible()\n'
)


def test_visibility_is_not_a_download_test():
    assert "check download.suggested_filename" in missing_steps(VISIBLE_ONLY, "download_pdf")
    assert check_journey(VISIBLE_ONLY, "download_pdf").startswith("rejected")


def test_every_mock_journey_test_is_covered():
    for journey, code in JOURNEY_TESTS.items():
        assert check_journey(code, journey) is None, journey


def test_write_test_refuses_uncovered_journey_file(tmp_path):
    task = {"id": "download_pdf", "journey": "download_pdf", "filename": "test_download_pdf.py", "goal": "g"}
    call = {"name": "write_test", "id": "c1",
            "args": {"filename": "test_download_pdf.py", "code": VISIBLE_ONLY, "journey": "download_pdf"}}
    content, status = execute_tool(call, task, {"tests": str(tmp_path), "results": str(tmp_path)},
                                   "http://localhost:8000/buggy/", {"code": None, "run": None})
    assert status == "error" and "rejected" in json.loads(content)["error"]
    assert not (tmp_path / "test_download_pdf.py").exists()


def test_missing_journeys():
    assert missing_journeys({"sign_in", "appointments"}) == ["wrong_password", "lab_results", "download_pdf"]
