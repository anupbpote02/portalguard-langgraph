"""pytest plugin for agent-written tests (loaded with `-p portalguard.fixtures`). Written by humans.

Generated tests live in runs/<id>/tests/, and write_test only accepts test_*.py, so the agent can't
replace these fixtures or the localhost route guard.
"""

from urllib.parse import urlparse

import pytest
from playwright.sync_api import expect

from portalguard.browser import load_test_users
from portalguard.config import ALLOWED_HOSTS

TIMEOUT_MS = 5_000  # a missing element should cost seconds, not the 30s default
expect.set_options(timeout=TIMEOUT_MS)


@pytest.fixture
def patient() -> dict:
    """The default synthetic test user (Jordan Rivera, TEST-000123)."""
    return load_test_users()[0]


@pytest.fixture
def patients() -> list[dict]:
    return load_test_users()


@pytest.fixture
def signed_in(page, base_url, patient):
    """A page already on the dashboard. Signs in by label + Enter (not the button), so tests using it
    don't fail because of a sign-in button bug they aren't testing."""
    page.goto(base_url + "index.html")
    page.get_by_label("Email").fill(patient["email"])
    page.get_by_label("Password").fill(patient["password"])
    page.get_by_label("Password").press("Enter")
    page.wait_for_url("**/dashboard.html")
    return page


@pytest.fixture(autouse=True)
def localhost_only(context):
    """URL allowlist inside the browser: any non-localhost request is aborted."""
    def guard(route):
        if urlparse(route.request.url).hostname in ALLOWED_HOSTS:
            route.continue_()
        else:
            route.abort("blockedbyclient")

    context.route("**/*", guard)
    context.set_default_timeout(TIMEOUT_MS)
    yield
