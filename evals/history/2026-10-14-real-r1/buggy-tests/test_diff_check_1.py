import pytest
from playwright.sync_api import expect

def test_sign_in_button_accessible_name(page, base_url):
    # Go to sign-in page
    page.goto(base_url + "index.html")

    # Check the 'Sign in' button has accessible name 'Sign in'
    sign_in_button = page.get_by_role("button", name="Sign in")
    expect(sign_in_button).to_be_visible()

    # Also check that no button without accessible name exists (to catch the diff issue)
    # We find all buttons and assert each has a non-empty accessible name
    buttons = page.get_by_role("button").all()
    for button in buttons:
        # accessible name is the name argument in get_by_role, so we check that
        # the button is either the sign_in_button or has a name
        # Playwright does not expose accessible name directly, so we check by trying to get the name via aria-label or text
        # We can check the accessible name by checking the accessible name property via evaluate
        accessible_name = button.evaluate("el => el.getAttribute('aria-label') || el.textContent.trim()")
        assert accessible_name, "Button is missing accessible name"
