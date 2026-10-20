"""Safety policy rules for dangerous actions and protected resources."""

from pathlib import Path
from typing import Any
from jarvis.config import config
from jarvis.tools.base import get_tool

SAFE_CLOSE_APPS = {
    "notepad",
    "calculator",
    "calc",
    "paint",
}


def _is_path_protected(path_str: str) -> bool:
    """Checks whether a target filesystem path is inside protected system directories."""
    try:
        resolved = Path(path_str).expanduser().resolve()
        safety_cfg = config.get("safety", {})
        protected_list = safety_cfg.get("protected_paths", [
            r"C:\Windows",
            r"C:\Program Files",
            r"C:\Program Files (x86)",
        ])
        for prot in protected_list:
            prot_path = Path(prot).resolve()
            if resolved == prot_path or prot_path in resolved.parents:
                return True
    except Exception:
        pass
    return False


def requires_confirmation(tool_name: str, args: dict[str, Any]) -> bool:
    """Determines whether a tool invocation requires explicit user approval.

    Checks:
    - Dangerous flag on Tool definition
    - System protected paths
    - Shell command allowlists
    - Dangerous hotkeys (e.g. alt+f4)
    - write_text_file outside home or with overwrite=True
    - close_app on non-safe applications

    Args:
        tool_name: Tool name being invoked.
        args: Invocation arguments.

    Returns:
        True if confirmation is required before execution.
    """
    safety_cfg = config.get("safety", {})
    if not safety_cfg.get("confirm_dangerous", True):
        return False

    # 1. Shell commands require confirmation unless explicitly allowed
    if tool_name == "run_command":
        cmd = args.get("command", "").strip()
        allowed = safety_cfg.get("allowed_shell_commands", [])
        return cmd not in allowed

    # 2. close_app is dangerous if app is not in the safe list
    if tool_name == "close_app":
        app_name = args.get("name", "").strip().lower()
        return app_name not in SAFE_CLOSE_APPS

    # 3. Check general tool definition dangerous flag
    tool_obj = get_tool(tool_name)
    if tool_obj and tool_obj.dangerous:
        return True

    # 4. Check for path-based tools targeting protected directories
    for key in ("path", "src", "dst", "folder"):
        if key in args and isinstance(args[key], str):
            if _is_path_protected(args[key]):
                return True

    # 5. write_text_file is dangerous if overwrite=True or path is outside user's home
    if tool_name == "write_text_file":
        if args.get("overwrite", False):
            return True
        path_val = args.get("path", "")
        if path_val:
            try:
                resolved = Path(path_val).expanduser().resolve()
                home = Path.home().resolve()
                if not (resolved == home or home in resolved.parents):
                    return True
            except Exception:
                return True

    # Dangerous keyboard hotkeys
    if tool_name == "hotkey":
        keys = args.get("keys", [])
        normalized = [str(k).lower().strip() for k in keys]
        if "alt" in normalized and "f4" in normalized:
            return True
        if "ctrl" in normalized and "shift" in normalized and "delete" in normalized:
            return True

    return False
