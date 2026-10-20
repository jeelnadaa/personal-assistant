"""Text-to-speech output pipeline with edge-tts and pyttsx3 fallback."""

import asyncio
import os
from pathlib import Path
import re
import tempfile
import threading
from typing import Any
import miniaudio
import numpy as np
import pyttsx3
import sounddevice as sd

from jarvis.config import config
from jarvis.logger import logger

_TTS_STOP_EVENT = threading.Event()
_PYTTSX3_ENGINE: Any = None
_TTS_LOCK = threading.Lock()


def _get_pyttsx3_engine() -> Any:
    """Lazily initializes the offline SAPI5 pyttsx3 engine."""
    global _PYTTSX3_ENGINE
    if _PYTTSX3_ENGINE is None:
        try:
            _PYTTSX3_ENGINE = pyttsx3.init("sapi5")
            _PYTTSX3_ENGINE.setProperty("rate", 185)
        except Exception as e:
            logger.warning("Could not initialize pyttsx3 engine: %s", e)
    return _PYTTSX3_ENGINE


def clean_text_for_speech(text: str) -> str:
    """Removes URLs, markdown syntax, and extraneous punctuation for clear speech."""
    # 1. Convert markdown links [text](url) -> text
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # 2. Remove bare URLs
    cleaned = re.sub(r"https?://\S+|www\.\S+", "", cleaned)
    # 3. Remove markdown formatting characters
    cleaned = re.sub(r"[*_#`~>\[\]()]", "", cleaned)
    # 4. Remove bullet dashes/asterisks at start of lines
    cleaned = re.sub(r"^\s*[-*•]\s*", "", cleaned, flags=re.MULTILINE)
    # 5. Clean whitespace before punctuation
    cleaned = re.sub(r"\s+([.,!?])", r"\1", cleaned)
    cleaned = " ".join(cleaned.split())
    return cleaned.strip()


def stop() -> None:
    """Interrupts any currently playing speech immediately."""
    _TTS_STOP_EVENT.set()
    try:
        sd.stop()
    except Exception:
        pass
    if _PYTTSX3_ENGINE:
        try:
            _PYTTSX3_ENGINE.stop()
        except Exception:
            pass


async def _generate_edge_tts_mp3(text: str, voice: str, rate: str, pitch: str, output_path: Path) -> None:
    """Generates an MP3 file using edge-tts."""
    import edge_tts
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
    await communicate.save(str(output_path))


def speak(text: str, block: bool = True) -> None:
    """Speaks text aloud using Edge-TTS or PyTTSx3 fallback.

    Args:
        text: The text string to read aloud.
        block: Whether to wait until speech playback completes.
    """
    clean_text = clean_text_for_speech(text)
    if not clean_text:
        return

    _TTS_STOP_EVENT.clear()

    voice = os.getenv("TTS_EDGE_VOICE", "en-GB-RyanNeural")
    rate = os.getenv("TTS_EDGE_RATE", "-4%")
    pitch = os.getenv("TTS_EDGE_PITCH", "-6Hz")

    with _TTS_LOCK:
        # Strategy 1: Edge-TTS + miniaudio + sounddevice
        edge_succeeded = False
        temp_mp3 = Path(tempfile.gettempdir()) / f"jarvis_tts_{os.getpid()}_{id(text)}.mp3"

        try:
            asyncio.run(_generate_edge_tts_mp3(clean_text, voice, rate, pitch, temp_mp3))
            if temp_mp3.exists() and temp_mp3.stat().st_size > 0:
                decoded = miniaudio.mp3_read_file_f32(str(temp_mp3))
                audio_data = np.array(decoded.samples, dtype=np.float32)
                if decoded.nchannels > 1:
                    audio_data = audio_data.reshape(-1, decoded.nchannels)

                if not _TTS_STOP_EVENT.is_set():
                    sd.play(audio_data, samplerate=decoded.sample_rate, blocking=block)
                edge_succeeded = True
        except Exception as edge_err:
            logger.info("Edge-TTS unavailable or failed (%s); switching to pyttsx3 fallback", edge_err)
        finally:
            if temp_mp3.exists():
                try:
                    temp_mp3.unlink()
                except Exception:
                    pass

        # Strategy 2: pyttsx3 offline fallback
        if not edge_succeeded and not _TTS_STOP_EVENT.is_set():
            engine = _get_pyttsx3_engine()
            if engine:
                try:
                    engine.say(clean_text)
                    engine.runAndWait()
                except Exception as pyttsx_err:
                    logger.error("Pyttsx3 speech synthesis failed: %s", pyttsx_err)
