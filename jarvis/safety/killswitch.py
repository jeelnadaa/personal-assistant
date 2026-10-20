"""Global Windows kill switch listener (Ctrl+Alt+J).

Registers a system-wide hotkey using the Windows user32 API.
When pressed, immediately signals task cancellation within milliseconds.
"""

import ctypes
from ctypes import wintypes
import threading
from typing import Callable

from jarvis.brain.agent import cancel_current_task
from jarvis.logger import logger

HOTKEY_ID = 0x4A01
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
VK_J = 0x4A  # Virtual Key for 'J'
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

_LISTENER_THREAD: threading.Thread | None = None
_LISTENER_TID: int | None = None
_STOP_EVENT = threading.Event()
_CUSTOM_KILL_CALLBACK: Callable[[], None] | None = None


def set_kill_callback(cb: Callable[[], None] | None) -> None:
    """Sets an optional callback invoked when the kill switch triggers (e.g. stop TTS / hide UI)."""
    global _CUSTOM_KILL_CALLBACK
    _CUSTOM_KILL_CALLBACK = cb


def _hotkey_worker() -> None:
    """Background message loop thread that registers and monitors Ctrl+Alt+J."""
    global _LISTENER_TID
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    _LISTENER_TID = kernel32.GetCurrentThreadId()

    # Register Ctrl+Alt+J hotkey
    reg_ok = user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL | MOD_ALT, VK_J)
    if not reg_ok:
        logger.warning("Could not register Ctrl+Alt+J global hotkey (error code %d).", kernel32.GetLastError())
        return

    logger.info("Ctrl+Alt+J global kill switch registered successfully.")

    msg = wintypes.MSG()
    while not _STOP_EVENT.is_set():
        # Peek and retrieve messages from thread queue
        res = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
        if res <= 0:  # WM_QUIT or error
            break

        if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
            logger.warning("[KILL SWITCH] Ctrl+Alt+J detected! Cancelling active task.")
            cancel_current_task()
            print("\n[!] Ctrl+Alt+J pressed: Task stopped immediately.")
            if _CUSTOM_KILL_CALLBACK:
                try:
                    _CUSTOM_KILL_CALLBACK()
                except Exception as e:
                    logger.error("Error in custom kill switch callback: %s", e)

        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))

    user32.UnregisterHotKey(None, HOTKEY_ID)
    logger.info("Ctrl+Alt+J global kill switch unregistered.")


def start_killswitch() -> None:
    """Starts the background thread monitoring for Ctrl+Alt+J."""
    global _LISTENER_THREAD, _STOP_EVENT
    if _LISTENER_THREAD and _LISTENER_THREAD.is_alive():
        return

    _STOP_EVENT.clear()
    _LISTENER_THREAD = threading.Thread(target=_hotkey_worker, daemon=True, name="KillSwitchListener")
    _LISTENER_THREAD.start()


def stop_killswitch() -> None:
    """Unregisters the hotkey and stops the listener thread."""
    global _LISTENER_THREAD, _LISTENER_TID, _STOP_EVENT
    _STOP_EVENT.set()
    if _LISTENER_TID:
        try:
            ctypes.windll.user32.PostThreadMessageW(_LISTENER_TID, WM_QUIT, 0, 0)
        except Exception:
            pass
    if _LISTENER_THREAD:
        _LISTENER_THREAD.join(timeout=1.0)
    _LISTENER_THREAD = None
    _LISTENER_TID = None
