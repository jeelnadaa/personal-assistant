"""Wake-up spoken greeting generation, caching, and playback for Jarvis."""

import hashlib
import os
from pathlib import Path
import random
import threading
from typing import Sequence
import miniaudio
import numpy as np
import sounddevice as sd

from jarvis.audio import tts
from jarvis.config import BASE_DIR, config
from jarvis.logger import logger

# Hardcoded wake greeting templates
GREETINGS_WITH_HONORIFIC: list[str] = [
    "Yes {honorific}, how can I help you?",
    "At your service, {honorific}. What can I do for you?",
    "Yes {honorific}, I'm listening.",
    "Online and ready, {honorific}. What do you need?",
    "Right here, {honorific}. How can I assist you?",
    "Yes {honorific}, what's on your mind?",
    "At your command, {honorific}.",
]

GREETINGS_CASUAL: list[str] = [
    "Yes, how can I help you?",
    "At your service. What can I do for you?",
    "I'm listening. What do you need?",
    "Online and ready. How can I assist you?",
    "Right here. What's on your mind?",
    "Yes, what can I do for you?",
]


def get_greeting_cache_dir() -> Path:
    """Returns the directory used for pre-cached wake greeting audio files."""
    cache_dir = BASE_DIR / "data" / "tts_cache" / "greetings"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def get_wake_greeting() -> str:
    """Returns a randomly selected wake-up greeting tailored to the configured honorific or user name."""
    persona_cfg = config.get("persona", {})
    honorific = os.getenv("HONORIFIC")
    if honorific is None:
        honorific = persona_cfg.get("honorific", "")
    honorific = honorific.strip()

    if honorific:
        template = random.choice(GREETINGS_WITH_HONORIFIC)
        return template.format(honorific=honorific)

    user_name = os.getenv("USER_NAME")
    if user_name is None:
        user_name = persona_cfg.get("user_name", "")
    user_name = user_name.strip()
    if user_name:
        template = random.choice(GREETINGS_WITH_HONORIFIC)
        return template.format(honorific=user_name)

    return random.choice(GREETINGS_CASUAL)


def get_all_active_greetings() -> list[str]:
    """Returns all greeting phrases configured for the active persona."""
    persona_cfg = config.get("persona", {})
    honorific = os.getenv("HONORIFIC")
    if honorific is None:
        honorific = persona_cfg.get("honorific", "")
    honorific = honorific.strip()
    if honorific:
        return [t.format(honorific=honorific) for t in GREETINGS_WITH_HONORIFIC]

    user_name = os.getenv("USER_NAME")
    if user_name is None:
        user_name = persona_cfg.get("user_name", "")
    user_name = user_name.strip()
    if user_name:
        return [t.format(honorific=user_name) for t in GREETINGS_WITH_HONORIFIC]

    return list(GREETINGS_CASUAL)


def _get_cache_path(greeting: str) -> Path:
    """Computes a deterministic cache file path based on greeting text, provider, and voice."""
    tts_prov = os.getenv("TTS_PROVIDER", config.get("tts", {}).get("provider", "edge")).strip().lower()
    voice = os.getenv("TTS_EDGE_VOICE", "en-GB-RyanNeural") if tts_prov in ("edge", "cloud") else os.getenv("TTS_PIPER_VOICE", "en_GB-alan-medium")
    key = f"{tts_prov}:{voice}:{greeting}"
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()[:16]
    return get_greeting_cache_dir() / f"greet_{digest}.mp3"


def play_wake_greeting(greeting: str, block: bool = True) -> bool:
    """Plays the wake greeting using fast cached audio or on-demand synthesis with interruption support.

    Args:
        greeting: Spoken greeting text.
        block: Whether to wait until speech playback completes.

    Returns:
        True if greeting played successfully, False otherwise.
    """
    cache_path = _get_cache_path(greeting)
    tts._TTS_STOP_EVENT.clear()

    # Try fast-path cached audio playback (<10ms latency)
    if cache_path.exists() and cache_path.stat().st_size > 0:
        try:
            decoded = miniaudio.mp3_read_file_f32(str(cache_path))
            audio_data = np.array(decoded.samples, dtype=np.float32)
            if decoded.nchannels > 1:
                audio_data = audio_data.reshape(-1, decoded.nchannels)

            if not tts._TTS_STOP_EVENT.is_set():
                sd.play(audio_data, samplerate=decoded.sample_rate, blocking=False)
                if block:
                    while sd.get_stream() and sd.get_stream().active:
                        if tts._TTS_STOP_EVENT.is_set():
                            sd.stop()
                            break
                        import time
                        time.sleep(0.01)
                return True
        except Exception as e:
            logger.debug("Cached greeting playback failed (%s); falling back to tts.speak", e)

    # Fallback: regular speech synthesis
    tts.speak(greeting, block=block)
    return True


def warmup_wake_greetings() -> None:
    """Background task to pre-synthesize and cache greeting audio for near-instant wake response."""
    def _worker() -> None:
        tts_prov = os.getenv("TTS_PROVIDER", config.get("tts", {}).get("provider", "edge")).strip().lower()
        if tts_prov not in ("edge", "cloud"):
            return  # Piper is already local; edge-tts benefits most from pre-caching

        import asyncio
        import edge_tts

        voice = os.getenv("TTS_EDGE_VOICE", "en-GB-RyanNeural")
        rate = os.getenv("TTS_EDGE_RATE", "-4%")
        pitch = os.getenv("TTS_EDGE_PITCH", "-6Hz")

        for phrase in get_all_active_greetings():
            p = _get_cache_path(phrase)
            if not p.exists() or p.stat().st_size == 0:
                try:
                    temp_p = p.with_suffix(".tmp")
                    comm = edge_tts.Communicate(text=phrase, voice=voice, rate=rate, pitch=pitch)
                    asyncio.run(comm.save(str(temp_p)))
                    if temp_p.exists() and temp_p.stat().st_size > 0:
                        temp_p.replace(p)
                        logger.debug("Pre-cached wake greeting: '%s'", phrase)
                except Exception as e:
                    logger.debug("Failed pre-caching greeting '%s': %s", phrase, e)

    t = threading.Thread(target=_worker, daemon=True, name="GreetingWarmup")
    t.start()
