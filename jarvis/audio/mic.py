"""Microphone audio input stream and Voice Activity Detection (VAD) recording."""

import collections
import queue
import time
from typing import Any
import numpy as np
import sounddevice as sd
import webrtcvad

from jarvis.config import config
from jarvis.logger import logger

SAMPLE_RATE = 16000
FRAME_DURATION_MS = 30  # 30ms frames
FRAME_SIZE = int(SAMPLE_RATE * (FRAME_DURATION_MS / 1000.0))  # 480 samples


class MicrophoneStream:
    """Manages a single persistent SoundDevice InputStream feeding VAD and wake detectors."""

    def __init__(self) -> None:
        self.stream: sd.InputStream | None = None
        self.wakeword_queue: queue.Queue[bytes] = queue.Queue(maxsize=100)
        self.record_queue: queue.Queue[bytes] = queue.Queue(maxsize=1000)

        self.wakeword_paused = False
        self.is_recording = False

        audio_cfg = config.get("audio", {})
        aggressiveness = audio_cfg.get("vad_aggressiveness", 2)
        self.vad = webrtcvad.Vad(int(aggressiveness))

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info: Any, status: sd.CallbackFlags) -> None:
        """Called by PortAudio for every 30ms audio block."""
        if status:
            logger.warning("Microphone stream status: %s", status)

        raw_bytes = indata.tobytes()

        # Push to recording queue if recording is in progress
        if self.is_recording:
            try:
                self.record_queue.put_nowait(raw_bytes)
            except queue.Full:
                pass

        # Push to wake word queue if listener is not paused
        if not self.wakeword_paused and not self.is_recording:
            try:
                self.wakeword_queue.put_nowait(raw_bytes)
            except queue.Full:
                pass

    def start(self) -> None:
        """Starts the persistent microphone input stream."""
        if self.stream is not None and self.stream.active:
            return

        audio_cfg = config.get("audio", {})
        input_device = audio_cfg.get("input_device")

        try:
            self.stream = sd.InputStream(
                device=input_device,
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=FRAME_SIZE,
                callback=self._audio_callback,
            )
            self.stream.start()
            logger.info("Microphone stream started (16kHz mono int16, 30ms frames).")
        except Exception as e:
            logger.error("Failed to start microphone stream: %s", e)
            raise e

    def stop(self) -> None:
        """Stops and closes the microphone input stream."""
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
            logger.info("Microphone stream stopped.")

    def pause_wakeword(self) -> None:
        """Pauses audio dispatch to the wake word detector."""
        self.wakeword_paused = True
        # Drain any leftover frames
        while not self.wakeword_queue.empty():
            try:
                self.wakeword_queue.get_nowait()
            except queue.Empty:
                break

    def resume_wakeword(self) -> None:
        """Resumes audio dispatch to the wake word detector."""
        # Drain stale frames before resuming
        while not self.wakeword_queue.empty():
            try:
                self.wakeword_queue.get_nowait()
            except queue.Empty:
                break
        self.wakeword_paused = False

    def record_until_silence(self) -> np.ndarray:
        """Waits for user speech to start (up to 6s) and records until silence or max limit.

        Returns:
            1D numpy array of int16 samples or empty array if no speech detected.
        """
        self.pause_wakeword()
        self.is_recording = True

        # Clear recording queue
        while not self.record_queue.empty():
            try:
                self.record_queue.get_nowait()
            except queue.Empty:
                break

        audio_cfg = config.get("audio", {})
        silence_sec = audio_cfg.get("silence_seconds", 1.2)
        max_sec = audio_cfg.get("max_record_seconds", 20.0)

        silence_threshold_frames = int(silence_sec / (FRAME_DURATION_MS / 1000.0))
        max_record_frames = int(max_sec / (FRAME_DURATION_MS / 1000.0))

        # Ring buffer for ~300ms pre-speech audio capture
        pre_buffer_size = 10
        pre_buffer: collections.deque[bytes] = collections.deque(maxlen=pre_buffer_size)

        recorded_frames: list[bytes] = []
        speech_started = False
        consecutive_silence = 0
        wait_start_time = time.time()

        try:
            while True:
                # 6-second timeout waiting for speech to begin
                if not speech_started and (time.time() - wait_start_time) > 6.0:
                    logger.info("No speech detected within 6 seconds.")
                    break

                try:
                    frame_bytes = self.record_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                is_speech = self.vad.is_speech(frame_bytes, SAMPLE_RATE)

                if not speech_started:
                    pre_buffer.append(frame_bytes)
                    if is_speech:
                        speech_started = True
                        recorded_frames.extend(pre_buffer)
                        logger.info("Speech detected, recording command...")
                else:
                    recorded_frames.append(frame_bytes)
                    if not is_speech:
                        consecutive_silence += 1
                        if consecutive_silence >= silence_threshold_frames:
                            logger.info("Silence detected (%0.1fs), stopping recording.", silence_sec)
                            break
                    else:
                        consecutive_silence = 0

                    if len(recorded_frames) >= max_record_frames:
                        logger.info("Max record duration (%0.1fs) reached, stopping.", max_sec)
                        break

        finally:
            self.is_recording = False
            self.resume_wakeword()

        if not recorded_frames or not speech_started:
            return np.array([], dtype=np.int16)

        # Combine all frames into a single int16 array
        combined_bytes = b"".join(recorded_frames)
        return np.frombuffer(combined_bytes, dtype=np.int16)


# Global microphone stream instance
mic_stream = MicrophoneStream()
