"""Web browsing, search, and page text extraction tools for Jarvis."""

import re
import urllib.parse
import urllib.request
import webbrowser
from jarvis.logger import logger
from jarvis.tools.base import ToolResult, tool


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
    clean_url = url.strip()
    if not (clean_url.startswith("http://") or clean_url.startswith("https://")):
        clean_url = "https://" + clean_url

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
    target_url = url.strip()
    if not (target_url.startswith("http://") or target_url.startswith("https://")):
        target_url = "https://" + target_url

    # Attempt fetching via Playwright if available
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(target_url, timeout=15000)
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
