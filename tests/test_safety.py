"""Unit tests for Jarvis safety layer, policy enforcement, audit logging, and kill switch."""

import json
from pathlib import Path
from unittest.mock import patch
import pytest

from jarvis.safety.audit import AUDIT_LOG_FILE, log_tool_execution
from jarvis.safety.killswitch import start_killswitch, stop_killswitch
from jarvis.safety.policy import _is_path_protected, requires_confirmation


def test_is_path_protected():
    """Verifies detection of protected system folders."""
    assert _is_path_protected(r"C:\Windows") is True
    assert _is_path_protected(r"C:\Windows\System32\drivers") is True
    assert _is_path_protected(r"C:\Program Files\App") is True
    assert _is_path_protected(r"C:\Program Files (x86)\App") is True

    # User documents/downloads are not system protected paths
    user_home = Path.home()
    assert _is_path_protected(str(user_home / "Documents" / "file.txt")) is False
    assert _is_path_protected(str(user_home / "Downloads" / "test.txt")) is False


def test_policy_dangerous_tools():
    """Verifies that dangerous tools require confirmation."""
    assert requires_confirmation("delete_file", {"path": "test.txt"}) is True
    assert requires_confirmation("shutdown_pc", {"action": "restart"}) is True
    assert requires_confirmation("move_file", {"src": "a.txt", "dst": "b.txt"}) is True


def test_policy_shell_command():
    """Verifies that run_command requires confirmation unless explicitly allowlisted."""
    assert requires_confirmation("run_command", {"command": "dir"}) is True

    with patch.dict("jarvis.config.config", {"safety": {"allowed_shell_commands": ["git status"]}}):
        assert requires_confirmation("run_command", {"command": "git status"}) is False
        assert requires_confirmation("run_command", {"command": "rmdir /s /q test"}) is True


def test_policy_write_file():
    """Verifies that write_text_file requires confirmation if overwriting or outside home."""
    user_home = Path.home()
    safe_path = str(user_home / "Documents" / "test.txt")

    # Safe write: inside home, overwrite=False
    assert requires_confirmation("write_text_file", {"path": safe_path, "overwrite": False}) is False

    # Overwrite=True requires confirmation
    assert requires_confirmation("write_text_file", {"path": safe_path, "overwrite": True}) is True

    # Writing to C:\Windows requires confirmation
    assert requires_confirmation("write_text_file", {"path": r"C:\Windows\bad.txt", "overwrite": False}) is True


def test_policy_hotkeys():
    """Verifies dangerous hotkey detection."""
    assert requires_confirmation("hotkey", {"keys": ["alt", "f4"]}) is True
    assert requires_confirmation("hotkey", {"keys": ["ctrl", "shift", "delete"]}) is True
    assert requires_confirmation("hotkey", {"keys": ["ctrl", "c"]}) is False
    assert requires_confirmation("hotkey", {"keys": ["ctrl", "v"]}) is False


def test_policy_close_app():
    """Verifies close_app requires confirmation for non-safe apps."""
    assert requires_confirmation("close_app", {"name": "chrome"}) is True
    assert requires_confirmation("close_app", {"name": "notepad"}) is False
    assert requires_confirmation("close_app", {"name": "calculator"}) is False


def test_audit_logging():
    """Verifies tool calls append properly formatted JSON records to audit.jsonl."""
    test_tool = "test_audit_tool"
    test_args = {"short": "123", "long": "A" * 300}

    log_tool_execution(
        tool_name=test_tool,
        args=test_args,
        ok=True,
        output="Audit success",
        confirmation_asked=True,
        confirmation_decision="allowed",
    )

    assert AUDIT_LOG_FILE.exists()
    with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    last_record = json.loads(lines[-1])
    assert last_record["tool"] == test_tool
    assert last_record["ok"] is True
    assert last_record["confirmation_asked"] is True
    assert last_record["confirmation_decision"] == "allowed"
    # Long argument should be redacted/truncated
    assert len(last_record["args"]["long"]) <= 200


def test_killswitch_lifecycle():
    """Verifies killswitch can be started and stopped without errors."""
    start_killswitch()
    stop_killswitch()


def test_killswitch_cancels_mid_task():
    """Verifies that triggering the Ctrl+Alt+J kill switch mid-task aborts execution in < 2 seconds."""
    import time
    import ctypes
    from jarvis.safety import killswitch
    from jarvis.safety.killswitch import start_killswitch, stop_killswitch, WM_HOTKEY, HOTKEY_ID
    from jarvis.brain.agent import run_task
    from jarvis.brain.providers.base import LLMProvider, LLMResponse, ToolCall

    start_killswitch()
    try:
        class SlowProvider(LLMProvider):
            def __init__(self):
                self.name = "slow"
                self.model = "slow"
                self.supports_vision = False
                self.supports_tools = True

            def chat(self, *args, **kwargs):
                return LLMResponse(
                    text="",
                    tool_calls=[ToolCall(id="c1", name="wait", args={"seconds": 5})],
                    raw=None,
                    usage={},
                )

        def progress_cb(status):
            if "running" in status and killswitch._LISTENER_TID:
                ctypes.windll.user32.PostThreadMessageW(killswitch._LISTENER_TID, WM_HOTKEY, HOTKEY_ID, 0)

        t0 = time.perf_counter()
        reply = run_task("do slow task", ui_callback=progress_cb, provider=SlowProvider())
        duration = time.perf_counter() - t0

        assert "stopped" in reply.lower()
        assert duration < 2.0  # Must abort in under 2 seconds
    finally:
        stop_killswitch()
