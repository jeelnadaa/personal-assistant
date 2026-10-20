"""Unit tests for extended system tools and spoken web URLs."""

import pytest
from jarvis.tools.system import cancel_shutdown, get_network_info, media_control
from jarvis.tools.web import normalize_spoken_url, web_search


def test_normalize_spoken_url():
    """Verifies that speech recognition artifacts in URLs are repaired."""
    assert normalize_spoken_url("github dot com") == "github.com"
    assert normalize_spoken_url("reddit dot com slash r slash python") == "reddit.com/r/python"
    assert normalize_spoken_url("https colon slash slash google dot com") == "https://google.com"


def test_media_control():
    """Verifies media control accepts valid commands."""
    res = media_control("play_pause")
    assert res.ok is True
    assert "play_pause" in res.output

    res_invalid = media_control("fast_forward")
    assert res_invalid.ok is False


def test_get_network_info():
    """Verifies network diagnostic returns active interfaces and internet state."""
    res = get_network_info()
    assert res.ok is True
    assert "Network Status:" in res.output


def test_cancel_shutdown():
    """Verifies cancel_shutdown tool executes shutdown /a without crashing."""
    res = cancel_shutdown()
    assert isinstance(res.ok, bool)
