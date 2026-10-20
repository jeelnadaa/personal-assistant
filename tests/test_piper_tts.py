"""Unit tests for Piper local neural TTS synthesis."""

from pathlib import Path
import numpy as np
import pytest

from jarvis.audio import piper_tts
from jarvis.audio.tts import clean_text_for_speech, get_tts_info


def test_clean_text_for_speech():
    """Verifies that markdown, links, and asterisks are stripped from speech text."""
    raw = "Hello **world**! Check [my site](https://example.com) for details. * Bullet point."
    cleaned = clean_text_for_speech(raw)
    assert "https://example.com" not in cleaned
    assert "my site" in cleaned
    assert "**" not in cleaned
    assert "Bullet point" in cleaned


def test_piper_voice_discovery():
    """Verifies that downloaded Piper voices are detected."""
    voices = piper_tts.get_available_voices()
    assert isinstance(voices, list)
    assert "en_GB-alan-medium" in voices


def test_piper_synthesize_audio():
    """Verifies that Piper synthesizes float32 audio samples."""
    audio_data, sample_rate = piper_tts.synthesize_audio("Jarvis system check.", voice_name="en_GB-alan-medium")
    assert audio_data is not None
    assert isinstance(audio_data, np.ndarray)
    assert audio_data.dtype == np.float32
    assert len(audio_data) > 0
    assert sample_rate == 22050


def test_get_tts_info():
    """Verifies that TTS diagnostics dictionary is populated."""
    info = get_tts_info()
    assert "provider" in info
    assert "available_piper_voices" in info
    assert "en_GB-alan-medium" in info["available_piper_voices"]
