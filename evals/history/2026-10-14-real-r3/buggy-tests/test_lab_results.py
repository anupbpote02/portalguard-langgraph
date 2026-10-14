import pytest
from playwright.sync_api import expect

def test_lab_results_frame_contents(signed_in, patient):
    # The lab results are inside a frame with id "lab-results-frame"
    frame = signed_in.frame_locator("#lab-results-frame")

    # Check the "Download PDF" button is visible
    download_button = frame.get_by_role("button", name="Download PDF")
    expect(download_button).to_be_visible()

    # Check that the lab results list contains the expected number of results
    # We expect at least one lab result from the patient fixture
    results = frame.locator(".lab-result-item")
    expect(results).to_have_count(len(patient["labResults"]))

    # Check the text of the first lab result matches the patient data
    if patient["labResults"]:
        first_result = patient["labResults"][0]
        first_result_locator = results.nth(0)
        expect(first_result_locator).to_contain_text(first_result["test"])
        expect(first_result_locator).to_contain_text(first_result["result"])
        expect(first_result_locator).to_contain_text(first_result["range"])
        expect(first_result_locator).to_contain_text(first_result["date"])
