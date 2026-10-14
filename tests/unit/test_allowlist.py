"""Safety rule: the agent may only open localhost URLs."""

import pytest

from portalguard.safety import check_url
from portalguard.tools import snapshot_page


@pytest.mark.parametrize("url", ["http://localhost:8000/good/", "http://127.0.0.1:8000/buggy/index.html"])
def test_localhost_allowed(url):
    check_url(url)


@pytest.mark.parametrize("url", [
    "https://example.com/",
    "http://localhost.evil.com:8000/good/",   # look-alike host
    "http://169.254.169.254/latest/meta-data/",  # cloud metadata
    "file:///C:/Windows/win.ini",
    "javascript:alert(1)",
])
def test_everything_else_blocked(url):
    with pytest.raises(ValueError, match="localhost only"):
        check_url(url)


def test_snapshot_tool_refuses_before_opening_a_browser(tmp_path):
    with pytest.raises(ValueError, match="localhost only"):
        snapshot_page.invoke({"url": "https://example.com/", "label": "x", "snapshot_dir": str(tmp_path)})
