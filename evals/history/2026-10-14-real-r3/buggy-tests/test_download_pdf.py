import pytest
from playwright.sync_api import expect

def test_download_pdf(signed_in, page, patient, base_url):
    # The lab results are inside a frame with id "lab-results-frame"
    frame = page.frame_locator("#lab-results-frame")

    # Check the Download PDF button is visible
    download_button = frame.get_by_role("button", name="Download PDF")
    expect(download_button).to_be_visible()

    # Click the Download PDF button and wait for the download
    with page.expect_download() as download_info:
        download_button.click()
    download = download_info.value

    # Check the suggested filename
    expected_filename = f"lab-results-{patient['mrn']}.pdf"
    assert download.suggested_filename == expected_filename
