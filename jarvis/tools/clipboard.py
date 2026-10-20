"""Clipboard reading and writing tools using pyperclip."""

import pyperclip
from jarvis.tools.base import ToolResult, tool


@tool(
    name="get_clipboard",
    description="Returns the current text contents of the Windows clipboard.",
    input_schema={"type": "object", "properties": {}},
    dangerous=False,
    category="clipboard",
)
def get_clipboard() -> ToolResult:
    """Reads current clipboard text."""
    try:
        text = pyperclip.paste()
        if not text:
            return ToolResult(ok=True, output="Clipboard is empty.")
        preview = text[:500] + ("..." if len(text) > 500 else "")
        return ToolResult(ok=True, output=f"Clipboard contents: {preview}")
    except Exception as e:
        return ToolResult(ok=False, output=f"Failed to read clipboard: {str(e)}")


@tool(
    name="set_clipboard",
    description="Copies the provided text into the Windows clipboard.",
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Text to copy to the clipboard."}
        },
        "required": ["text"],
    },
    dangerous=False,
    category="clipboard",
)
def set_clipboard(text: str) -> ToolResult:
    """Sets clipboard text."""
    try:
        pyperclip.copy(text)
        return ToolResult(ok=True, output=f"Copied {len(text)} characters to the clipboard.")
    except Exception as e:
        return ToolResult(ok=False, output=f"Failed to set clipboard: {str(e)}")
