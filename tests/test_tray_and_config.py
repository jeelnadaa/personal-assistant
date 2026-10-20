"""Tests for in-app configuration reloading, frozen paths, and system tray actions."""

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

from jarvis.config import (
    BASE_DIR,
    get_base_dir,
    get_bundled_dir,
    get_config_summary,
    load_config,
    reload_config,
)
from jarvis.ui.tray import JarvisTray


class TestConfigFrozenAndReload(unittest.TestCase):
    """Verifies that config correctly handles frozen binary paths and live reloading."""

    def test_base_dir_not_frozen(self) -> None:
        """When running from source, get_base_dir should return project root."""
        with patch.object(sys, "frozen", False, create=True):
            base = get_base_dir()
            self.assertTrue((base / "main.py").exists() or (base / "config.yaml").exists())

    def test_base_dir_frozen(self) -> None:
        """When running frozen, get_base_dir should point to the directory of sys.executable."""
        fake_exe = "C:\\Program Files\\Jarvis\\jarvis.exe"
        with patch.object(sys, "frozen", True, create=True), patch.object(sys, "executable", fake_exe):
            base = get_base_dir()
            self.assertEqual(base, Path("C:\\Program Files\\Jarvis"))

    def test_bundled_dir(self) -> None:
        """When sys._MEIPASS is defined, get_bundled_dir should return it."""
        fake_temp = "C:\\Users\\User\\AppData\\Local\\Temp\\_MEI12345"
        with patch.object(sys, "_MEIPASS", fake_temp, create=True):
            bundled = get_bundled_dir()
            self.assertEqual(bundled, Path(fake_temp))

    def test_reload_config(self) -> None:
        """reload_config should refresh config values."""
        cfg = reload_config()
        self.assertIsInstance(cfg, dict)
        self.assertIn("llm", cfg)

    def test_config_summary_no_secrets(self) -> None:
        """get_config_summary should not disclose secret API keys."""
        summary = get_config_summary()
        self.assertIn("llm_provider", summary)
        self.assertIn("wakeword_phrase", summary)
        self.assertIn("config_file", summary)
        # Ensure no key fields exist in summary
        for key in summary.keys():
            self.assertNotIn("key", key.lower())
            self.assertNotIn("secret", key.lower())


class TestTrayPersistenceAndActions(unittest.TestCase):
    """Verifies system tray menu items and handlers."""

    def setUp(self) -> None:
        self.on_quit_mock = MagicMock()
        self.on_reload_mock = MagicMock()
        self.tray = JarvisTray(
            on_quit=self.on_quit_mock,
            get_status_fn=lambda: "IDLE",
            on_reload=self.on_reload_mock,
        )

    def test_menu_contains_configuration_and_persistence_actions(self) -> None:
        """Menu must contain config editors, reloader, console toggle, and data/logs shortcuts."""
        menu = self.tray._build_menu()
        menu_texts = [item.text for item in menu.items if hasattr(item, "text")]

        self.assertIn("Status", menu_texts)
        self.assertIn("Configure (config.yaml)", menu_texts)
        self.assertIn("Configure Keys (.env)", menu_texts)
        self.assertIn("Reload Configuration", menu_texts)
        self.assertIn("Toggle Console Window", menu_texts)
        self.assertIn("Open Data Folder", menu_texts)
        self.assertIn("Open Logs Folder", menu_texts)
        self.assertIn("Quit Jarvis", menu_texts)

    def test_reload_config_action_invokes_callback(self) -> None:
        """Clicking reload should invoke the on_reload callback."""
        mock_icon = MagicMock()
        self.tray._on_reload_config_clicked(mock_icon, None)
        self.on_reload_mock.assert_called_once()
        mock_icon.notify.assert_called()

    def test_status_action_displays_summary(self) -> None:
        """Querying status from tray should format status and active models."""
        mock_icon = MagicMock()
        self.tray._on_status_clicked(mock_icon, None)
        mock_icon.notify.assert_called()
        args, kwargs = mock_icon.notify.call_args
        self.assertIn("Status: IDLE", args[0])

    def test_toggle_pause_updates_mic(self) -> None:
        """Toggling pause should pause/resume wake word listener."""
        mock_icon = MagicMock()
        with patch("jarvis.ui.tray.mic_stream") as mock_mic:
            # 1. First toggle pauses
            self.tray._on_toggle_pause_clicked(mock_icon, None)
            self.assertTrue(self.tray.is_paused)
            mock_mic.pause_wakeword.assert_called_once()

            # 2. Second toggle resumes
            self.tray._on_toggle_pause_clicked(mock_icon, None)
            self.assertFalse(self.tray.is_paused)
            mock_mic.resume_wakeword.assert_called_once()


if __name__ == "__main__":
    unittest.main()
