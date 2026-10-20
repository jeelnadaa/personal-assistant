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

