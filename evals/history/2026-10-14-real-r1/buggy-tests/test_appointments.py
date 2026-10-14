import pytest
from playwright.sync_api import expect

def test_appointments_headings_and_list(signed_in, page, patient):
    # The page is already on the dashboard due to signed_in fixture
    # Check for the heading 'Welcome, Jordan Rivera'
    welcome_heading = page.get_by_role("heading", name="Welcome, Jordan Rivera")
    expect(welcome_heading).to_be_visible()

    # Check for the heading 'Upcoming appointments'
    upcoming_heading = page.get_by_role("heading", name="Upcoming appointments")
    expect(upcoming_heading).to_be_visible()

    # Check the appointments list
    # The patient dict has appointments list, check that the page shows them
    # We assume appointments are shown as list items or text containing appointment info
    # We check that the count of appointments shown matches patient['appointments'] count
    # We find all elements that contain appointment text
    # We use to_have_count and to_have_text

    # Let's find all elements that contain appointment text, assuming they are in a list or container
    # We try to find all elements that contain any of the appointment texts
    # For simplicity, we check that the container has the text of all appointments

    # The container is the section under 'Upcoming appointments' heading
    # We find the heading, then find the next sibling or parent container

    # Simplify: check that the page contains text of each appointment
    for appt in patient['appointments']:
        expect(page.get_by_text(appt)).to_be_visible()

    # Also check the count of appointments shown matches
    # We find all elements that contain appointment text
    # We assume each appointment is in a list item
    # So we find all list items under the 'Upcoming appointments' section
    # Let's find the section by heading
    upcoming_section = page.get_by_role("heading", name="Upcoming appointments").locator("xpath=..")
    # Find list items under this section
    list_items = upcoming_section.locator("li")
    expect(list_items).to_have_count(len(patient['appointments']))
