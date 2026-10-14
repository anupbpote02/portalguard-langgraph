import pytest
from playwright.sync_api import expect

def test_lab_results_frame_contents(signed_in, patient):
    # Access the frame's body
    frame_body = signed_in.frame_locator("#lab-results-frame").locator("body")

    # Check the "Lab results" heading is present on the baseline
    heading = frame_body.get_by_role("heading", name="Lab results")
    expect(heading).to_be_visible()

    # Check the "Download PDF" button is visible
    download_button = frame_body.get_by_role("button", name="Download PDF")
    expect(download_button).to_be_visible()

    # Check that the frame contains the text of each lab result test name
    for lab_result in patient['labResults']:
        expect(frame_body).to_contain_text(lab_result['test'])

    # Check that at least one row exists
    rows = frame_body.get_by_role("row")
    expect(rows).to_have_count(lambda c: c >= 1)  # at least one row
