"""Crash recovery supervisor with rate-limited auto-restarts for Jarvis."""

import json
from pathlib import Path
import time
import traceback
from typing import Any, Callable

from jarvis.logger import logger

CRASH_HISTORY_FILE = Path("data/crash_history.json")
MAX_RESTARTS_PER_HOUR = 3
RESTART_WINDOW_SECONDS = 3600.0


class CrashSupervisor:
    """Tracks unhandled process exceptions and enforces a max 3 restarts per hour policy."""

    def __init__(
        self,
        history_path: Path = CRASH_HISTORY_FILE,
        max_restarts: int = MAX_RESTARTS_PER_HOUR,
        window_seconds: float = RESTART_WINDOW_SECONDS,
    ) -> None:
        self.history_path = history_path
        self.max_restarts = max_restarts
        self.window_seconds = window_seconds

    def _load_history(self) -> list[dict[str, Any]]:
        """Loads crash history timestamps from disk."""
        if not self.history_path.exists():
            return []
        try:
            with open(self.history_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning("Could not read crash history: %s", e)
            return []

    def _save_history(self, history: list[dict[str, Any]]) -> None:
        """Saves pruned crash history timestamps to disk."""
        try:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.history_path, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            logger.warning("Could not save crash history: %s", e)

    def get_recent_crashes(self) -> list[dict[str, Any]]:
        """Returns crashes that occurred within the last window_seconds."""
        now = time.time()
        history = self._load_history()
        return [entry for entry in history if now - entry.get("timestamp", 0) <= self.window_seconds]

    def record_crash(self, error_message: str) -> int:
        """Records a new crash occurrence and returns total crashes in current window."""
        now = time.time()
        recent = self.get_recent_crashes()
        recent.append({"timestamp": now, "error": error_message[:500]})
        self._save_history(recent)
        return len(recent)

    def should_restart(self) -> tuple[bool, int]:
        """Evaluates if a crash restart is permitted under rate limit.

        Returns:
            (can_restart, recent_crash_count)
        """
        recent = self.get_recent_crashes()
        count = len(recent)
        return (count <= self.max_restarts, count)

    def run_supervised(self, func: Callable[[], Any], restart_delay: float = 2.0) -> int:
        """Runs func inside an automated crash recovery supervisor loop."""
        while True:
            try:
                func()
                # Clean exit without uncaught exceptions
                return 0
            except (KeyboardInterrupt, SystemExit):
                logger.info("Normal user termination requested.")
                return 0
            except Exception as e:
                tb_str = traceback.format_exc()
                logger.critical("Unhandled exception in Jarvis application:\n%s", tb_str)

                count = self.record_crash(str(e))
                can_restart, _ = self.should_restart()

                if can_restart:
                    logger.warning(
                        "Attempting automatic crash restart (%d/%d in the last hour) in %.1fs...",
                        count,
                        self.max_restarts,
                        restart_delay,
                    )
                    time.sleep(restart_delay)
                else:
                    logger.critical(
                        "Exceeded maximum allowed restarts (%d per hour). Jarvis supervisor exiting.",
                        self.max_restarts,
                    )
                    print(
                        f"\n[CRITICAL] Jarvis has encountered repeated fatal errors ({count} in the last hour). "
                        "Auto-restart disabled. Check logs/jarvis.log for details.\n"
                    )
                    return 1
