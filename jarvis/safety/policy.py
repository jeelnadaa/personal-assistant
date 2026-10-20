"""Safety policy rules for dangerous actions and protected resources."""

from pathlib import Path
from typing import Any
from jarvis.config import config
from jarvis.tools.base import get_tool


def _is_path_protected(path_str: str) -> bool:
    """Checks whether a target filesystem path is inside protected system directories."""
    try:
        resolved = Path(path_str).resolve()
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

    Args:
        tool_name: Tool name being invoked.
        args: Invocations arguments.

    Returns:
        True if confirmation is required before execution.
    """
    safety_cfg = config.get("safety", {})
    if not safety_cfg.get("confirm_dangerous", True):
        return False

    tool_obj = get_tool(tool_name)
    if tool_obj and tool_obj.dangerous:
        return True

    # Check for path-based tools targeting protected directories
    for key in ("path", "src", "dst", "folder"):
        if key in args and isinstance(args[key], str):
            if _is_path_protected(args[key]):
                return True

    # Shell commands require confirmation unless explicitly allowed
    if tool_name == "run_command":
        cmd = args.get("command", "").strip()
        allowed = safety_cfg.get("allowed_shell_commands", [])
        if cmd not in allowed:
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
