"""Web browsing and search tools for Jarvis."""

import urllib.parse
import webbrowser
from jarvis.tools.base import tool, ToolResult
from jarvis.logger import logger


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
