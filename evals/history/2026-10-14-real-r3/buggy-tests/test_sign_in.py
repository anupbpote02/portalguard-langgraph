import pytest
from playwright.sync_api import expect

def test_sign_in_journey(page, base_url, patient):
    # Go to the sign-in page
    page.goto(base_url + "index.html")

    # Check the heading 'Sign in' is visible
    heading = page.get_by_role("heading", name="Sign in")
    expect(heading).to_be_visible()

    # Fill in email and password
    page.get_by_label("Email").fill(patient["email"])
    page.get_by_label("Password").fill(patient["password"])

    # Click the 'Sign in' button to submit the form
    sign_in_button = page.get_by_role("button", name="Sign in")
    expect(sign_in_button).to_be_visible()
    sign_in_button.click()

    # Expect to be redirected to the dashboard
    expect(page).to_have_url(base_url + "dashboard.html")
