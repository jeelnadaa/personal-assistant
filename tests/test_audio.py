"""Unit tests for the audio pipeline: sounds, TTS cleaning, STT format, and mic stream."""

from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from jarvis.audio.mic import MicrophoneStream
from jarvis.audio.sounds import _generate_tone, play_done_sound, play_error_sound, play_wake_sound
from jarvis.audio.stt import _audio_to_wav_bytes, transcribe
from jarvis.audio.tts import clean_text_for_speech, speak, stop as stop_speech


def test_sounds_tone_generation():
    """Verifies sine wave synthesis and envelope calculation."""
    wave = _generate_tone(440.0, 0.1, sample_rate=16000)
    assert len(wave) == 1600
    assert isinstance(wave, np.ndarray)
    assert wave.dtype == np.float32

    # Verify edge ramps (envelope prevents click)
    assert abs(wave[0]) < 0.05
    assert abs(wave[-1]) < 0.05


def test_sounds_playback_mock():
    """Verifies sound playback calls sounddevice.play."""
    with patch("sounddevice.play") as mock_play:
        play_wake_sound(block=False)
        assert mock_play.called

        play_done_sound(block=False)
        assert mock_play.called

        play_error_sound(block=False)
        assert mock_play.called


def test_tts_clean_text_for_speech():
    """Verifies stripping of URLs, markdown syntax, and extraneous characters."""
    sample = "Hello! Check https://github.com/project. Also **important** `code` [link](http://test.com)."
    cleaned = clean_text_for_speech(sample)
    assert "https://" not in cleaned
    assert "github.com" not in cleaned
    assert "**" not in cleaned
    assert "`" not in cleaned
    assert cleaned == "Hello! Check Also important code link."


def test_stt_silence_rejection():
    """Verifies transcribe returns empty string for silence or very short audio."""
    # Under 0.4 seconds of silence
    tiny_audio = np.zeros(2000, dtype=np.int16)
    res = transcribe(tiny_audio)
    assert res == ""

    # None audio
    assert transcribe(None) == ""


def test_stt_wav_bytes_conversion():
    """Verifies conversion of int16 numpy array to WAV buffer."""
    audio = np.zeros(16000, dtype=np.int16)
    buf = _audio_to_wav_bytes(audio, 16000)
    assert buf is not None
    assert buf.name == "audio.wav"
    assert len(buf.getvalue()) > 32000  # 16000 samples * 2 bytes + header


def test_mic_stream_pause_resume():
    """Verifies pause and resume toggles wakeword dispatch."""
    stream = MicrophoneStream()
    assert stream.wakeword_paused is False

    stream.pause_wakeword()
    assert stream.wakeword_paused is True

    stream.resume_wakeword()
    assert stream.wakeword_paused is False


def test_app_voice_turn_flow(monkeypatch):
    """Verifies JarvisApp end-to-end voice turn state transitions and latency logging."""
    from jarvis.app import AppState, JarvisApp

    transitions = []

    def mock_ui_cb(state: str, msg: str) -> None:
        transitions.append(state)

    app = JarvisApp(ui_callback=mock_ui_cb)

    # Mock audio pipeline steps
    mock_audio = np.ones(16000, dtype=np.int16)
    monkeypatch.setattr("jarvis.app.mic_stream.record_until_silence", lambda: mock_audio)
    monkeypatch.setattr("jarvis.app.play_wake_sound", lambda block=True: None)
    monkeypatch.setattr("jarvis.app.play_done_sound", lambda block=False: None)
    monkeypatch.setattr("jarvis.app.transcribe", lambda samples: "open calculator")
    monkeypatch.setattr("jarvis.app.run_task", lambda text, ui_callback=None: "Calculator is now open.")
    monkeypatch.setattr("jarvis.app.speak", lambda text, block=True: None)

    app._process_voice_turn()

    assert app.state == AppState.IDLE
    assert "LISTENING" in transitions
    assert "PROCESSING" in transitions
    assert "SPEAKING" in transitions


def test_wakeword_interrupts_ongoing_task(monkeypatch):
    """Verifies that saying wake word while Jarvis is working interrupts the task and restarts listening."""
    from jarvis.app import JarvisApp, AppState
    from jarvis.brain.agent import is_task_cancelled

    stopped_speech = []
    monkeypatch.setattr("jarvis.app.stop_speech", lambda: stopped_speech.append(True))
    worker_started = []
    monkeypatch.setattr("jarvis.app.JarvisApp._process_voice_turn", lambda self, turn_id=None, is_followup=False: worker_started.append(turn_id))

    app = JarvisApp()
    app.state = AppState.SPEAKING

    # User says wake word again while Jarvis is speaking
    app._on_wake_detected()

    assert is_task_cancelled()
    assert len(stopped_speech) == 1
    assert app.turn_counter == 1


def test_system_prompt_includes_honorific(monkeypatch):
    """Verifies that HONORIFIC from .env or config is embedded in the system prompt."""
    from jarvis.brain.prompts import build_system_prompt

    monkeypatch.setenv("HONORIFIC", "sir")
    prompt = build_system_prompt()
    assert "HONORIFIC INSTRUCTION:" in prompt
    assert "'sir'" in prompt

    monkeypatch.setenv("HONORIFIC", "boss")
    prompt_boss = build_system_prompt()
    assert "'boss'" in prompt_boss


def test_tts_cloud_provider(monkeypatch):
    """Verifies that TTS_PROVIDER='cloud' or 'edge' routes to Edge-TTS."""
    from jarvis.audio.tts import speak

    edge_called = []
    monkeypatch.setenv("TTS_PROVIDER", "cloud")
    monkeypatch.setattr("jarvis.audio.tts._speak_with_edge", lambda text, block: edge_called.append(text) or True)

    speak("Testing cloud speech", block=True)
    assert len(edge_called) == 1
    assert "Testing cloud speech" in edge_called[0]

