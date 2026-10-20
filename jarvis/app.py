"""Application state machine orchestrating wake word, recording, STT, brain, and TTS."""

from enum import Enum
import threading
import time
from typing import Callable

from jarvis.audio.mic import mic_stream
from jarvis.audio.sounds import play_done_sound, play_error_sound, play_wake_sound
from jarvis.audio.stt import transcribe
from jarvis.audio.tts import speak, stop as stop_speech
from jarvis.audio.wakeword import WakeWordDetector
from jarvis.brain.agent import cancel_current_task, is_task_cancelled, reset_cancel_event, run_task
from jarvis.logger import logger
from jarvis.safety.killswitch import set_kill_callback, start_killswitch, stop_killswitch


class AppState(Enum):
    """Execution states for the Jarvis runtime state machine."""

    IDLE = "IDLE"
    LISTENING = "LISTENING"
    PROCESSING = "PROCESSING"
    SPEAKING = "SPEAKING"
    CONFIRMING = "CONFIRMING"
    PAUSED = "PAUSED"


class JarvisApp:
    """Jarvis core state machine managing voice events, speech pipeline, and task execution."""

    def __init__(
        self,
        ui_callback: Callable[[str, str], None] | None = None,
        enable_tray: bool = True,
    ) -> None:
        self.state = AppState.IDLE
        self.running = False
        self.ui_callback = ui_callback  # (state, message)
        self.state_lock = threading.Lock()

        # Audio components
        self.wake_detector = WakeWordDetector(on_detect=self._on_wake_detected)
        self.worker_thread: threading.Thread | None = None

        # System tray
        self.enable_tray = enable_tray
        self.tray = None
        if self.enable_tray:
            try:
                from jarvis.ui.tray import JarvisTray
                self.tray = JarvisTray(
                    on_quit=self.stop,
                    get_status_fn=lambda: self.state.value,
                )
            except Exception as e:
                logger.warning("Could not initialize system tray: %s", e)

        # Link kill switch to speech and task cancellation
        set_kill_callback(self._on_kill_switch)

    def _set_state(self, new_state: AppState, message: str = "") -> None:
        """Updates internal state and informs UI callback."""
        with self.state_lock:
            self.state = new_state
            logger.info("Jarvis State -> %s %s", new_state.value, f'({message})' if message else '')
            if self.ui_callback:
                try:
                    self.ui_callback(new_state.value, message)
                except Exception as e:
                    logger.warning("UI callback error: %s", e)

    def _on_kill_switch(self) -> None:
        """Handles emergency kill switch (Ctrl+Alt+J)."""
        logger.warning("Emergency kill switch engaged in state: %s", self.state.value)
        cancel_current_task()
        stop_speech()
        self._set_state(AppState.IDLE, "Stopped")
        speak("Stopped.", block=False)
        mic_stream.resume_wakeword()

    def _on_wake_detected(self) -> None:
        """Triggered by openWakeWord when 'hey jarvis' is detected."""
        if self.state != AppState.IDLE:
            return

        logger.info("Wake word detected! Entering LISTENING state.")
        # Start voice processing cycle in worker thread so detector stays responsive
        self.worker_thread = threading.Thread(target=self._process_voice_turn, daemon=True, name="VoiceWorker")
        self.worker_thread.start()

    def _process_voice_turn(self, is_followup: bool = False) -> None:
        """Records speech, transcribes, invokes agent loop, and speaks response."""
        reset_cancel_event()
        self._set_state(AppState.LISTENING, "Listening...")

        if not is_followup:
            play_wake_sound(block=True)

        audio_samples = mic_stream.record_until_silence()
        end_of_speech_time = time.perf_counter()

        if audio_samples is None or len(audio_samples) == 0:
            logger.info("Empty audio recording. Returning to IDLE.")
            play_error_sound(block=True)
            self._set_state(AppState.IDLE)
            return

        self._set_state(AppState.PROCESSING, "Transcribing...")
        user_text = transcribe(audio_samples)
        if not user_text.strip():
            logger.info("Transcription yielded empty text. Returning to IDLE.")
            self._set_state(AppState.IDLE)
            return

        logger.info("Transcribed User Speech: '%s'", user_text)
        self._set_state(AppState.PROCESSING, f"Thinking: '{user_text}'")

        # Execute agent loop
        def agent_progress(status: str) -> None:
            self._set_state(AppState.PROCESSING, status)

        reply = run_task(user_text, ui_callback=agent_progress)

        # Log measured latency from speech end to response generation
        speech_to_reply_latency = time.perf_counter() - end_of_speech_time
        logger.info(
            "Measured turnaround latency (end-of-speech to start-of-reply): %.2fs",
            speech_to_reply_latency,
        )
        print(f"\n[Turnaround Latency]: {speech_to_reply_latency:.2f}s | Jarvis: {reply}\n")

        # Check for cancellation before speaking
        if is_task_cancelled():
            self._set_state(AppState.IDLE)
            return

        # Speak response
        self._set_state(AppState.SPEAKING, reply)
        mic_stream.pause_wakeword()
        try:
            speak(reply, block=True)
            play_done_sound(block=False)
        finally:
            mic_stream.resume_wakeword()

        # Support follow-up questions
        if reply.strip().endswith("?"):
            logger.info("Reply ended with question mark. Initiating automatic follow-up listening.")
            self._process_voice_turn(is_followup=True)
        else:
            self._set_state(AppState.IDLE)

    def start(self) -> None:
        """Starts microphone stream, kill switch, wake word detector, and state machine."""
        if self.running:
            return
        self.running = True

        logger.info("Starting Jarvis Voice Application...")
        mic_stream.start()
        start_killswitch()
        self.wake_detector.start()
        if self.tray:
            try:
                self.tray.start()
            except Exception as e:
                logger.warning("Could not start tray: %s", e)
        self._set_state(AppState.IDLE, "Ready. Say 'Hey Jarvis'")

        print("=" * 60)
        print(" Jarvis Voice Assistant Running")
        print(" Wake phrase: 'Hey Jarvis' | Kill Switch: Ctrl+Alt+J")
        print(" Press Ctrl+C in terminal to stop.")
        print("=" * 60)

    def stop(self) -> None:
        """Stops all background audio streams and listeners."""
        self.running = False
        if self.tray:
            try:
                self.tray.stop()
            except Exception as e:
                logger.warning("Could not stop tray: %s", e)
        self.wake_detector.stop()
        stop_killswitch()
        mic_stream.stop()
        stop_speech()

        try:
            from jarvis.tools.web import browser_close

            browser_close()
        except Exception as e:
            logger.debug("Browser cleanup during shutdown: %s", e)

        self._set_state(AppState.PAUSED, "Stopped")
        logger.info("Jarvis Application stopped.")
