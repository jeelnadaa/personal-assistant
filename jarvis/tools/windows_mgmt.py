"""Window management tools for listing, focusing, minimizing, maximizing, and snapping windows on Windows 11."""

from typing import Any
import psutil

try:
    import win32api
    import win32con
    import win32gui
    import win32process
except ImportError:
    win32api = None
    win32con = None
    win32gui = None
    win32process = None

from jarvis.logger import logger
from jarvis.tools.base import ToolResult, tool


def _find_window_by_title(title_contains: str) -> tuple[int, str] | None:
    """Finds the best matching visible top-level window handle by title substring."""
    if not win32gui:
        return None

    clean_target = title_contains.strip().lower()
    matches: list[tuple[int, str]] = []

    def enum_cb(hwnd: int, extra: Any) -> None:
        if win32gui.IsWindowVisible(hwnd):
            text = win32gui.GetWindowText(hwnd).strip()
            if text and clean_target in text.lower():
                matches.append((hwnd, text))

    win32gui.EnumWindows(enum_cb, None)
    if not matches:
        return None

    # Return shortest title match as likely most specific
    matches.sort(key=lambda item: len(item[1]))
    return matches[0]


@tool(
    name="list_windows",
    description="Returns titles and handle IDs of all visible windows currently open on the desktop.",
    input_schema={"type": "object", "properties": {}},
    dangerous=False,
    category="windows_mgmt",
)
def list_windows() -> ToolResult:
    """Lists all visible top-level windows with their handles."""
    if not win32gui:
        return ToolResult(ok=False, output="win32gui is not available.")

    results: list[str] = []

    def enum_cb(hwnd: int, extra: Any) -> None:
        if win32gui.IsWindowVisible(hwnd):
            text = win32gui.GetWindowText(hwnd).strip()
            if text and text not in ("Program Manager", "Default IME", "MSCTFIME UI"):
                results.append(f"HWND {hwnd}: {text}")

    win32gui.EnumWindows(enum_cb, None)
    if not results:
        return ToolResult(ok=True, output="No visible windows found.")

    return ToolResult(ok=True, output="Visible windows:\n" + "\n".join(results[:30]))


@tool(
    name="focus_window",
    description="Brings a window matching the title substring to the foreground and restores it if minimized.",
    input_schema={
        "type": "object",
        "properties": {
            "title_contains": {
                "type": "string",
                "description": "Substring of the window title to match.",
            }
        },
        "required": ["title_contains"],
    },
    dangerous=False,
    category="windows_mgmt",
)
def focus_window(title_contains: str) -> ToolResult:
    """Focuses and restores the matching window."""
    if not win32gui or not win32con:
        return ToolResult(ok=False, output="win32gui is not available.")

    match = _find_window_by_title(title_contains)
    if not match:
        return ToolResult(ok=False, output=f"No window found matching '{title_contains}'.")

    hwnd, title = match
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        return ToolResult(ok=True, output=f"Focused window: '{title}' (HWND {hwnd}).")
    except Exception as e:
        logger.warning("SetForegroundWindow fallback needed for hwnd %d: %s", hwnd, e)
        try:
            # Force focus via thread attachment if standard focus was prevented by Windows
            cur_tid = win32api.GetCurrentThreadId()
            target_tid, _ = win32process.GetWindowThreadProcessId(hwnd)
            win32process.AttachThreadInput(cur_tid, target_tid, True)
            win32gui.SetForegroundWindow(hwnd)
            win32process.AttachThreadInput(cur_tid, target_tid, False)
            return ToolResult(ok=True, output=f"Focused window: '{title}'.")
        except Exception as e2:
            return ToolResult(ok=False, output=f"Could not focus '{title}': {str(e2)}")


@tool(
    name="minimize_window",
    description="Minimizes a visible window matching the title substring.",
    input_schema={
        "type": "object",
        "properties": {
            "title_contains": {
                "type": "string",
                "description": "Substring of the window title to minimize.",
            }
        },
        "required": ["title_contains"],
    },
    dangerous=False,
    category="windows_mgmt",
)
def minimize_window(title_contains: str) -> ToolResult:
    """Minimizes the specified window."""
    if not win32gui or not win32con:
        return ToolResult(ok=False, output="win32gui is not available.")

    match = _find_window_by_title(title_contains)
    if not match:
        return ToolResult(ok=False, output=f"No window found matching '{title_contains}'.")

    hwnd, title = match
    win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
    return ToolResult(ok=True, output=f"Minimized window: '{title}'.")


@tool(
    name="maximize_window",
    description="Maximizes a visible window matching the title substring.",
    input_schema={
        "type": "object",
        "properties": {
            "title_contains": {
                "type": "string",
                "description": "Substring of the window title to maximize.",
            }
        },
        "required": ["title_contains"],
    },
    dangerous=False,
    category="windows_mgmt",
)
def maximize_window(title_contains: str) -> ToolResult:
    """Maximizes the specified window."""
    if not win32gui or not win32con:
        return ToolResult(ok=False, output="win32gui is not available.")

    match = _find_window_by_title(title_contains)
    if not match:
        return ToolResult(ok=False, output=f"No window found matching '{title_contains}'.")

    hwnd, title = match
    win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
    return ToolResult(ok=True, output=f"Maximized window: '{title}'.")


@tool(
    name="snap_window",
    description="Snaps a window to 'left', 'right', or 'fullscreen' across the primary workspace area.",
    input_schema={
        "type": "object",
        "properties": {
            "title_contains": {
                "type": "string",
                "description": "Substring of the window title to snap.",
            },
            "position": {
                "type": "string",
                "enum": ["left", "right", "fullscreen"],
                "description": "Target snap position: 'left', 'right', or 'fullscreen'.",
            },
        },
        "required": ["title_contains", "position"],
    },
    dangerous=False,
    category="windows_mgmt",
)
def snap_window(title_contains: str, position: str) -> ToolResult:
    """Positions a window to half the monitor (left/right) or maximizes it."""
    if not win32gui or not win32con or not win32api:
        return ToolResult(ok=False, output="win32 functions are not available.")

    match = _find_window_by_title(title_contains)
    if not match:
        return ToolResult(ok=False, output=f"No window found matching '{title_contains}'.")

    hwnd, title = match
    pos = position.strip().lower()

    if pos == "fullscreen":
        win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
        return ToolResult(ok=True, output=f"Snapped '{title}' to fullscreen.")

    # Get work area of current monitor
    try:
        monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
        info = win32api.GetMonitorInfo(monitor)
        work_area = info["Work"]  # (left, top, right, bottom)
        w_left, w_top, w_right, w_bottom = work_area
        total_w = w_right - w_left
        total_h = w_bottom - w_top
        half_w = total_w // 2

        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

        if pos == "left":
            win32gui.MoveWindow(hwnd, w_left, w_top, half_w, total_h, True)
            return ToolResult(ok=True, output=f"Snapped '{title}' to the left half of the screen.")
        elif pos == "right":
            win32gui.MoveWindow(hwnd, w_left + half_w, w_top, half_w, total_h, True)
            return ToolResult(ok=True, output=f"Snapped '{title}' to the right half of the screen.")
        else:
            return ToolResult(ok=False, output=f"Invalid position '{position}'. Must be left, right, or fullscreen.")
    except Exception as e:
        logger.error("Failed to snap window %s: %s", title, e)
        return ToolResult(ok=False, output=f"Failed to snap window: {str(e)}")


@tool(
    name="get_active_window",
    description="Returns the title and process name of the current active foreground window.",
    input_schema={"type": "object", "properties": {}},
    dangerous=False,
    category="windows_mgmt",
)
def get_active_window() -> ToolResult:
    """Returns foreground window title and process name."""
    if not win32gui:
        return ToolResult(ok=False, output="win32gui is not available.")

    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return ToolResult(ok=True, output="No foreground window (desktop).")

        title = win32gui.GetWindowText(hwnd).strip()
        proc_name = "unknown"
        if win32process:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            try:
                proc = psutil.Process(pid)
                proc_name = proc.name()
            except Exception:
                pass

        return ToolResult(ok=True, output=f"Active Window: '{title}' (Process: {proc_name}, HWND: {hwnd})")
    except Exception as e:
        return ToolResult(ok=False, output=f"Error reading active window: {str(e)}")
