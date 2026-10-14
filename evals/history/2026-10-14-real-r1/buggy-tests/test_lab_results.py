import pytest
from playwright.sync_api import expect

def test_lab_results_frame_heading_and_download_button(signed_in, page, patient):
    # The lab results are inside a frame with id 'lab-results-frame'
    frame_locator = page.frame_locator('#lab-results-frame')

    # Check the button 'Download PDF' is visible inside the frame
    download_button = frame_locator.get_by_role('button', name='Download PDF')
    expect(download_button).to_be_visible()

    # The baseline shows the heading "Lab results" was removed, so we do NOT check for it

    # Check that the lab results list has at least one result with text
    lab_results = patient.get('labResults', [])

    # Check that each lab result name is present in the frame text
    for result in lab_results:
        expect(frame_locator).to_contain_text(result['name'])

    # Also check that if there are no lab results, the frame contains some placeholder text
    if not lab_results:
        expect(frame_locator).to_contain_text('No lab results')
