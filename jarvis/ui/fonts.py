"""Font management for Jarvis UI, registering and applying Satoshi typography."""

from pathlib import Path
import sys

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from jarvis.logger import logger


def _get_fonts_dir() -> Path:
    """Returns the directory containing bundled font assets."""
    if hasattr(sys, "_MEIPASS"):
        candidate = Path(sys._MEIPASS) / "jarvis" / "resources" / "fonts"
        if candidate.exists():
            return candidate
        alt_candidate = Path(sys._MEIPASS) / "resources" / "fonts"
        if alt_candidate.exists():
            return alt_candidate

    return Path(__file__).resolve().parent.parent / "resources" / "fonts"


def setup_satoshi_font(app: QApplication | None = None) -> str:
    """Registers Satoshi font weights with QFontDatabase and sets application font.

    Args:
        app: Optional QApplication instance to apply the font to.

    Returns:
        The registered font family name ('Satoshi' or fallback 'Segoe UI').
    """
    fonts_dir = _get_fonts_dir()
    font_files = [
        "Satoshi-Regular.otf",
        "Satoshi-Medium.otf",
        "Satoshi-Bold.otf",
    ]

    loaded_any = False
    for font_file in font_files:
        path = fonts_dir / font_file
        if path.exists():
            fid = QFontDatabase.addApplicationFont(str(path))
            if fid != -1:
                loaded_any = True
                logger.debug("Registered font asset: %s (id: %d)", font_file, fid)
            else:
                logger.warning("Failed to register font asset: %s", font_file)
        else:
            logger.debug("Font asset not found at %s", path)

    chosen_family = "Satoshi" if loaded_any else "Segoe UI"

    if app is not None:
        font = QFont(chosen_family, 10)
        font.setStyleHint(QFont.StyleHint.SansSerif)
        app.setFont(font)
        logger.info("Application typography configured with primary font: '%s'", chosen_family)

    return chosen_family
