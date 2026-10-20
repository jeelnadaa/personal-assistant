"""System tray icon and context menu for background Jarvis operation using pystray."""

import os
from pathlib import Path
import threading
from typing import Any, Callable

from PIL import Image, ImageDraw
import pystray

from jarvis.audio.mic import mic_stream
from jarvis.audio.tts import stop as stop_speech
from jarvis.brain.agent import cancel_current_task
from jarvis.logger import logger


def create_tray_icon_image(size: int = 64, active: bool = True) -> Image.Image:
    """Draws a clean, modern circular Jarvis icon with Pillow."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = 4
    # Outer circle
    bg_color = (20, 26, 38, 255) if active else (40, 40, 40, 255)
    border_color = (0, 210, 255, 255) if active else (120, 120, 120, 255)
    draw.ellipse((margin, margin, size - margin, size - margin), fill=bg_color, outline=border_color, width=3)

    # Inner glowing dot
    dot_margin = size // 3
    dot_color = (0, 235, 255, 255) if active else (150, 150, 150, 255)
    draw.ellipse(
        (dot_margin, dot_margin, size - dot_margin, size - dot_margin),
        fill=dot_color,
    )
    return img


class JarvisTray:
    """Manages the background system tray icon and menu callbacks."""

    def __init__(
        self,
        on_quit: Callable[[], None] | None = None,
        get_status_fn: Callable[[], str] | None = None,
        on_reload: Callable[[], None] | None = None,
    ) -> None:
        self.on_quit = on_quit
        self.get_status_fn = get_status_fn
        self.on_reload = on_reload
        self.is_paused = False
        self.console_visible = False
        self.icon: pystray.Icon | None = None
        self._thread: threading.Thread | None = None

    def _on_status_clicked(self, icon: pystray.Icon, item: Any) -> None:
        """Displays status notification."""
        from jarvis.config import get_config_summary
        cfg_summary = get_config_summary()
        status = self.get_status_fn() if self.get_status_fn else "Running"
        summary_msg = (
            f"Status: {status}\n"
            f"Provider: {cfg_summary['llm_provider']} ({cfg_summary['llm_model']})\n"
            f"Wake phrase: '{cfg_summary['wakeword_phrase']}'\n"
            f"STT: {cfg_summary['stt_provider']} ({cfg_summary['stt_model']} on {cfg_summary['stt_device']})\n"
            f"TTS: {cfg_summary['tts_engine']}"
        )
        logger.info("Tray menu: Status queried -> %s", status)
        try:
            icon.notify(summary_msg, title="Jarvis Assistant Status")
        except Exception as e:
            logger.warning("Could not show tray notification: %s", e)

    def _on_toggle_pause_clicked(self, icon: pystray.Icon, item: Any) -> None:
        """Toggles pausing of wake word and mic listening."""
        self.is_paused = not self.is_paused
        if self.is_paused:
            mic_stream.pause_wakeword()
            logger.info("Tray menu: Wake word paused.")
            icon.icon = create_tray_icon_image(active=False)
            try:
                icon.notify("Wake word listener paused.", title="Jarvis Assistant")
            except Exception:
                pass
        else:
            mic_stream.resume_wakeword()
            logger.info("Tray menu: Wake word resumed.")
            icon.icon = create_tray_icon_image(active=True)
            try:
                icon.notify("Wake word listener active.", title="Jarvis Assistant")
            except Exception:
                pass

    def _on_edit_config_clicked(self, icon: pystray.Icon, item: Any) -> None:
        """Opens config.yaml in the system editor."""
        from jarvis.config import BASE_DIR
        cfg_path = BASE_DIR / "config.yaml"
        logger.info("Tray menu: Opening configuration file at %s", cfg_path)
        try:
            if not cfg_path.exists():
                cfg_path.touch()
            os.startfile(str(cfg_path))
        except Exception as e:
            logger.error("Failed to open config.yaml: %s", e)

    def _on_edit_env_clicked(self, icon: pystray.Icon, item: Any) -> None:
        """Opens .env file in Notepad."""
        import subprocess
        from jarvis.config import BASE_DIR
        env_path = BASE_DIR / ".env"
        logger.info("Tray menu: Opening environment file at %s", env_path)
        try:
            if not env_path.exists():
                env_path.touch()
            subprocess.Popen(["notepad.exe", str(env_path)])
        except Exception as e:
            logger.error("Failed to open .env: %s", e)

    def _on_reload_config_clicked(self, icon: pystray.Icon, item: Any) -> None:
        """Reloads settings and wake word phrase without restarting."""
        logger.info("Tray menu: Reload configuration triggered.")
        try:
            if self.on_reload:
                self.on_reload()
            else:
                from jarvis.config import reload_config
                reload_config()
            icon.notify("Configuration reloaded successfully.", title="Jarvis Assistant")
        except Exception as e:
            logger.error("Failed to reload configuration: %s", e)
            try:
                icon.notify(f"Reload failed: {e}", title="Jarvis Assistant")
            except Exception:
                pass

    def _on_toggle_console_clicked(self, icon: pystray.Icon, item: Any) -> None:
        """Toggles visibility of the attached Windows console window."""
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if not hwnd:
            try:
                icon.notify("No console window is attached to this process.", title="Jarvis Assistant")
            except Exception:
                pass
            return
        self.console_visible = not self.console_visible
        # SW_SHOW = 5, SW_HIDE = 0
        ctypes.windll.user32.ShowWindow(hwnd, 5 if self.console_visible else 0)

    def _on_text_mode_clicked(self, icon: pystray.Icon, item: Any) -> None:
        """Opens or gives guidance on text mode."""
        logger.info("Tray menu: Text mode selected.")
        try:
            icon.notify("Run 'jarvis.exe --text' or 'python main.py --text' for CLI console mode.", title="Jarvis Text Mode")
        except Exception:
            pass

    def _on_open_data_clicked(self, icon: pystray.Icon, item: Any) -> None:
        """Opens data directory in Windows Explorer."""
        from jarvis.config import BASE_DIR
        data_dir = (BASE_DIR / "data").resolve()
        data_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Tray menu: Opening data folder at %s", data_dir)
        try:
            os.startfile(str(data_dir))
        except Exception as e:
            logger.error("Failed to open data directory: %s", e)

    def _on_open_logs_clicked(self, icon: pystray.Icon, item: Any) -> None:
        """Opens logs directory in Windows Explorer."""
        from jarvis.config import BASE_DIR
        logs_dir = (BASE_DIR / "logs").resolve()
        logs_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Tray menu: Opening logs folder at %s", logs_dir)
        try:
            os.startfile(str(logs_dir))
        except Exception as e:
            logger.error("Failed to open logs directory: %s", e)

    def _on_stop_task_clicked(self, icon: pystray.Icon, item: Any) -> None:
        """Cancels any running task and stops speech immediately."""
        logger.warning("Tray menu: Emergency task stop triggered.")
        cancel_current_task()
        stop_speech()
        try:
            icon.notify("Stopped active task.", title="Jarvis Assistant")
        except Exception:
            pass

    def _on_quit_clicked(self, icon: pystray.Icon, item: Any) -> None:
        """Stops tray icon and signals application termination."""
        logger.info("Tray menu: Quit selected.")
        cancel_current_task()
        stop_speech()
        icon.stop()
        if self.on_quit:
            self.on_quit()

    def _build_menu(self) -> pystray.Menu:
        """Constructs the system tray context menu."""
        return pystray.Menu(
            pystray.MenuItem("Status", self._on_status_clicked),
            pystray.MenuItem(
                lambda item: "Resume listening" if self.is_paused else "Pause listening",
                self._on_toggle_pause_clicked,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Configure (config.yaml)", self._on_edit_config_clicked),
            pystray.MenuItem("Configure Keys (.env)", self._on_edit_env_clicked),
            pystray.MenuItem("Reload Configuration", self._on_reload_config_clicked),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Toggle Console Window", self._on_toggle_console_clicked),
            pystray.MenuItem("Open Data Folder", self._on_open_data_clicked),
            pystray.MenuItem("Open Logs Folder", self._on_open_logs_clicked),
            pystray.MenuItem("Text Mode Info", self._on_text_mode_clicked),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Stop Current Task (Ctrl+Alt+J)", self._on_stop_task_clicked),
            pystray.MenuItem("Quit Jarvis", self._on_quit_clicked),
        )

    def start(self) -> None:
        """Starts the tray icon in a dedicated daemon thread."""
        img = create_tray_icon_image(active=True)
        self.icon = pystray.Icon(
            name="Jarvis",
            icon=img,
            title="Jarvis Assistant",
            menu=self._build_menu(),
        )
        self._thread = threading.Thread(target=self.icon.run, daemon=True, name="TrayThread")
        self._thread.start()
        logger.info("Jarvis system tray icon started.")

    def stop(self) -> None:
        """Stops the tray icon if running."""
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
