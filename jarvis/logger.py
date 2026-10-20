"""Logging configuration for Jarvis.

Sets up rotating file logging to logs/jarvis.log and standard formatting.
"""

from pathlib import Path
import logging
from logging.handlers import RotatingFileHandler

_LOGGER_INITIALIZED = False


def setup_logger(name: str = "jarvis", level: int = logging.INFO) -> logging.Logger:
    """Configures and returns a rotating file logger for Jarvis.

    Args:
        name: Logger name.
        level: Logging level.

    Returns:
        Configured logging.Logger instance.
    """
    global _LOGGER_INITIALIZED
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not _LOGGER_INITIALIZED:
        log_dir = Path("logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "jarvis.log"

        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-7s | %(name)s:%(filename)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Rotating file handler: 5MB per file, up to 5 backups
        file_handler = RotatingFileHandler(
            filename=log_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        _LOGGER_INITIALIZED = True

    return logger


# Default application logger instance
logger = setup_logger()
