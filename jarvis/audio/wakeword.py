"""Configurable wake word detection supporting openWakeWord models and custom phrases."""

import os
from pathlib import Path
import queue
import re
import threading
import time
from typing import Callable
import numpy as np

from jarvis.audio.mic import mic_stream
from jarvis.config import config
from jarvis.logger import logger

CHUNK_SIZE = 1280  # 80ms at 16kHz
OPENWAKEWORD_BUILTIN = {
    "hey_jarvis": "hey_jarvis",
    "hey jarvis": "hey_jarvis",
    "heyjarvis": "hey_jarvis",
    "alexa": "alexa",
    "hey_mycroft": "hey_mycroft",
    "hey mycroft": "hey_mycroft",
    "heymycroft": "hey_mycroft",
    "hey_rhasspy": "hey_rhasspy",
    "hey rhasspy": "hey_rhasspy",
    "heyrhasspy": "hey_rhasspy",
    "timer": "timer",
    "weather": "weather",
}


def normalize_phrase(phrase: str) -> str:
    """Normalizes a phrase string for matching by stripping symbols and unifying whitespace."""
    clean = re.sub(r"[^a-zA-Z0-9\s_]", "", phrase)
    clean = re.sub(r"[\s_]+", " ", clean)
    return clean.strip().lower()


class WakeWordDetector:
    """Detects configurable wake words (built-in openWakeWord or custom phrases)."""

    def __init__(self, on_detect: Callable[[], None] | None = None) -> None:
        self.on_detect = on_detect
        self.running = False
        self.thread: threading.Thread | None = None

        ww_cfg = config.get("wakeword", {})
        raw_phrase = os.getenv("WAKEWORD_PHRASE", ww_cfg.get("phrase", "hey_jarvis"))
        self.raw_phrase = raw_phrase.strip()
        self.normalized_phrase = normalize_phrase(self.raw_phrase)
        self.custom_model_path = os.getenv("WAKEWORD_MODEL_PATH", ww_cfg.get("custom_model_path", ""))

        self.threshold = float(os.getenv("WAKEWORD_THRESHOLD", ww_cfg.get("threshold", 0.6)))
        self.cooldown = float(ww_cfg.get("cooldown_seconds", 2.0))
        self.last_detection_time = 0.0
        self._lock = threading.Lock()
        self._reset_requested = False

        # Determine engine mode: 'openwakeword' (for pre-trained/custom onnx) or 'whisper_verifier' (for arbitrary custom phrase)
        self.builtin_key = OPENWAKEWORD_BUILTIN.get(self.normalized_phrase)
        if self.custom_model_path and Path(self.custom_model_path).exists():
            self.mode = "custom_onnx"
        elif self.builtin_key:
            self.mode = "openwakeword"
        else:
            self.mode = "whisper_verifier"

        self.model = None

    def reset(self) -> None:
        """Resets detector internal buffers, clears mic queue, and resets model recurrent states."""
        self._reset_requested = True
        # Drain the mic wakeword queue immediately
        while not mic_stream.wakeword_queue.empty():
            try:
                mic_stream.wakeword_queue.get_nowait()
            except queue.Empty:
                break
        with self._lock:
            if self.model and hasattr(self.model, "reset"):
                try:
                    self.model.reset()
                except Exception as e:
                    logger.debug("Error resetting openwakeword model recurrent state: %s", e)
            self.last_detection_time = time.time()

    def reload_settings(self) -> None:
        """Reloads wake word settings from updated environment and configuration."""
        ww_cfg = config.get("wakeword", {})
        raw_phrase = os.getenv("WAKEWORD_PHRASE", ww_cfg.get("phrase", "hey_jarvis"))
        self.raw_phrase = raw_phrase.strip()
        self.normalized_phrase = normalize_phrase(self.raw_phrase)
        self.custom_model_path = os.getenv("WAKEWORD_MODEL_PATH", ww_cfg.get("custom_model_path", ""))
        self.threshold = float(os.getenv("WAKEWORD_THRESHOLD", ww_cfg.get("threshold", 0.6)))
        self.builtin_key = OPENWAKEWORD_BUILTIN.get(self.normalized_phrase)

        if self.custom_model_path and Path(self.custom_model_path).exists():
            self.mode = "custom_onnx"
        elif self.builtin_key:
            self.mode = "openwakeword"
        else:
            self.mode = "whisper_verifier"

        with self._lock:
            self.model = None  # Recreated on next loop
        logger.info(
            "WakeWordDetector reloaded: phrase='%s', mode=%s, threshold=%.2f",
            self.raw_phrase,
            self.mode,
            self.threshold,
        )

    def _ensure_model(self) -> None:
        """Initializes openWakeWord model for built-in or custom ONNX models."""
        if self.mode == "whisper_verifier":
            # Two-stage verification will use the local STT service
            return

        if self.model is not None:
            return

        from openwakeword.model import Model
        from openwakeword.utils import download_models

        target = self.custom_model_path if self.mode == "custom_onnx" else self.builtin_key
        try:
            logger.info("Initializing openWakeWord model for '%s'...", target)
            self.model = Model(wakeword_models=[target])
        except Exception:
            if self.mode == "openwakeword":
                logger.info("Downloading openWakeWord model '%s'...", target)
                download_models([target])
                self.model = Model(wakeword_models=[target])
            else:
                raise

    def _detect_loop(self) -> None:
        """Continuously reads audio from mic_stream and evaluates wake condition."""
        self._ensure_model()
        sample_buffer = bytearray()
        vad_accumulator = bytearray()

        while self.running:
            with self._lock:
                if self._reset_requested:
                    self._reset_requested = False
                    sample_buffer.clear()
                    vad_accumulator.clear()
                    if self.model and hasattr(self.model, "reset"):
                        try:
                            self.model.reset()
                        except Exception:
                            pass
                    self.last_detection_time = time.time()

            try:
                frame_bytes = mic_stream.wakeword_queue.get(timeout=0.1)
                sample_buffer.extend(frame_bytes)
            except queue.Empty:
                continue

            with self._lock:
                if self._reset_requested:
                    self._reset_requested = False
                    sample_buffer.clear()
                    vad_accumulator.clear()
                    continue

                # Mode A: openWakeWord built-in or custom ONNX
                if self.mode in ("openwakeword", "custom_onnx") and self.model:
                    detected = False
                    while len(sample_buffer) >= (CHUNK_SIZE * 2):
                        chunk_bytes = bytes(sample_buffer[: CHUNK_SIZE * 2])
                        del sample_buffer[: CHUNK_SIZE * 2]

                        audio_chunk = np.frombuffer(chunk_bytes, dtype=np.int16)
                        try:
                            prediction = self.model.predict(audio_chunk)
                            for model_name, score in prediction.items():
                                if score >= self.threshold:
                                    now = time.time()
                                    if now - self.last_detection_time >= self.cooldown:
                                        self.last_detection_time = now
                                        logger.info("Wake word detected ('%s', score: %.3f)", model_name, score)
                                        detected = True
                                        sample_buffer.clear()
                                        vad_accumulator.clear()
                                        if hasattr(self.model, "reset"):
                                            try:
                                                self.model.reset()
                                            except Exception:
                                                pass
                                        self._trigger()
                                        break
                            if detected:
                                break
                        except Exception as p_err:
                            logger.error("Wake word prediction error: %s", p_err)

                # Mode B: Two-Stage Hybrid Verification for arbitrary phrases
                elif self.mode == "whisper_verifier":
                    while len(sample_buffer) >= (CHUNK_SIZE * 2):
                        chunk_bytes = bytes(sample_buffer[: CHUNK_SIZE * 2])
                        del sample_buffer[: CHUNK_SIZE * 2]
                        vad_accumulator.extend(chunk_bytes)

                        # When ~1.2s of speech is accumulated, verify with local whisper
                        if len(vad_accumulator) >= (16000 * 2 * 1.2):
                            raw_bytes = bytes(vad_accumulator)
                            vad_accumulator.clear()
                            audio_data = np.frombuffer(raw_bytes, dtype=np.int16)

                            # Only transcribe if audio has sufficient energy
                            if np.max(np.abs(audio_data)) > 700:
                                try:
                                    from jarvis.audio.stt import transcribe
                                    phrase_text = transcribe(audio_data)
                                    if phrase_text:
                                        norm_text = normalize_phrase(phrase_text)
                                        if self.normalized_phrase in norm_text:
                                            now = time.time()
                                            if now - self.last_detection_time >= self.cooldown:
                                                self.last_detection_time = now
                                                logger.info("Custom wake phrase verified: '%s'", phrase_text)
                                                sample_buffer.clear()
                                                vad_accumulator.clear()
                                                self._trigger()
                                                break
                                except Exception as e:
                                    logger.debug("Hybrid wake verification error: %s", e)

    def _trigger(self) -> None:
        """Executes detection callback safely."""
        if self.on_detect:
            try:
                self.on_detect()
            except Exception as cb_err:
                logger.error("Error in wake word callback: %s", cb_err)

    def start(self) -> None:
        """Starts the wake word detector thread."""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._detect_loop, daemon=True, name="WakeWordDetector")
        self.thread.start()
        logger.info("Wake word detector started for phrase '%s' (mode: %s).", self.raw_phrase, self.mode)

    def stop(self) -> None:
        """Stops the wake word detector thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
            self.thread = None
        logger.info("Wake word detector stopped.")
