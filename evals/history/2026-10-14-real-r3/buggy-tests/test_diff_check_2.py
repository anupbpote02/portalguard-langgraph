import pytest
from playwright.sync_api import expect

# This test checks that the baseline headings "Upcoming appointments" on the dashboard main page
# and "Lab results" inside the lab results frame are still present.
# According to the snapshot diff, these headings were removed in the release, so this test
# will fail if the release removed them, which is expected for diff_check.

def test_diff_check_headings(signed_in, page):
    # Check the "Upcoming appointments" heading on the dashboard main page
    upcoming_appointments_heading = page.get_by_role("heading", name="Upcoming appointments")
    expect(upcoming_appointments_heading).to_be_visible()

    # Check the "Lab results" heading inside the lab results iframe
    lab_results_frame = page.frame_locator("#lab-results-frame")
    lab_results_heading = lab_results_frame.get_by_role("heading", name="Lab results")
    expect(lab_results_heading).to_be_visible()
