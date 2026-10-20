"""Speech-to-text (STT) transcription using Groq hosted Whisper and faster-whisper fallback."""

import io
import os
import wave
import numpy as np

from jarvis.config import config
from jarvis.logger import logger

_LOCAL_WHISPER_MODEL = None


def _get_local_whisper_model():
    """Lazily loads local faster-whisper model once at startup."""
    global _LOCAL_WHISPER_MODEL
    if _LOCAL_WHISPER_MODEL is None:
        try:
            from faster_whisper import WhisperModel
            stt_cfg = config.get("stt", {})
            model_size = stt_cfg.get("model", "small.en")
            device = stt_cfg.get("device", "cpu")
            compute_type = stt_cfg.get("compute_type", "int8")
            logger.info("Loading local faster-whisper model '%s' on %s (%s)...", model_size, device, compute_type)
            _LOCAL_WHISPER_MODEL = WhisperModel(model_size, device=device, compute_type=compute_type)
        except Exception as e:
            logger.error("Failed to initialize faster-whisper: %s", e)
    return _LOCAL_WHISPER_MODEL


def _audio_to_wav_bytes(audio: np.ndarray, sample_rate: int = 16000) -> io.BytesIO:
    """Converts numpy audio array to an in-memory WAV buffer."""
    if audio.dtype != np.int16:
        # Convert float to int16 PCM
        audio_norm = np.clip(audio, -1.0, 1.0)
        audio_int16 = (audio_norm * 32767).astype(np.int16)
    else:
        audio_int16 = audio

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())
    buf.seek(0)
    buf.name = "audio.wav"
    return buf


def transcribe(audio: np.ndarray, sample_rate: int = 16000) -> str:
    """Transcribes audio array into text.

    Args:
        audio: 1D numpy array of 16kHz audio samples.
        sample_rate: Audio sampling rate (default 16000).

    Returns:
        Cleaned transcription string or empty string on silence.
    """
    if audio is None or len(audio) < sample_rate * 0.4:
        # Less than 0.4 seconds of audio is likely noise or click
        return ""

    stt_provider = os.getenv("STT_PROVIDER", "local").strip().lower()

    # Strategy 1: Groq Cloud Whisper
    if stt_provider == "groq" and os.getenv("GROQ_API_KEY"):
        try:
            from groq import Groq
            client = Groq()
            wav_buf = _audio_to_wav_bytes(audio, sample_rate)
            model_name = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")

            resp = client.audio.transcriptions.create(
                file=wav_buf,
                model=model_name,
                language="en",
                temperature=0.0,
            )
            text = resp.text.strip()
            # Filter common whisper artifacts on silence
            hallucinations = {"thank you.", "thank you", "thanks for watching", "bye."}
            if text.lower() in hallucinations and np.max(np.abs(audio)) < 500:
                return ""
            return text
        except Exception as groq_err:
            logger.warning("Groq Whisper transcription failed (%s); falling back to local faster-whisper", groq_err)

    # Strategy 2: Local faster-whisper
    try:
        model = _get_local_whisper_model()
        if not model:
            return ""

        if audio.dtype != np.float32:
            audio_f32 = audio.astype(np.float32) / 32768.0
        else:
            audio_f32 = audio

        segments, _ = model.transcribe(
            audio_f32,
            language="en",
            beam_size=1,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=400),
        )
        text = " ".join(seg.text for seg in segments).strip()
        return text
    except Exception as local_err:
        logger.error("Local faster-whisper transcription failed: %s", local_err)
        return ""
