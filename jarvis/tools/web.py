"""Web browsing, search, and Playwright persistent browser automation tools for Jarvis."""

from pathlib import Path
import re
import urllib.parse
import urllib.request
import webbrowser
from typing import Any

from jarvis.logger import logger
from jarvis.tools.base import ToolResult, tool

BROWSER_PROFILE_DIR = Path("data/browser_profile")


def _normalize_url(url: str) -> str:
    """Ensures URL has a valid scheme, defaulting to https:// if none specified."""
    clean = url.strip()
    schemes = ("http://", "https://", "file://", "data:", "about:")
    if not any(clean.startswith(s) for s in schemes):
        clean = "https://" + clean
    return clean


class PersistentBrowserSession:
    """Manages a persistent Playwright Chromium browser session preserving cookies and state."""

    def __init__(self) -> None:
        self.pw: Any = None
        self.context: Any = None
        self.page: Any = None

    def _ensure_page(self) -> Any:
        """Initializes or restores the persistent browser context and page."""
        if self.context is None or self.page is None or self.page.is_closed():
            from playwright.sync_api import sync_playwright

            BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            self.pw = sync_playwright().start()

            try:
                # Try launching headed first so the user can see navigation
                self.context = self.pw.chromium.launch_persistent_context(
                    user_data_dir=str(BROWSER_PROFILE_DIR),
                    headless=False,
                    viewport={"width": 1280, "height": 800},
                    args=["--disable-blink-features=AutomationControlled"],
                )
            except Exception as e:
                logger.info("Headed browser launch unavailable, falling back to headless: %s", e)
                self.context = self.pw.chromium.launch_persistent_context(
                    user_data_dir=str(BROWSER_PROFILE_DIR),
                    headless=True,
                    viewport={"width": 1280, "height": 800},
                )

            if len(self.context.pages) > 0:
                self.page = self.context.pages[0]
            else:
                self.page = self.context.new_page()

        return self.page

    def open(self, url: str) -> ToolResult:
        """Navigates to the specified URL."""
        clean_url = _normalize_url(url)

        try:
            page = self._ensure_page()
            page.goto(clean_url, timeout=25000, wait_until="domcontentloaded")
            title = page.title()
            return ToolResult(
                ok=True,
                output=f"Navigated to '{clean_url}'. Page title: '{title}'.",
            )
        except Exception as e:
            logger.error("Persistent browser navigation to '%s' failed: %s", clean_url, e)
            return ToolResult(ok=False, output=f"Failed to navigate to '{url}': {str(e)}")

    def click(self, text_or_selector: str) -> ToolResult:
        """Clicks an element by text, selector, or button role."""
        if self.page is None or self.page.is_closed():
            return ToolResult(ok=False, output="No browser page is currently open. Call browser_open first.")

        target = text_or_selector.strip()
        try:
            # 1. Try exact or partial text locator
            text_loc = self.page.get_by_text(target).first
            if text_loc.count() > 0:
                text_loc.click(timeout=5000)
                return ToolResult(ok=True, output=f"Clicked element with text '{target}'. Current URL: {self.page.url}")

            # 2. Try role button or link
            btn_loc = self.page.get_by_role("button", name=target).first
            if btn_loc.count() > 0:
                btn_loc.click(timeout=5000)
                return ToolResult(ok=True, output=f"Clicked button '{target}'. Current URL: {self.page.url}")

            link_loc = self.page.get_by_role("link", name=target).first
            if link_loc.count() > 0:
                link_loc.click(timeout=5000)
                return ToolResult(ok=True, output=f"Clicked link '{target}'. Current URL: {self.page.url}")

            # 3. Try standard CSS / XPath selector
            self.page.locator(target).first.click(timeout=5000)
            return ToolResult(ok=True, output=f"Clicked selector '{target}'. Current URL: {self.page.url}")

        except Exception as e:
            logger.warning("Browser click failed for '%s': %s", target, e)
            return ToolResult(ok=False, output=f"Failed to click '{target}': {str(e)}")

    def type_text(self, selector: str, text: str) -> ToolResult:
        """Fills text into an input field matching the selector."""
        if self.page is None or self.page.is_closed():
            return ToolResult(ok=False, output="No browser page is currently open. Call browser_open first.")

        sel = selector.strip()
        try:
            loc = self.page.locator(sel).first
            loc.fill(text, timeout=5000)
            return ToolResult(ok=True, output=f"Typed text into '{sel}'.")
        except Exception as e:
            # Fallback to get_by_placeholder or get_by_label
            try:
                self.page.get_by_placeholder(sel).first.fill(text, timeout=4000)
                return ToolResult(ok=True, output=f"Typed text into placeholder '{sel}'.")
            except Exception:
                logger.warning("Browser type failed for '%s': %s", sel, e)
                return ToolResult(ok=False, output=f"Failed to type into '{sel}': {str(e)}")

    def read(self) -> ToolResult:
        """Reads visible text from the currently open page."""
        if self.page is None or self.page.is_closed():
            return ToolResult(ok=False, output="No browser page is currently open. Call browser_open first.")

        try:
            title = self.page.title()
            url = self.page.url
            raw_text = self.page.inner_text("body")
            clean_text = " ".join(raw_text.split())
            if len(clean_text) > 4000:
                clean_text = clean_text[:3997] + "..."

            output = f"Page Title: {title}\nURL: {url}\n\nVisible Content:\n{clean_text}"
            return ToolResult(ok=True, output=output)
        except Exception as e:
            logger.error("Browser read failed: %s", e)
            return ToolResult(ok=False, output=f"Failed to read page content: {str(e)}")

    def close(self) -> ToolResult:
        """Closes browser context and stops Playwright."""
        try:
            if self.context:
                self.context.close()
            if self.pw:
                self.pw.stop()
            self.context = None
            self.page = None
            self.pw = None
            return ToolResult(ok=True, output="Persistent browser session closed successfully.")
        except Exception as e:
            logger.error("Error closing browser session: %s", e)
            return ToolResult(ok=False, output=f"Error closing browser: {str(e)}")


_BROWSER_SESSION = PersistentBrowserSession()


# =========================================================================
# Standalone & Default Browser Tools
# =========================================================================

@tool(
    name="open_url",
    description="Opens a web URL in the user's default browser (e.g. 'https://www.google.com').",
    input_schema={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Full URL including https:// or http:// protocol.",
            }
        },
        "required": ["url"],
    },
    dangerous=False,
    category="web",
)
def open_url(url: str) -> ToolResult:
    """Opens a URL in the default web browser."""
    clean_url = _normalize_url(url)

    try:
        webbrowser.open(clean_url)
        return ToolResult(ok=True, output=f"Opened URL in default browser: {clean_url}")
    except Exception as e:
        logger.error("Failed to open URL '%s': %s", url, e)
        return ToolResult(ok=False, output=f"Failed to open URL '{url}': {str(e)}")


@tool(
    name="web_search",
    description="Performs a Google search in the default web browser for the given query.",
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search term or query string to search for.",
            }
        },
        "required": ["query"],
    },
    dangerous=False,
    category="web",
)
def web_search(query: str) -> ToolResult:
    """Opens default browser with Google search results for query."""
    encoded = urllib.parse.quote_plus(query.strip())
    search_url = f"https://www.google.com/search?q={encoded}"
    try:
        webbrowser.open(search_url)
        return ToolResult(ok=True, output=f"Opened Google search for '{query}'.")
    except Exception as e:
        logger.error("Failed to execute web search for '%s': %s", query, e)
        return ToolResult(ok=False, output=f"Failed to execute web search: {str(e)}")


@tool(
    name="browser_get_page_text",
    description="Fetches a web page and extracts visible text content (cleaned, maximum 4000 characters).",
    input_schema={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Target webpage URL to read.",
            }
        },
        "required": ["url"],
    },
    dangerous=False,
    category="web",
)
def browser_get_page_text(url: str) -> ToolResult:
    """Fetches webpage and cleans HTML into readable text."""
    target_url = _normalize_url(url)

    # Attempt fetching via Playwright if available
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(target_url, timeout=15000, wait_until="domcontentloaded")
            text = page.inner_text("body")
            browser.close()

            clean_text = " ".join(text.split())
            if len(clean_text) > 4000:
                clean_text = clean_text[:3997] + "..."
            return ToolResult(ok=True, output=clean_text)
    except Exception as pw_err:
        logger.info("Playwright page fetch fallback to urllib: %s", pw_err)

    # Standard library fallback
    try:
        req = urllib.request.Request(
            target_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Jarvis/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        # Strip scripts and styles
        html = re.sub(r"<(script|style).*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
        # Strip all HTML tags
        text = re.sub(r"<[^>]+>", " ", html)
        clean_text = " ".join(text.split())
        if len(clean_text) > 4000:
            clean_text = clean_text[:3997] + "..."
        return ToolResult(ok=True, output=clean_text if clean_text else "Page contained no visible text.")
    except Exception as e:
        logger.error("Failed to read webpage '%s': %s", target_url, e)
        return ToolResult(ok=False, output=f"Failed to fetch webpage text: {str(e)}")


# =========================================================================
# Playwright Persistent Browser Automation Tools
# =========================================================================

@tool(
    name="browser_open",
    description="Opens a persistent Chromium browser window and navigates to the specified URL.",
    input_schema={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Web URL to open in the automated browser.",
            }
        },
        "required": ["url"],
    },
    dangerous=False,
    category="web",
)
def browser_open(url: str) -> ToolResult:
    """Opens a persistent browser session and navigates to url."""
    return _BROWSER_SESSION.open(url)


@tool(
    name="browser_click",
    description="Clicks a button, link, or element on the active browser page by its visible text or CSS selector.",
    input_schema={
        "type": "object",
        "properties": {
            "text_or_selector": {
                "type": "string",
                "description": "Visible button/link text or CSS selector to click.",
            }
        },
        "required": ["text_or_selector"],
    },
    dangerous=False,
    category="web",
)
def browser_click(text_or_selector: str) -> ToolResult:
    """Clicks element on the active browser page."""
    return _BROWSER_SESSION.click(text_or_selector)


@tool(
    name="browser_type",
    description="Types text into an input field or text area matching the selector on the active browser page.",
    input_schema={
        "type": "object",
        "properties": {
            "selector": {
                "type": "string",
                "description": "CSS selector, input name, or placeholder of the target input element.",
            },
            "text": {
                "type": "string",
                "description": "Text to type into the input element.",
            },
        },
        "required": ["selector", "text"],
    },
    dangerous=False,
    category="web",
)
def browser_type(selector: str, text: str) -> ToolResult:
    """Types text into an input field on the active browser page."""
    return _BROWSER_SESSION.type_text(selector, text)


@tool(
    name="browser_read",
    description="Reads and extracts all visible text content from the currently open browser page (up to 4000 characters).",
    input_schema={"type": "object", "properties": {}},
    dangerous=False,
    category="web",
)
def browser_read() -> ToolResult:
    """Reads visible text from the active browser page."""
    return _BROWSER_SESSION.read()


@tool(
    name="browser_close",
    description="Closes the active persistent browser session and window.",
    input_schema={"type": "object", "properties": {}},
    dangerous=False,
    category="web",
)
def browser_close() -> ToolResult:
    """Closes the persistent browser session."""
    return _BROWSER_SESSION.close()
