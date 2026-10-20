"""Unit tests for Phase 8: startup registration, named mutex, crash recovery, and setup checks."""

import json
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch
import pytest

from jarvis.crash_recovery import CrashSupervisor
from jarvis.platform.mutex import SingleInstanceMutex
from jarvis.setup_check import (
    check_api_keys,
    check_browser_automation,
    check_microphone,
    check_tts_engine,
    check_wake_models,
    run_all_checks,
)
from scripts.install_startup import (
    get_command_path,
    get_startup_status,
    install_to_startup,
    uninstall_from_startup,
)


def test_single_instance_mutex_lifecycle():
    """Verifies named mutex prevents second concurrent instance and allows release."""
    mutex_name = "Local\\Jarvis_Test_Mutex_Lifecycle"

    m1 = SingleInstanceMutex(mutex_name)
    m2 = SingleInstanceMutex(mutex_name)

    try:
        assert m1.acquire() is True

        # Second instance should be blocked
        assert m2.acquire() is False
        assert m2.already_running is True

        # Release first instance
        m1.release()

        # Now second instance can acquire
        assert m2.acquire() is True
    finally:
        m1.release()
        m2.release()


def test_single_instance_mutex_context_manager():
    """Verifies mutex works as a context manager."""
    mutex_name = "Local\\Jarvis_Test_Mutex_Context"

    with SingleInstanceMutex(mutex_name) as acquired:
        assert acquired is True

        # Nested instance with same name should fail
        m2 = SingleInstanceMutex(mutex_name)
        assert m2.acquire() is False
        m2.release()


def test_crash_supervisor_normal_run(tmp_path: Path):
    """Verifies supervisor runs clean function without recording crashes."""
    history_file = tmp_path / "crash_history.json"
    supervisor = CrashSupervisor(history_path=history_file, max_restarts=3)

    run_counter = [0]

    def clean_task():
        run_counter[0] += 1

    ret = supervisor.run_supervised(clean_task)
    assert ret == 0
    assert run_counter[0] == 1
    assert len(supervisor.get_recent_crashes()) == 0


def test_crash_supervisor_max_restart_limit(tmp_path: Path):
    """Verifies supervisor enforces max 3 restarts per hour policy."""
    history_file = tmp_path / "crash_history.json"
    supervisor = CrashSupervisor(history_path=history_file, max_restarts=3, window_seconds=3600.0)

    run_counter = [0]

    def failing_task():
        run_counter[0] += 1
        raise RuntimeError(f"Simulated crash #{run_counter[0]}")

    # Supervisor should attempt restarts until limit is hit, then return 1
    ret = supervisor.run_supervised(failing_task, restart_delay=0.01)
    assert ret == 1
    # Initial run + 3 restarts = 4 runs total
    assert run_counter[0] == 4

    # Verify history recorded
    crashes = supervisor.get_recent_crashes()
    assert len(crashes) == 4
    can_restart, count = supervisor.should_restart()
    assert can_restart is False
    assert count >= 3


def test_setup_checks():
    """Verifies diagnostic check functions return structured CheckResult objects."""
    res_api = check_api_keys()
    assert res_api.status in ("PASS", "WARN", "FAIL")
    assert res_api.name is not None

    res_mic = check_microphone()
    assert res_mic.status in ("PASS", "WARN", "FAIL")

    res_wake = check_wake_models()
    assert res_wake.status in ("PASS", "WARN")

    res_tts = check_tts_engine()
    assert res_tts.status in ("PASS", "WARN")

    res_browser = check_browser_automation()
    assert res_browser.status in ("PASS", "WARN", "FAIL")

    all_res = run_all_checks()
    assert len(all_res) >= 5


def test_install_startup_command_resolution():
    """Verifies pythonw / python executable path resolution."""
    pythonw, main_py = get_command_path()
    assert pythonw.name in ("pythonw.exe", "python.exe")
    assert main_py.name == "main.py"
    assert main_py.exists()


def test_install_startup_registry_mock():
    """Verifies startup registry installation and removal logic with mock winreg."""
    mock_winreg = MagicMock()
    mock_key = MagicMock()
    mock_winreg.OpenKey.return_value.__enter__.return_value = mock_key

    with patch.dict("sys.modules", {"winreg": mock_winreg}):
        # 1. Test install
        ok_ins, msg_ins = install_to_startup("JarvisTestApp")
        assert ok_ins is True
        mock_winreg.SetValueEx.assert_called_once()

        # 2. Test status
        mock_winreg.QueryValueEx.return_value = ("fake_cmd", 1)
        is_inst, cmd = get_startup_status("JarvisTestApp")
        assert is_inst is True
        assert cmd == "fake_cmd"

        # 3. Test uninstall
        ok_un, msg_un = uninstall_from_startup("JarvisTestApp")
        assert ok_un is True
        mock_winreg.DeleteValue.assert_called_once()
