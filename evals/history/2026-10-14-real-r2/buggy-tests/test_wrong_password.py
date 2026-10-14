import pytest
from playwright.sync_api import expect

def test_wrong_password_shows_error(page, base_url, patient):
    # Go to sign-in page
    page.goto(base_url + "index.html")

    # Check the sign-in heading is visible
    sign_in_heading = page.get_by_role("heading", name="Sign in")
    expect(sign_in_heading).to_be_visible()

    # Fill in email with patient's email
    email_input = page.get_by_role("textbox", name="Email")
    email_input.fill(patient["email"])

    # Fill in wrong password
    password_input = page.get_by_role("textbox", name="Password")
    password_input.fill("wrongpassword123")

    # Click the sign-in button
    sign_in_button = page.get_by_role("button")  # The button lost its accessible name in the release
    sign_in_button.click()

    # Expect an error message in an alert role
    error_alert = page.get_by_role("alert")
    expect(error_alert).to_be_visible()
    # The baseline error text is "Incorrect email or password. Please try again."
    expect(error_alert).to_have_text("Incorrect email or password. Please try again.")

    # The page should remain on the sign-in page
    expect(page).to_have_url(base_url + "index.html")
