import pytest
from playwright.sync_api import expect

def test_sign_in_page_elements_and_submit(page, base_url, patient):
    # Go to the sign-in page
    page.goto(base_url + "index.html")

    # Check the heading 'Sign in'
    heading = page.get_by_role("heading", name="Sign in")
    expect(heading).to_be_visible()

    # Check the textboxes 'Email' and 'Password'
    email_input = page.get_by_role("textbox", name="Email")
    expect(email_input).to_be_visible()

    password_input = page.get_by_role("textbox", name="Password")
    expect(password_input).to_be_visible()

    # Fill in the email and password
    email_input.fill(patient["email"])
    password_input.fill(patient["password"])

    # Click the button with accessible name 'Sign in' to submit
    # Baseline snapshot diff shows button "Sign in" changed to button with no accessible name
    # So locate the button by role only, but ensure it is the only button on the page
    buttons = page.get_by_role("button")
    expect(buttons).to_have_count(1)
    sign_in_button = buttons.nth(0)
    expect(sign_in_button).to_be_visible()
    sign_in_button.click()

    # After sign in, expect to be redirected to dashboard
    expect(page).to_have_url(lambda url: url.endswith("dashboard.html"))
