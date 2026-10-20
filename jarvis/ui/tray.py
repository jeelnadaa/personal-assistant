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
    ) -> None:
        self.on_quit = on_quit
        self.get_status_fn = get_status_fn
        self.is_paused = False
        self.icon: pystray.Icon | None = None
        self._thread: threading.Thread | None = None

    def _on_status_clicked(self, icon: pystray.Icon, item: Any) -> None:
        """Displays status notification."""
        status = self.get_status_fn() if self.get_status_fn else "Running"
        logger.info("Tray menu: Status queried -> %s", status)
        try:
            icon.notify(f"Current Status: {status}", title="Jarvis Assistant")
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

    def _on_text_mode_clicked(self, icon: pystray.Icon, item: Any) -> None:
        """Opens or gives guidance on text mode."""
        logger.info("Tray menu: Text mode selected.")
        try:
            icon.notify("Run 'python main.py --text' in a terminal for text console mode.", title="Jarvis Text Mode")
        except Exception:
            pass

    def _on_open_logs_clicked(self, icon: pystray.Icon, item: Any) -> None:
        """Opens logs directory in Windows Explorer."""
        logs_dir = Path("logs").resolve()
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
            pystray.MenuItem("Text mode", self._on_text_mode_clicked),
            pystray.MenuItem("Open logs folder", self._on_open_logs_clicked),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Stop current task", self._on_stop_task_clicked),
            pystray.MenuItem("Quit", self._on_quit_clicked),
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
