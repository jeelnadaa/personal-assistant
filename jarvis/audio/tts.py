"""Text-to-speech output pipeline with local Piper neural TTS and Edge-TTS/pyttsx3 fallbacks."""

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

from jarvis.audio import piper_tts
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
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    cleaned = re.sub(r"https?://\S+|www\.\S+", "", cleaned)
    cleaned = re.sub(r"[*_#`~>\[\]()]", "", cleaned)
    cleaned = re.sub(r"^\s*[-*•]\s*", "", cleaned, flags=re.MULTILINE)
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


def _speak_with_piper(text: str, block: bool) -> bool:
    """Synthesizes and plays speech using local offline Piper neural voice."""
    tts_cfg = config.get("tts", {})
    voice = os.getenv("TTS_PIPER_VOICE") or os.getenv("PIPER_VOICE", tts_cfg.get("piper_voice", "en_GB-alan-medium"))
    speed = float(os.getenv("TTS_SPEED", tts_cfg.get("speed", 1.0)))

    try:
        audio_data, sample_rate = piper_tts.synthesize_audio(text, voice_name=voice, speed_factor=speed)
        if audio_data is None or len(audio_data) == 0:
            return False

        if not _TTS_STOP_EVENT.is_set():
            sd.play(audio_data, samplerate=sample_rate, blocking=block)
        return True
    except Exception as e:
        logger.warning("Piper local TTS failed (%s); falling back...", e)
        return False


def _speak_with_edge(text: str, block: bool) -> bool:
    """Synthesizes and plays speech using Microsoft Edge online neural TTS."""
    voice = os.getenv("TTS_EDGE_VOICE", "en-GB-RyanNeural")

    # Natural conversational speed (defaults to +15% / 1.15x)
    rate_env = os.getenv("TTS_EDGE_RATE")
    if rate_env and rate_env != "-4%":
        rate = rate_env
    else:
        speed = float(os.getenv("TTS_SPEED", config.get("tts", {}).get("speed", 1.15)))
        pct = int(round((speed - 1.0) * 100))
        rate = f"+{pct}%" if pct >= 0 else f"{pct}%"

    pitch_env = os.getenv("TTS_EDGE_PITCH")
    pitch = pitch_env if (pitch_env and pitch_env != "-6Hz") else "0Hz"

    temp_mp3 = Path(tempfile.gettempdir()) / f"jarvis_tts_{os.getpid()}_{id(text)}.mp3"
    try:
        asyncio.run(_generate_edge_tts_mp3(text, voice, rate, pitch, temp_mp3))
        if temp_mp3.exists() and temp_mp3.stat().st_size > 0:
            decoded = miniaudio.mp3_read_file_f32(str(temp_mp3))
            audio_data = np.array(decoded.samples, dtype=np.float32)
            if decoded.nchannels > 1:
                audio_data = audio_data.reshape(-1, decoded.nchannels)

            if not _TTS_STOP_EVENT.is_set():
                sd.play(audio_data, samplerate=decoded.sample_rate, blocking=block)
            return True
    except Exception as e:
        logger.warning("Edge-TTS failed (%s); falling back...", e)
        return False
    finally:
        if temp_mp3.exists():
            try:
                temp_mp3.unlink()
            except Exception:
                pass
    return False


def speak(text: str, block: bool = True) -> None:
    """Speaks text aloud using the configured primary TTS engine with fallbacks.

    Priority order when provider is 'piper' (default):
    1. Piper local neural voice (100% offline)
    2. Edge-TTS online neural voice (free cloud)
    3. pyttsx3 SAPI5 (offline fallback)

    Args:
        text: The text string to read aloud.
        block: Whether to wait until speech playback completes.
    """
    clean_text = clean_text_for_speech(text)
    if not clean_text:
        return

    _TTS_STOP_EVENT.clear()
    provider = os.getenv("TTS_PROVIDER", config.get("tts", {}).get("provider", "piper")).strip().lower()

    with _TTS_LOCK:
        succeeded = False

        if provider in ("edge", "cloud"):
            succeeded = _speak_with_edge(clean_text, block=block)
            if not succeeded and not _TTS_STOP_EVENT.is_set():
                succeeded = _speak_with_piper(clean_text, block=block)
        elif provider == "piper":
            succeeded = _speak_with_piper(clean_text, block=block)
            if not succeeded and not _TTS_STOP_EVENT.is_set():
                succeeded = _speak_with_edge(clean_text, block=block)

        # Emergency fallback: pyttsx3 Windows SAPI5
        if not succeeded and not _TTS_STOP_EVENT.is_set():
            engine = _get_pyttsx3_engine()
            if engine:
                try:
                    engine.say(clean_text)
                    engine.runAndWait()
                except Exception as pyttsx_err:
                    logger.error("Pyttsx3 speech synthesis fallback failed: %s", pyttsx_err)


def get_tts_info() -> dict[str, Any]:
    """Returns diagnostics for active TTS configuration and available Piper voices."""
    provider = os.getenv("TTS_PROVIDER", config.get("tts", {}).get("provider", "piper")).strip().lower()
    return {
        "provider": provider,
        "piper_voice": os.getenv("TTS_PIPER_VOICE") or os.getenv("PIPER_VOICE", "en_GB-alan-medium"),
        "edge_voice": os.getenv("TTS_EDGE_VOICE", "en-GB-RyanNeural"),
        "available_piper_voices": piper_tts.get_available_voices(),
    }
