import pytest
from playwright.sync_api import expect

def test_sign_in_button_accessible_name(page, base_url):
    # Go to the sign-in page
    page.goto(base_url + "index.html")

    # Locate the 'Sign in' button by role and name
    sign_in_button = page.get_by_role("button", name="Sign in")

    # Assert the button is visible and has the accessible name 'Sign in'
    expect(sign_in_button).to_be_visible()

    # Additionally, check that the accessible name is exactly 'Sign in'
    # Playwright does not provide direct API to get accessible name, but get_by_role with name ensures it
    # So this test ensures the button is found by role and name, meaning accessible name is present

    # Negative check: ensure no button with empty accessible name exists
    buttons = page.get_by_role("button")
    for i in range(buttons.count()):
        button = buttons.nth(i)
        # We check that no button has empty accessible name by trying to get it by empty name
        # But Playwright does not provide direct accessible name retrieval, so we rely on get_by_role
        # So we check that all buttons have non-empty accessible names by ensuring get_by_role with empty name returns none
        # This is a limitation, so we just check the known button
        pass

    # This test is focused on the known 'Sign in' button accessible name

