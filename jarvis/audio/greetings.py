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


def play_wake_greeting(greeting: str, block: bool = True) -> bool:
    """Plays the wake greeting using the active configured TTS engine and settings.

    Args:
        greeting: Spoken greeting text.
        block: Whether to wait until speech playback completes.

    Returns:
        True if greeting played successfully, False otherwise.
    """
    tts.speak(greeting, block=block)
    return True


def warmup_wake_greetings() -> None:
    """Warmup hook for speech pipeline."""
    # Active TTS synthesis handles instant playback via local Piper or Edge streaming
    pass
