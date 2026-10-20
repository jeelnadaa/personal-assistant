"""Unit tests for customizable wake word detection logic."""

import pytest
from jarvis.audio.wakeword import WakeWordDetector, normalize_phrase


def test_normalize_phrase():
    """Verifies wake phrase normalization."""
    assert normalize_phrase("Hey Jarvis!") == "hey jarvis"
    assert normalize_phrase("  Hello, Assistant!  ") == "hello assistant"
    assert normalize_phrase("HEY BRO") == "hey bro"


def test_builtin_wakeword_mode(monkeypatch):
    """Verifies that built-in phrases route to openWakeWord."""
    monkeypatch.setenv("WAKEWORD_PHRASE", "Hey Jarvis")
    detector = WakeWordDetector()
    assert detector.mode == "openwakeword"
    assert detector.builtin_key == "hey_jarvis"


def test_custom_phrase_hybrid_mode(monkeypatch):
    """Verifies that arbitrary custom phrases route to whisper_verifier."""
    monkeypatch.setenv("WAKEWORD_PHRASE", "Hey Bro")
    detector = WakeWordDetector()
    assert detector.mode == "whisper_verifier"
    assert detector.normalized_phrase == "hey bro"
