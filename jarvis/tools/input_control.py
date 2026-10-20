"""Mouse and keyboard simulation tools using pyautogui."""

import time
import pyautogui
import pyperclip

from jarvis.logger import logger
from jarvis.tools.base import ToolResult, tool

# Ensure PyAutoGUI failsafe is enabled (moving mouse to corner raises FailSafeException)
pyautogui.FAILSAFE = True


@tool(
    name="type_text",
    description="Types text into whatever input field or window is currently focused. Uses clipboard for long or unicode text.",
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Text to type."},
            "interval": {
                "type": "number",
                "description": "Typing delay in seconds between keypresses (default: 0.02).",
                "default": 0.02,
            },
        },
        "required": ["text"],
    },
    dangerous=False,
    category="input",
)
def type_text(text: str, interval: float = 0.02) -> ToolResult:
    """Types text directly or uses clipboard paste for unicode/length."""
    try:
        # Use clipboard paste if text is long or contains non-ASCII characters
        is_ascii = all(ord(c) < 128 for c in text)
        if len(text) > 30 or not is_ascii:
            old_clip = pyperclip.paste()
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.1)
            # Restore previous clipboard after a brief moment
            try:
                pyperclip.copy(old_clip)
            except Exception:
                pass
            return ToolResult(ok=True, output=f"Pasted text ({len(text)} characters).")
        else:
            pyautogui.write(text, interval=interval)
            return ToolResult(ok=True, output=f"Typed '{text}'.")
    except Exception as e:
        logger.error("Failed to type text: %s", e)
        return ToolResult(ok=False, output=f"Failed to type: {str(e)}")


@tool(
    name="press_key",
    description="Presses a single key (e.g. 'enter', 'esc', 'tab', 'win', 'space', 'backspace', 'up', 'down').",
    input_schema={
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "Key name to press."}
        },
        "required": ["key"],
    },
    dangerous=False,
    category="input",
)
def press_key(key: str) -> ToolResult:
    """Presses and releases a single key."""
    clean_k = key.strip().lower()
    try:
        pyautogui.press(clean_k)
        return ToolResult(ok=True, output=f"Pressed key '{clean_k}'.")
    except Exception as e:
        return ToolResult(ok=False, output=f"Failed to press key '{key}': {str(e)}")


@tool(
    name="hotkey",
    description="Presses a combination of keys together (e.g. ['ctrl', 'c'], ['alt', 'tab']). Dangerous for alt+f4.",
    input_schema={
        "type": "object",
        "properties": {
            "keys": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of keys in the shortcut (e.g. ['ctrl', 's']).",
            }
        },
        "required": ["keys"],
    },
    dangerous=False,  # Dangerous status dynamically evaluated by policy.py for alt+f4
    category="input",
)
def hotkey(keys: list[str]) -> ToolResult:
    """Executes a key combo shortcut."""
    clean_keys = [k.strip().lower() for k in keys]
    try:
        pyautogui.hotkey(*clean_keys)
        return ToolResult(ok=True, output=f"Triggered hotkey combo: {' + '.join(clean_keys)}.")
    except Exception as e:
        return ToolResult(ok=False, output=f"Failed to trigger hotkey: {str(e)}")


@tool(
    name="click",
    description="Clicks at specific screen coordinates (x, y) with the specified mouse button.",
    input_schema={
        "type": "object",
        "properties": {
            "x": {"type": "integer", "description": "Horizontal pixel coordinate."},
            "y": {"type": "integer", "description": "Vertical pixel coordinate."},
            "button": {
                "type": "string",
                "enum": ["left", "right", "middle"],
                "description": "Mouse button to click (default: left).",
                "default": "left",
            },
            "clicks": {
                "type": "integer",
                "description": "Number of clicks (default: 1, 2 for double click).",
                "default": 1,
            },
        },
        "required": ["x", "y"],
    },
    dangerous=False,
    category="input",
)
def click(x: int, y: int, button: str = "left", clicks: int = 1) -> ToolResult:
    """Clicks at screen position."""
    try:
        pyautogui.click(x=x, y=y, button=button, clicks=clicks)
        return ToolResult(ok=True, output=f"Clicked at ({x}, {y}) with {button} button ({clicks} time(s)).")
    except Exception as e:
        return ToolResult(ok=False, output=f"Click failed: {str(e)}")


@tool(
    name="move_mouse",
    description="Moves the mouse pointer to screen coordinates (x, y).",
    input_schema={
        "type": "object",
        "properties": {
            "x": {"type": "integer", "description": "Target X coordinate."},
            "y": {"type": "integer", "description": "Target Y coordinate."},
        },
        "required": ["x", "y"],
    },
    dangerous=False,
    category="input",
)
def move_mouse(x: int, y: int) -> ToolResult:
    """Moves mouse cursor."""
    try:
        pyautogui.moveTo(x=x, y=y)
        return ToolResult(ok=True, output=f"Moved mouse cursor to ({x}, {y}).")
    except Exception as e:
        return ToolResult(ok=False, output=f"Move mouse failed: {str(e)}")


@tool(
    name="scroll",
    description="Scrolls the mouse wheel up (positive integer) or down (negative integer).",
    input_schema={
        "type": "object",
        "properties": {
            "amount": {"type": "integer", "description": "Scroll amount (positive=up, negative=down)."}
        },
        "required": ["amount"],
    },
    dangerous=False,
    category="input",
)
def scroll(amount: int) -> ToolResult:
    """Scrolls mouse wheel."""
    try:
        pyautogui.scroll(amount)
        direction = "up" if amount > 0 else "down"
        return ToolResult(ok=True, output=f"Scrolled {direction} by {abs(amount)} clicks.")
    except Exception as e:
        return ToolResult(ok=False, output=f"Scroll failed: {str(e)}")


@tool(
    name="drag",
    description="Drags the mouse with left button held from (x1, y1) to (x2, y2).",
    input_schema={
        "type": "object",
        "properties": {
            "x1": {"type": "integer", "description": "Start X coordinate."},
            "y1": {"type": "integer", "description": "Start Y coordinate."},
            "x2": {"type": "integer", "description": "Target X coordinate."},
            "y2": {"type": "integer", "description": "Target Y coordinate."},
        },
        "required": ["x1", "y1", "x2", "y2"],
    },
    dangerous=False,
    category="input",
)
def drag(x1: int, y1: int, x2: int, y2: int) -> ToolResult:
    """Performs mouse drag operation."""
    try:
        pyautogui.moveTo(x1, y1)
        pyautogui.dragTo(x2, y2, button="left")
        return ToolResult(ok=True, output=f"Dragged from ({x1}, {y1}) to ({x2}, {y2}).")
    except Exception as e:
        return ToolResult(ok=False, output=f"Drag failed: {str(e)}")


@tool(
    name="wait",
    description="Pauses execution for a specified number of seconds (capped at 10.0 seconds).",
    input_schema={
        "type": "object",
        "properties": {
            "seconds": {"type": "number", "description": "Seconds to wait (max 10).", "maximum": 10}
        },
        "required": ["seconds"],
    },
    dangerous=False,
    category="input",
)
def wait(seconds: float) -> ToolResult:
    """Waits for specified duration, capped at 10 seconds, responding promptly to cancellation."""
    from jarvis.brain.agent import is_task_cancelled

    duration = max(0.0, min(10.0, float(seconds)))
    start = time.perf_counter()
    while time.perf_counter() - start < duration:
        if is_task_cancelled():
            return ToolResult(ok=False, output="Wait interrupted: task was cancelled.")
        time.sleep(0.05)
    return ToolResult(ok=True, output=f"Waited {duration:.1f} second(s).")

