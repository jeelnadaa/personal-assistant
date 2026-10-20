"""High-quality local Speech-to-Text (STT) transcription with GPU acceleration.

Uses faster-whisper with automatic CUDA detection on NVIDIA GPUs (float16)
and seamless CPU fallback (int8), with optional Groq Cloud Whisper fallback.
"""

import io
import os
import wave
from typing import Any
import numpy as np

from jarvis.config import config
from jarvis.logger import logger

_LOCAL_WHISPER_MODEL: Any = None
_ACTIVE_DEVICE: str = "cpu"
_ACTIVE_COMPUTE_TYPE: str = "int8"
_ACTIVE_MODEL_NAME: str = "medium.en"


def is_cuda_available() -> bool:
    """Checks whether an NVIDIA GPU with CUDA support is available for CTranslate2."""
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def _resolve_stt_backend() -> tuple[str, str, str]:
    """Resolves model size, compute device, and precision based on hardware and configuration."""
    stt_cfg = config.get("stt", {})

    model_size = os.getenv("STT_MODEL", stt_cfg.get("model", "medium.en")).strip()
    configured_device = os.getenv("STT_DEVICE", stt_cfg.get("device", "auto")).strip().lower()
    configured_compute = os.getenv("STT_COMPUTE_TYPE", stt_cfg.get("compute_type", "auto")).strip().lower()

    if configured_device == "auto":
        device = "cuda" if is_cuda_available() else "cpu"
    else:
        device = configured_device

    if configured_compute == "auto":
        compute_type = "float16" if device == "cuda" else "int8"
    else:
        compute_type = configured_compute

    return model_size, device, compute_type


def _get_local_whisper_model() -> Any:
    """Lazily loads local faster-whisper model with GPU acceleration and CPU fallback."""
    global _LOCAL_WHISPER_MODEL, _ACTIVE_DEVICE, _ACTIVE_COMPUTE_TYPE, _ACTIVE_MODEL_NAME

    if _LOCAL_WHISPER_MODEL is not None:
        return _LOCAL_WHISPER_MODEL

    from faster_whisper import WhisperModel

    model_size, device, compute_type = _resolve_stt_backend()

    # Attempt primary configured device (CUDA preferred)
    try:
        logger.info(
            "Loading local faster-whisper model '%s' on %s (precision: %s)...",
            model_size,
            device,
            compute_type,
        )
        _LOCAL_WHISPER_MODEL = WhisperModel(model_size, device=device, compute_type=compute_type)
        _ACTIVE_DEVICE = device
        _ACTIVE_COMPUTE_TYPE = compute_type
        _ACTIVE_MODEL_NAME = model_size
        logger.info("faster-whisper model '%s' successfully initialized on %s.", model_size, device)
        return _LOCAL_WHISPER_MODEL
    except Exception as gpu_err:
        if device == "cuda":
            logger.warning("Failed to load faster-whisper on CUDA (%s). Falling back to CPU int8...", gpu_err)
            try:
                _LOCAL_WHISPER_MODEL = WhisperModel(model_size, device="cpu", compute_type="int8")
                _ACTIVE_DEVICE = "cpu"
                _ACTIVE_COMPUTE_TYPE = "int8"
                _ACTIVE_MODEL_NAME = model_size
                logger.info("faster-whisper model '%s' loaded on CPU fallback.", model_size)
                return _LOCAL_WHISPER_MODEL
            except Exception as cpu_err:
                logger.error("Failed to load faster-whisper on CPU fallback: %s", cpu_err)
        else:
            logger.error("Failed to initialize faster-whisper on %s: %s", device, gpu_err)

    return None


def get_stt_info() -> dict[str, Any]:
    """Returns runtime diagnostics for the active STT engine."""
    provider = os.getenv("STT_PROVIDER", "local").strip().lower()
    return {
        "provider": provider,
        "model": _ACTIVE_MODEL_NAME,
        "device": _ACTIVE_DEVICE,
        "compute_type": _ACTIVE_COMPUTE_TYPE,
        "cuda_available": is_cuda_available(),
    }


def _audio_to_wav_bytes(audio: np.ndarray, sample_rate: int = 16000) -> io.BytesIO:
    """Converts numpy audio array to an in-memory WAV buffer."""
    if audio.dtype != np.int16:
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
    """Transcribes audio array into text using local faster-whisper or Groq fallback.

    Args:
        audio: 1D numpy array of 16kHz audio samples.
        sample_rate: Audio sampling rate (default 16000).

    Returns:
        Cleaned transcription string or empty string on silence.
    """
    if audio is None or len(audio) < sample_rate * 0.35:
        # Ignore sub-350ms noise bursts or click artifacts
        return ""

    stt_provider = os.getenv("STT_PROVIDER", "local").strip().lower()

    # Strategy 1: Local GPU/CPU faster-whisper (Default for zero cost & complete privacy)
    if stt_provider == "local" or not os.getenv("GROQ_API_KEY"):
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
                vad_parameters=dict(min_silence_duration_ms=300),
            )
            text = " ".join(seg.text for seg in segments).strip()

            # Filter hallucinations on silence
            hallucinations = {
                "thank you.", "thank you", "thanks for watching",
                "bye.", "subtitles by", "you",
            }
            if text.lower() in hallucinations and np.max(np.abs(audio)) < 600:
                return ""

            return text
        except Exception as local_err:
            logger.error("Local faster-whisper transcription error: %s", local_err)

    # Strategy 2: Groq Cloud Whisper (Fallback if local STT fails or explicitly configured)
    if os.getenv("GROQ_API_KEY"):
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
            hallucinations = {"thank you.", "thank you", "thanks for watching", "bye."}
            if text.lower() in hallucinations and np.max(np.abs(audio)) < 500:
                return ""
            return text
        except Exception as groq_err:
            logger.warning("Groq transcription fallback failed: %s", groq_err)

    return ""
