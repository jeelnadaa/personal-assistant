"""Application state machine orchestrating wake word, recording, STT, brain, and TTS."""

from enum import Enum
import threading
import time
from typing import Callable

from jarvis.audio.greetings import get_wake_greeting, play_wake_greeting, warmup_wake_greetings
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
        self.turn_counter = 0

        # System tray
        self.enable_tray = enable_tray
        self.tray = None
        if self.enable_tray:
            try:
                from jarvis.ui.tray import JarvisTray
                self.tray = JarvisTray(
                    on_quit=self.stop,
                    get_status_fn=lambda: self.state.value,
                    on_reload=self.reload_configuration,
                )
            except Exception as e:
                logger.warning("Could not initialize system tray: %s", e)

        # Link kill switch to speech and task cancellation
        set_kill_callback(self._on_kill_switch)

    def reload_configuration(self) -> None:
        """Reloads runtime configuration from disk without restarting."""
        from jarvis.config import reload_config
        reload_config()
        self.wake_detector.reload_settings()
        logger.info("JarvisApp: Configuration and wake word settings reloaded.")

    def _set_state(self, new_state: AppState, message: str = "", query: str = "") -> None:
        """Updates internal state and informs UI callback."""
        with self.state_lock:
            self.state = new_state
            logger.info("Jarvis State -> %s %s", new_state.value, f'({message})' if message else '')
            if self.ui_callback:
                try:
                    import inspect
                    sig = inspect.signature(self.ui_callback)
                    if len(sig.parameters) >= 3:
                        self.ui_callback(new_state.value, message, query)
                    else:
                        self.ui_callback(new_state.value, message)
                except Exception as e:
                    logger.warning("UI callback error: %s", e)

    def wake(self) -> None:
        """Triggers wake listening cycle (e.g. from UI click or shortcut)."""
        self._on_wake_detected()

    def dismiss_to_idle(self) -> None:
        """Dismisses any active action/speech and resets state cleanly to IDLE."""
        with self.state_lock:
            self.turn_counter += 1
        cancel_current_task()
        stop_speech()
        self.wake_detector.reset()
        mic_stream.resume_wakeword()
        self._set_state(AppState.IDLE)
        logger.info("Jarvis dismissed to IDLE by user.")

    def _on_kill_switch(self) -> None:
        """Handles emergency kill switch (Ctrl+Alt+J)."""
        logger.warning("Emergency kill switch engaged in state: %s", self.state.value)
        with self.state_lock:
            self.turn_counter += 1
        cancel_current_task()
        stop_speech()
        self._set_state(AppState.IDLE, "Stopped")
        speak("Stopped.", block=False)
        mic_stream.resume_wakeword()

    def _on_wake_detected(self) -> None:
        """Triggered when wake word is detected; interrupts any in-progress task and listens."""
        if self.state == AppState.PAUSED:
            return

        with self.state_lock:
            # If Jarvis is currently working on something (speaking, thinking/processing, confirming)
            if self.state in (AppState.PROCESSING, AppState.SPEAKING, AppState.CONFIRMING):
                logger.info(
                    "Wake word detected while working on a task in state %s. Interrupting current action and listening for new command...",
                    self.state.value,
                )
                cancel_current_task()
                stop_speech()
            elif self.state == AppState.LISTENING:
                # Already actively recording speech
                return

            self.turn_counter += 1
            turn_id = self.turn_counter

        # Reset wake detector internal state so it doesn't trigger on residual sound
        self.wake_detector.reset()

        logger.info("Wake word detected! Entering LISTENING state (Turn #%d).", turn_id)
        # Start voice processing cycle in worker thread so detector stays responsive
        self.worker_thread = threading.Thread(
            target=self._process_voice_turn,
            args=(turn_id, False),
            daemon=True,
            name=f"VoiceWorker-{turn_id}",
        )
        self.worker_thread.start()

    def _process_voice_turn(self, turn_id: int | None = None, is_followup: bool = False) -> None:
        """Records speech, transcribes, invokes agent loop, and speaks response."""
        if turn_id is None:
            with self.state_lock:
                self.turn_counter += 1
                turn_id = self.turn_counter

        reset_cancel_event()
        self._set_state(AppState.LISTENING, "Listening...")

        if not is_followup:
            greeting = get_wake_greeting()
            self._set_state(AppState.LISTENING, greeting)

            def _play_greeting() -> None:
                try:
                    play_wake_greeting(greeting, block=True)
                except Exception as e:
                    logger.debug("Wake greeting playback failed: %s", e)

            greeting_thread = threading.Thread(
                target=_play_greeting,
                daemon=True,
                name=f"WakeGreetingPlayback-{turn_id}",
            )
            greeting_thread.start()

            def _on_speech_started() -> None:
                logger.info("User speech detected during greeting; interrupting greeting playback immediately.")
                stop_speech()
                if turn_id == self.turn_counter and not is_task_cancelled():
                    self._set_state(AppState.LISTENING, "Listening...")

            audio_samples = mic_stream.record_until_silence(on_speech_start=_on_speech_started)
            stop_speech()  # Ensure greeting audio is silenced when recording finishes
        else:
            audio_samples = mic_stream.record_until_silence()

        end_of_speech_time = time.perf_counter()

        # Check if cancelled or superseded during recording
        if turn_id != self.turn_counter or is_task_cancelled():
            return

        if audio_samples is None or len(audio_samples) == 0:
            logger.info("Empty audio recording. Returning to IDLE.")
            play_error_sound(block=True)
            self.wake_detector.reset()
            mic_stream.resume_wakeword()
            self._set_state(AppState.IDLE)
            return

        # Reset wake detector internal state so barge-in only triggers on new wake words
        self.wake_detector.reset()
        mic_stream.resume_wakeword()

        self._set_state(AppState.PROCESSING, "Transcribing...")
        user_text = transcribe(audio_samples)
        if not user_text.strip():
            logger.info("Transcription yielded empty text. Returning to IDLE.")
            self.wake_detector.reset()
            mic_stream.resume_wakeword()
            self._set_state(AppState.IDLE)
            return

        if turn_id != self.turn_counter or is_task_cancelled():
            return

        logger.info("Transcribed User Speech: '%s'", user_text)
        self._set_state(AppState.PROCESSING, f"Thinking: '{user_text}'")

        # Execute agent loop
        def agent_progress(status: str) -> None:
            if turn_id == self.turn_counter and not is_task_cancelled():
                self._set_state(AppState.PROCESSING, status)

        reply = run_task(user_text, ui_callback=agent_progress)

        # Check for cancellation before speaking
        if turn_id != self.turn_counter or is_task_cancelled():
            logger.info("Task cancelled or superseded before speaking.")
            return

        # Log measured latency from speech end to response generation
        speech_to_reply_latency = time.perf_counter() - end_of_speech_time
        logger.info(
            "Measured turnaround latency (end-of-speech to start-of-reply): %.2fs",
            speech_to_reply_latency,
        )
        print(f"\n[Turnaround Latency]: {speech_to_reply_latency:.2f}s | Jarvis: {reply}\n")

        # Speak response (ensure wakeword remains active for barge-in)
        self._set_state(AppState.SPEAKING, reply, query=user_text)
        self.wake_detector.reset()
        mic_stream.resume_wakeword()
        try:
            speak(reply, block=True)
            if turn_id == self.turn_counter and not is_task_cancelled():
                play_done_sound(block=False)
        finally:
            self.wake_detector.reset()
            mic_stream.resume_wakeword()

        if turn_id != self.turn_counter or is_task_cancelled():
            return

        # Support follow-up questions
        if reply.strip().endswith("?"):
            logger.info("Reply ended with question mark. Initiating automatic follow-up listening.")
            self._process_voice_turn(turn_id, is_followup=True)
        else:
            with self.state_lock:
                self.state = AppState.IDLE
            self.wake_detector.reset()
            mic_stream.resume_wakeword()
            logger.info("Jarvis turn complete. Answer card displayed; ready for wake word or Esc.")

    def start(self) -> None:
        """Starts microphone stream, kill switch, wake word detector, and state machine."""
        if self.running:
            return
        self.running = True

        logger.info("Starting Jarvis Voice Application...")
        mic_stream.start()
        start_killswitch()
        self.wake_detector.start()
        warmup_wake_greetings()
        if self.tray:
            try:
                self.tray.start()
            except Exception as e:
                logger.warning("Could not start tray: %s", e)
        phrase = self.wake_detector.raw_phrase or "Hey Jarvis"
        self._set_state(AppState.IDLE, f"Ready. Say '{phrase}'")

        print("=" * 60)
        print(" Jarvis Voice Assistant Running")
        print(f" Wake phrase: '{phrase}' | Kill Switch: Ctrl+Alt+J")
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
