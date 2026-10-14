import pytest
from playwright.sync_api import expect

def test_sign_in_button_accessible_name(page, base_url):
    # Go to the sign-in page
    page.goto(base_url + "index.html")

    # Check the 'Sign in' button has the accessible name 'Sign in'
    sign_in_button = page.get_by_role("button", name="Sign in")
    expect(sign_in_button).to_be_visible()

    # Also check that there is no button without accessible name (to catch the changed diff)
    # We find all buttons and assert none has empty accessible name
    buttons = page.get_by_role("button")
    for i in range(buttons.count()):
        button = buttons.nth(i)
        # The accessible name is the name argument in get_by_role, so we check text content
        # But Playwright does not expose accessible name directly, so we check text content
        # We expect the 'Sign in' button to have text 'Sign in'
        text = button.text_content()
        assert text and text.strip() != "", "Found a button with no accessible name or empty text"

    # Check the heading 'Sign in' is present
    heading = page.get_by_role("heading", name="Sign in")
    expect(heading).to_be_visible()
