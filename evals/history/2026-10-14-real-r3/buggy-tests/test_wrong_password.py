import pytest
import re
from playwright.sync_api import expect

def test_wrong_password_shows_error(page, base_url, patient):
    # Go to sign-in page
    page.goto(base_url + "index.html")

    # Fill in email with valid patient email
    page.get_by_role("textbox", name="Email").fill(patient["email"])
    # Fill in password with wrong password
    page.get_by_role("textbox", name="Password").fill("wrongpassword")

    # Click the sign in button
    sign_in_button = page.get_by_role("button", name="Sign in")
    expect(sign_in_button).to_be_visible()
    sign_in_button.click()

    # Expect an error message in an alert role about wrong password
    alert = page.get_by_role("alert")
    expect(alert).to_be_visible()
    expect(alert).to_have_text(re.compile(r"wrong|incorrect|error", re.I))

    # Also expect to remain on the sign-in page
    expect(page).to_have_url(base_url + "index.html")
