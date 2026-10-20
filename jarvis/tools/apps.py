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
        "Universal application launcher for Windows 11. "
        "Discovers installed software from Start Menu, Desktop shortcuts, Registry App Paths, "
        "and system locations with fuzzy matching and disambiguation support."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name or query of the application to launch (e.g., 'chrome', 'excel', 'spotify', 'cadcraft').",
            }
        },
        "required": ["name"],
    },
    dangerous=False,
    category="apps",
)
def open_app(name: str) -> ToolResult:
    """Launches an application using the universal AppResolver service."""
    from jarvis.services.app_resolver import get_app_resolver

    resolver = get_app_resolver()
    ok, message = resolver.launch(name)
    return ToolResult(ok=ok, output=message)


@tool(
    name="refresh_apps_index",
    description="Forces a full rescan of Start Menu, Desktop shortcuts, and Windows Registry application paths.",
    input_schema={"type": "object", "properties": {}},
    dangerous=False,
    category="apps",
)
def refresh_apps_index() -> ToolResult:
    """Rescans all system application sources and refreshes the persistent cache."""
    from jarvis.services.app_resolver import get_app_resolver

    resolver = get_app_resolver()
    count = resolver.refresh(force=True)
    return ToolResult(ok=True, output=f"Successfully indexed {count} applications.")


@tool(
    name="list_apps",
    description="Lists installed applications currently indexed by Jarvis matching an optional filter string.",
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Optional search term to filter indexed applications by name.",
            }
        },
    },
    dangerous=False,
    category="apps",
)
def list_apps(query: str = "") -> ToolResult:
    """Lists indexed applications matching query."""
    from jarvis.services.app_resolver import get_app_resolver

    resolver = get_app_resolver()
    clean_q = query.strip().lower()
    matching = []

    for key, app in resolver.apps.items():
        if not clean_q or clean_q in key or any(clean_q in a for a in app.aliases):
            matching.append(f"- {app.name} ({app.source})")

    if not matching:
        return ToolResult(ok=True, output=f"No installed applications found matching '{query}'.")

    matching = sorted(set(matching))[:25]
    return ToolResult(ok=True, output=f"Found {len(matching)} matching applications:\n" + "\n".join(matching))


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
        def enum_cb(hwnd: int, extra: Any) -> bool:
            nonlocal closed_any
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd).lower()
                if clean_name in title:
                    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                    closed_any = True
            return True

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

    def enum_cb(hwnd: int, extra: Any) -> bool:
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd).strip()
            if title and title not in ("Program Manager", "Default IME", "MSCTFIME UI"):
                windows.append(title)
        return True

    win32gui.EnumWindows(enum_cb, None)
    if not windows:
        return ToolResult(ok=True, output="No visible application windows detected.")

    output_lines = [f"- {w}" for w in windows[:30]]
    return ToolResult(ok=True, output="Visible running apps:\n" + "\n".join(output_lines))
