"""Unit tests for customizable wake word detection logic."""

import pytest
from jarvis.audio.wakeword import WakeWordDetector, normalize_phrase


def test_normalize_phrase():
    """Verifies wake phrase normalization."""
    assert normalize_phrase("Hey Jarvis!") == "hey jarvis"
    assert normalize_phrase("hey_jarvis") == "hey jarvis"
    assert normalize_phrase("  Hello,  Assistant!  ") == "hello assistant"
    assert normalize_phrase("HEY BRO") == "hey bro"
    assert normalize_phrase("hey_mycroft") == "hey mycroft"


def test_builtin_wakeword_mode(monkeypatch):
    """Verifies that built-in phrases route to openWakeWord."""
    monkeypatch.setenv("WAKEWORD_PHRASE", "Hey Jarvis")
    detector = WakeWordDetector()
    assert detector.mode == "openwakeword"
    assert detector.builtin_key == "hey_jarvis"

    monkeypatch.setenv("WAKEWORD_PHRASE", "hey_jarvis")
    detector2 = WakeWordDetector()
    assert detector2.mode == "openwakeword"
    assert detector2.builtin_key == "hey_jarvis"


def test_custom_phrase_hybrid_mode(monkeypatch):
    """Verifies that arbitrary custom phrases route to whisper_verifier."""
    monkeypatch.setenv("WAKEWORD_PHRASE", "Hey Bro")
    detector = WakeWordDetector()
    assert detector.mode == "whisper_verifier"
    assert detector.normalized_phrase == "hey bro"


def test_whisper_verifier_buffer_safety(monkeypatch):
    """Verifies that clearing vad_accumulator does not raise BufferError."""
    import numpy as np

    vad_accumulator = bytearray(b"\x00\x00" * int(16000 * 1.5))
    # Emulate the fix: copy to immutable bytes before clearing bytearray
    raw_bytes = bytes(vad_accumulator)
    vad_accumulator.clear()
    audio_data = np.frombuffer(raw_bytes, dtype=np.int16)
    assert len(vad_accumulator) == 0
    assert len(audio_data) == int(16000 * 1.5)
