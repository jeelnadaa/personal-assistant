"""Wake word detection engine using openWakeWord."""

import queue
import threading
import time
from typing import Callable
import numpy as np

from jarvis.audio.mic import mic_stream
from jarvis.config import config
from jarvis.logger import logger

CHUNK_SIZE = 1280  # 80ms at 16kHz


class WakeWordDetector:
    """Detects wake words (e.g. 'hey jarvis') on microphone audio stream using openWakeWord."""

    def __init__(self, on_detect: Callable[[], None] | None = None) -> None:
        self.on_detect = on_detect
        self.running = False
        self.thread: threading.Thread | None = None

        ww_cfg = config.get("wakeword", {})
        self.phrase = ww_cfg.get("phrase", "hey_jarvis")
        self.threshold = float(ww_cfg.get("threshold", 0.5))
        self.cooldown = float(ww_cfg.get("cooldown_seconds", 2.0))
        self.last_detection_time = 0.0

        self.model = None

    def _ensure_model(self) -> None:
        """Downloads required wake word models if not present and initializes Model."""
        if self.model is not None:
            return

        from openwakeword.model import Model
        from openwakeword.utils import download_models

        try:
            logger.info("Initializing wake word detector for '%s'...", self.phrase)
            self.model = Model(wakeword_models=[self.phrase])
        except Exception:
            logger.info("Model not found locally; downloading '%s'...", self.phrase)
            download_models([self.phrase])
            self.model = Model(wakeword_models=[self.phrase])

    def _detect_loop(self) -> None:
        """Continuously reads audio from mic_stream.wakeword_queue and checks for wake word."""
        self._ensure_model()
        sample_buffer = bytearray()

        while self.running:
            try:
                frame_bytes = mic_stream.wakeword_queue.get(timeout=0.1)
                sample_buffer.extend(frame_bytes)
            except queue.Empty:
                continue

            # Process in 80ms (1280 samples = 2560 bytes) chunks
            while len(sample_buffer) >= (CHUNK_SIZE * 2):
                chunk_bytes = sample_buffer[: CHUNK_SIZE * 2]
                del sample_buffer[: CHUNK_SIZE * 2]

                audio_chunk = np.frombuffer(chunk_bytes, dtype=np.int16)
                try:
                    prediction = self.model.predict(audio_chunk)
                    # Extract prediction score for active model
                    for model_name, score in prediction.items():
                        if score >= self.threshold:
                            now = time.time()
                            if now - self.last_detection_time >= self.cooldown:
                                self.last_detection_time = now
                                logger.info(
                                    "Wake word detected ('%s', score: %.3f)",
                                    model_name,
                                    score,
                                )
                                if self.on_detect:
                                    try:
                                        self.on_detect()
                                    except Exception as cb_err:
                                        logger.error("Error in wake word callback: %s", cb_err)
                                break
                except Exception as p_err:
                    logger.error("Wake word prediction error: %s", p_err)

    def start(self) -> None:
        """Starts the wake word detector thread."""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._detect_loop, daemon=True, name="WakeWordDetector")
        self.thread.start()
        logger.info("Wake word detector started.")

    def stop(self) -> None:
        """Stops the wake word detector thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
            self.thread = None
        logger.info("Wake word detector stopped.")
