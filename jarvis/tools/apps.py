"""Application launching, management, and window inspection tools for Windows 11."""

from pathlib import Path
import os
import difflib
import subprocess
import time
from typing import Any
import psutil

try:
    import win32gui
    import win32process
    import win32con
except ImportError:
    win32gui = None
    win32process = None
    win32con = None

from jarvis.tools.base import tool, ToolResult
from jarvis.logger import logger

APP_ALIASES: dict[str, str] = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "edge": "msedge.exe",
    "microsoft edge": "msedge.exe",
    "spotify": "spotify:",
    "vscode": "code.cmd",
    "code": "code.cmd",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "word": "winword.exe",
    "excel": "excel.exe",
    "powerpoint": "powerpnt.exe",
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "terminal": "wt.exe",
    "windows terminal": "wt.exe",
    "settings": "ms-settings:",
    "task manager": "taskmgr.exe",
    "paint": "mspaint.exe",
}

SAFE_CLOSE_APPS = {
    "notepad",
    "calculator",
    "calc",
    "paint",
    "explorer",
    "cmd",
}


def _get_start_menu_shortcuts() -> dict[str, Path]:
    """Collects all .lnk shortcut paths from system and user Start Menu folders."""
    shortcuts: dict[str, Path] = {}
    search_dirs = []

    program_data = os.environ.get("ProgramData")
    if program_data:
        search_dirs.append(Path(program_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs")

    app_data = os.environ.get("APPDATA")
    if app_data:
        search_dirs.append(Path(app_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs")

    for s_dir in search_dirs:
        if s_dir.exists():
            for p in s_dir.rglob("*.lnk"):
                name = p.stem.lower()
                shortcuts[name] = p
    return shortcuts


@tool(
    name="open_app",
    description=(
        "Opens an application by its friendly name (e.g. 'notepad', 'chrome', 'calculator', 'spotify'). "
        "Prefer this over manual clicking. Returns confirmation and the method used to launch."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Friendly name of the application to launch (e.g., 'notepad', 'chrome', 'spotify').",
            }
        },
        "required": ["name"],
    },
    dangerous=False,
    category="apps",
)
def open_app(name: str) -> ToolResult:
    """Launches an application using alias mapping, Start Menu search, or os.startfile."""
    clean_name = name.strip().lower()

    # Strategy (a): Built-in alias map
    if clean_name in APP_ALIASES:
        target = APP_ALIASES[clean_name]
        try:
            os.startfile(target)
            return ToolResult(ok=True, output=f"Launched '{name}' via alias mapping ({target}).")
        except Exception as e:
            logger.warning("Alias launch failed for %s (%s): %s", clean_name, target, e)

    # Strategy (b): Start Menu shortcut fuzzy match
    shortcuts = _get_start_menu_shortcuts()
    if shortcuts:
        matches = difflib.get_close_matches(clean_name, list(shortcuts.keys()), n=1, cutoff=0.5)
        if matches:
            matched_name = matches[0]
            shortcut_path = shortcuts[matched_name]
            try:
                os.startfile(str(shortcut_path))
                return ToolResult(
                    ok=True,
                    output=f"Launched '{name}' via Start Menu shortcut match: {shortcut_path.name}.",
                )
            except Exception as e:
                logger.warning("Start Menu shortcut launch failed for %s: %s", shortcut_path, e)

    # Strategy (c): Direct startfile / shell execute fallback
    try:
        os.startfile(name)
        return ToolResult(ok=True, output=f"Launched '{name}' via system startfile.")
    except Exception as e:
        logger.error("Failed to open application '%s': %s", name, e)
        return ToolResult(ok=False, output=f"Could not open '{name}': {str(e)}")


@tool(
    name="close_app",
    description=(
        "Gracefully closes windows of an application by name. "
        "Sends WM_CLOSE first, and terminates process only if unresponsive after 3 seconds."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the application or process to close.",
            }
        },
        "required": ["name"],
    },
    dangerous=True,
    category="apps",
)
def close_app(name: str) -> ToolResult:
    """Gracefully closes an application by name."""
    clean_name = name.strip().lower()
    closed_any = False

    # Close top-level windows matching name
    if win32gui and win32con:
        def enum_cb(hwnd: int, extra: Any) -> None:
            nonlocal closed_any
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd).lower()
                if clean_name in title:
                    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                    closed_any = True

        try:
            win32gui.EnumWindows(enum_cb, None)
        except Exception as e:
            logger.warning("Error enumerating windows for close_app: %s", e)

    time.sleep(1.0)

    # Check matching processes
    proc_matched = False
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            pname = proc.info["name"].lower()
            if clean_name in pname or pname.startswith(clean_name):
                proc_matched = True
                proc.terminate()
                try:
                    proc.wait(timeout=3.0)
                except psutil.TimeoutExpired:
                    proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if closed_any or proc_matched:
        return ToolResult(ok=True, output=f"Closed application '{name}'.")
    return ToolResult(ok=False, output=f"No running instances found for application '{name}'.")


@tool(
    name="list_running_apps",
    description="Lists the names and window titles of visible top-level windows currently running.",
    input_schema={
        "type": "object",
        "properties": {},
    },
    dangerous=False,
    category="apps",
)
def list_running_apps() -> ToolResult:
    """Lists visible top-level application windows."""
    if not win32gui:
        return ToolResult(ok=False, output="win32gui is not available.")

    windows: list[str] = []

    def enum_cb(hwnd: int, extra: Any) -> None:
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd).strip()
            if title and title not in ("Program Manager", "Default IME", "MSCTFIME UI"):
                windows.append(title)

    win32gui.EnumWindows(enum_cb, None)
    if not windows:
        return ToolResult(ok=True, output="No visible application windows detected.")

    output_lines = [f"- {w}" for w in windows[:30]]
    return ToolResult(ok=True, output="Visible running apps:\n" + "\n".join(output_lines))
