import pytest
from playwright.sync_api import expect

def test_wrong_password_shows_error_and_signin_button_accessible(page, base_url, patient):
    # Go to sign-in page
    page.goto(base_url + "index.html")

    # Check the heading "Sign in" is visible
    sign_in_heading = page.get_by_role("heading", name="Sign in")
    expect(sign_in_heading).to_be_visible()

    # Fill in email with patient's email
    email_input = page.get_by_role("textbox", name="Email")
    email_input.fill(patient["email"])

    # Fill in password with a wrong password
    password_input = page.get_by_role("textbox", name="Password")
    password_input.fill("wrongpassword123")

    # Click the "Sign in" button
    sign_in_button = page.get_by_role("button", name="Sign in")
    sign_in_button.click()

    # Expect an error message alert to appear
    error_alert = page.get_by_role("alert")
    expect(error_alert).to_be_visible()

    # Check the sign-in button is still visible and enabled
    expect(sign_in_button).to_be_visible()
    expect(sign_in_button).to_be_enabled()

    # Optionally, check the URL remains on the sign-in page
    expect(page).to_have_url(base_url + "index.html")
