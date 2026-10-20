"""Auto-discovers and registers all tools in jarvis.tools."""

import importlib
import pkgutil
from pathlib import Path

from jarvis.tools.base import (
    Tool,
    ToolResult,
    tool,
    run_tool,
    get_tool,
    get_all_tools,
    get_tool_schemas,
)

# Dynamically import all tool modules in this package to trigger @tool registrations
_tools_dir = Path(__file__).resolve().parent
for _module_info in pkgutil.iter_modules([str(_tools_dir)]):
    if _module_info.name not in ("base", "__main__") and not _module_info.name.startswith("_"):
        importlib.import_module(f"jarvis.tools.{_module_info.name}")

# Explicit imports to guarantee bundling and registration under PyInstaller frozen binary
_KNOWN_TOOL_MODULES = (
    "apps",
    "clipboard",
    "files",
    "input_control",
    "memory_tools",
    "screen",
    "shell",
    "system",
    "web",
    "windows_mgmt",
)
for _mod_name in _KNOWN_TOOL_MODULES:
    try:
        importlib.import_module(f"jarvis.tools.{_mod_name}")
    except Exception:
        pass

__all__ = [
    "Tool",
    "ToolResult",
    "tool",
    "run_tool",
    "get_tool",
    "get_all_tools",
    "get_tool_schemas",
]
