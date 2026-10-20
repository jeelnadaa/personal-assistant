"""Unit tests for Playwright browser automation tools."""

import pytest
from jarvis.tools.web import (
    browser_click,
    browser_close,
    browser_get_page_text,
    browser_open,
    browser_read,
    browser_type,
    open_url,
    web_search,
)


def test_browser_full_automation_flow():
    """Verifies opening, reading, clicking, typing, and closing Playwright browser."""
    # 1. Open test page with data URL
    html_content = (
        "data:text/html,<!DOCTYPE html><html><head><title>Jarvis Test Page</title></head>"
        "<body><h1>Playwright Automation</h1>"
        "<input id='username' placeholder='Enter Name' />"
        "<button id='submit-btn'>Click Me</button>"
        "<div id='result'></div>"
        "<script>document.getElementById('submit-btn').onclick = function() { document.getElementById('result').innerText = 'Button Clicked'; }</script>"
        "</body></html>"
    )

    open_res = browser_open(html_content)
    assert open_res.ok is True
    assert "Jarvis Test Page" in open_res.output

    # 2. Read content
    read_res = browser_read()
    assert read_res.ok is True
    assert "Playwright Automation" in read_res.output

    # 3. Type text into input
    type_res = browser_type("#username", "JarvisUser")
    assert type_res.ok is True

    # 4. Click button by text
    click_res = browser_click("Click Me")
    assert click_res.ok is True

    # Verify DOM update
    read_res2 = browser_read()
    assert "Button Clicked" in read_res2.output

    # 5. Close browser
    close_res = browser_close()
    assert close_res.ok is True
