import pytest
from playwright.sync_api import expect

def test_dashboard_upcoming_appointments_heading(signed_in, page):
    # The test verifies that the dashboard page contains the 'Upcoming appointments' heading
    # This is a diff check test to detect regressions in the UI

    # The user is already signed in and on the dashboard page
    # Check for the heading 'Upcoming appointments'
    heading = page.get_by_role("heading", name="Upcoming appointments")
    expect(heading).to_be_visible()  # Wait and assert the heading is visible
