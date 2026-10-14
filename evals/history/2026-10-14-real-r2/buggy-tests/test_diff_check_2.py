import pytest
from playwright.sync_api import expect

def test_upcoming_appointments_heading(signed_in, page):
    # Verify that the 'Upcoming appointments' heading is present on the dashboard page
    heading = page.get_by_role("heading", name="Upcoming appointments")
    expect(heading).to_be_visible()  # Baseline expects this heading to be present
