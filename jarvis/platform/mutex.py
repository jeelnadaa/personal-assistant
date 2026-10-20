"""Single-instance application lock using Windows Named Mutex."""

import ctypes
import sys
from typing import Any

from jarvis.logger import logger

ERROR_ALREADY_EXISTS = 183


class SingleInstanceMutex:
    """Windows Named Mutex to prevent multiple concurrent instances of Jarvis."""

    def __init__(self, mutex_name: str = "Local\\JarvisDesktopAssistantSingleInstanceMutex") -> None:
        self.mutex_name = mutex_name
        self.handle: Any = None
        self.already_running = False

    def acquire(self) -> bool:
        """Attempts to acquire the named mutex.

        Returns:
            True if this is the only instance running, False if another instance is detected.
        """
        if sys.platform != "win32":
            return True

        try:
            kernel32 = ctypes.windll.kernel32
            # CreateMutexW(lpMutexAttributes, bInitialOwner, lpName)
            self.handle = kernel32.CreateMutexW(None, True, self.mutex_name)
            last_error = kernel32.GetLastError()
            if last_error == ERROR_ALREADY_EXISTS:
                self.already_running = True
                if self.handle:
                    kernel32.CloseHandle(self.handle)
                    self.handle = None
                logger.warning(
                    "Another instance of Jarvis is already running (Mutex: %s).",
                    self.mutex_name,
                )
                return False

            self.already_running = False
            return True
        except Exception as e:
            logger.error("Failed to create named mutex: %s", e)
            return True  # Fallback to allow starting if mutex creation fails

    def release(self) -> None:
        """Releases and closes the mutex handle."""
        if sys.platform != "win32" or not self.handle:
            return

        try:
            kernel32 = ctypes.windll.kernel32
            kernel32.ReleaseMutex(self.handle)
            kernel32.CloseHandle(self.handle)
            self.handle = None
            logger.debug("Released named mutex: %s", self.mutex_name)
        except Exception as e:
            logger.error("Error releasing mutex: %s", e)

    def __enter__(self) -> bool:
        return self.acquire()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()
