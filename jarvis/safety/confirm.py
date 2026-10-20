"""Confirmation prompt handling for dangerous operations (UI buttons and voice)."""

import sys
import threading
import time
from typing import Callable

from jarvis.config import config
from jarvis.logger import logger

_CUSTOM_CONFIRM_HANDLER: Callable[[str], bool] | None = None
AFFIRMATIVE_VOICE_RESPONSES = {"yes", "yeah", "go ahead", "do it", "sure", "confirm", "allow"}


def set_confirm_handler(handler: Callable[[str], bool] | None) -> None:
    """Sets a custom confirmation handler (e.g. GUI dialog or voice prompt)."""
    global _CUSTOM_CONFIRM_HANDLER
    _CUSTOM_CONFIRM_HANDLER = handler


def _voice_confirm_worker(
    description: str,
    confirm_event: threading.Event,
    result_target: Any,
) -> None:
    """Runs spoken voice prompt and listens for spoken yes/no response."""
    try:
        from jarvis.audio.mic import mic_stream
        from jarvis.audio.stt import transcribe
        from jarvis.audio.tts import speak

        # Speak confirmation prompt aloud
        speak(f"{description}. Should I go ahead?", block=True)

        if confirm_event.is_set():
            return

        # Record spoken response
        samples = mic_stream.record_until_silence(max_record_seconds=6.0, silence_seconds=1.2)
        if confirm_event.is_set():
            return

        if samples is not None and len(samples) > 0:
            user_speech = transcribe(samples).strip().lower()
            logger.info("Voice confirmation transcription: '%s'", user_speech)

            if any(term in user_speech for term in AFFIRMATIVE_VOICE_RESPONSES):
                logger.info("Spoken confirmation approved: matched affirmative response.")
                if hasattr(result_target, "_confirm_result"):
                    result_target._confirm_result = True
                else:
                    result_target[0] = True
                confirm_event.set()
            elif any(neg in user_speech for neg in ["no", "deny", "cancel", "stop", "don't"]):
                logger.info("Spoken confirmation rejected: matched negative response.")
                if hasattr(result_target, "_confirm_result"):
                    result_target._confirm_result = False
                else:
                    result_target[0] = False
                confirm_event.set()
    except Exception as exc:
        logger.warning("Voice confirmation error: %s", exc)


def ask(description: str) -> bool:
    """Asks the user for approval to execute a potentially dangerous action.

    Handles overlay UI buttons, voice confirmation, and console fallback.

    Args:
        description: Readable summary of the action requesting execution.

    Returns:
        True if approved, False otherwise.
    """
    logger.info("Requesting confirmation for: %s", description)

    if _CUSTOM_CONFIRM_HANDLER is not None:
        try:
            decision = _CUSTOM_CONFIRM_HANDLER(description)
            logger.info("Custom confirm handler returned: %s", decision)
            return decision
        except Exception as e:
            logger.error("Error in custom confirm handler: %s", e)
            return False

    # Check if PySide6 QApplication is active
    try:
        from PySide6.QtWidgets import QApplication
        from jarvis.ui.overlay import get_overlay

        if QApplication.instance() is not None:
            overlay = get_overlay()
            confirm_method = config.get("safety", {}).get("confirm_method", "voice").lower()

            overlay._confirm_event.clear()
            overlay._confirm_result = False

            # Display prompt and buttons on overlay
            overlay.bridge.sig_confirm_request.emit(description)

            # If voice confirmation is enabled, start voice listener thread
            if confirm_method in ("voice", "both"):
                voice_thread = threading.Thread(
                    target=_voice_confirm_worker,
                    args=(description, overlay._confirm_event, overlay),
                    daemon=True,
                    name="VoiceConfirmThread",
                )
                voice_thread.start()

            # Wait up to 15 seconds for decision (pump Qt events if on main thread)
            app = QApplication.instance()
            is_main_thread = threading.current_thread() is threading.main_thread()
            if is_main_thread and app is not None:
                start_time = time.perf_counter()
                finished = False
                while time.perf_counter() - start_time < 15.0:
                    app.processEvents()
                    if overlay._confirm_event.is_set():
                        finished = True
                        break
                    time.sleep(0.02)
            else:
                finished = overlay._confirm_event.wait(timeout=15.0)

            overlay.bridge.sig_set_state.emit("IDLE", "")

            if not finished:
                logger.warning("Confirmation timed out after 15s. Denying action.")
                return False

            decision = overlay._confirm_result
            logger.info("Confirmation resolved to: %s", decision)
            return decision

    except Exception as e:
        logger.debug("Overlay confirmation unavailable, falling back to console: %s", e)

    # Fallback to console prompt
    try:
        print(f"\n[SECURITY] Jarvis wants to: {description}")
        resp = input("Allow this action? [y/N]: ").strip().lower()
        allowed = resp in ("y", "yes")
        logger.info("Console confirmation decision: %s", allowed)
        return allowed
    except (EOFError, KeyboardInterrupt):
        return False
