import pytest
from playwright.sync_api import expect

def test_upcoming_appointments_and_list(signed_in, patient, page):
    # The signed_in fixture ensures we are on the dashboard page
    # Check that the heading 'Upcoming appointments' is visible on the dashboard
    heading = page.get_by_role("heading", name="Upcoming appointments")
    expect(heading).to_be_visible()

    # Check that the appointments list contains the patient's appointments
    # We expect the appointments to be visible as text on the page
    for appointment in patient["appointments"]:
        expect(page.get_by_text(appointment)).to_be_visible()

    # Also check the count of appointments on the page matches the patient's appointments count
    # We assume each appointment is shown as a list item or similar
    # We find all elements that contain any of the appointment texts and count them
    # This is a heuristic since no exact role or container is given
    # We use a locator that matches any appointment text
    # If no appointments, count should be zero
    if patient["appointments"]:
        # Create a locator that matches any appointment text
        # We join with | for regex OR
        import re
        pattern = "|".join(re.escape(a) for a in patient["appointments"])
        appointments_locator = page.locator(f"text=/{pattern}/")
        expect(appointments_locator).to_have_count(len(patient["appointments"]))
    else:
        # No appointments expected, check no appointment text is visible
        # We check that no element with text matching any appointment is visible
        # Since no appointments, this is trivially true
        pass
