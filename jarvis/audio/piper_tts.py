"""Piper local offline neural Text-To-Speech engine.

Provides natural-sounding speech synthesis completely offline using Piper ONNX models,
with low latency and minimal resource consumption.
"""

from pathlib import Path
import threading
from typing import Any, Generator
import urllib.request
import numpy as np

from jarvis.config import config
from jarvis.logger import logger

PIPER_VOICES_DIR = Path("data/piper_voices")
DEFAULT_VOICE = "en_GB-alan-medium"
HUGGINGFACE_BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/"

_LOADED_VOICE: Any = None
_LOADED_VOICE_NAME: str = ""
_PIPER_LOCK = threading.Lock()


def get_available_voices() -> list[str]:
    """Returns a list of downloaded Piper voice models available in data/piper_voices/."""
    if not PIPER_VOICES_DIR.exists():
        return []
    voices = []
    for model_path in PIPER_VOICES_DIR.glob("*.onnx"):
        voices.append(model_path.stem)
    return sorted(voices)


def ensure_voice_downloaded(voice_name: str = DEFAULT_VOICE) -> tuple[Path, Path]:
    """Ensures that the ONNX model and JSON config for the voice exist, downloading if needed."""
    PIPER_VOICES_DIR.mkdir(parents=True, exist_ok=True)
    model_path = PIPER_VOICES_DIR / f"{voice_name}.onnx"
    config_path = PIPER_VOICES_DIR / f"{voice_name}.onnx.json"

    if model_path.exists() and config_path.exists():
        return model_path, config_path

    logger.info("Piper voice '%s' not found locally. Initiating download...", voice_name)

    # Currently supports en_GB-alan-medium automatic download
    if voice_name == "en_GB-alan-medium":
        base_url = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/"
        urllib.request.urlretrieve(f"{base_url}{voice_name}.onnx.json", config_path)
        urllib.request.urlretrieve(f"{base_url}{voice_name}.onnx", model_path)
        logger.info("Piper voice '%s' successfully downloaded.", voice_name)
    else:
        raise FileNotFoundError(
            f"Voice '{voice_name}' is not downloaded. Place '{voice_name}.onnx' and "
            f"'{voice_name}.onnx.json' in '{PIPER_VOICES_DIR}'."
        )

    return model_path, config_path


def get_piper_voice(voice_name: str = DEFAULT_VOICE) -> Any:
    """Loads and caches the PiperVoice instance."""
    global _LOADED_VOICE, _LOADED_VOICE_NAME

    with _PIPER_LOCK:
        if _LOADED_VOICE is not None and _LOADED_VOICE_NAME == voice_name:
            return _LOADED_VOICE

        try:
            import piper

            model_path, config_path = ensure_voice_downloaded(voice_name)
            logger.info("Loading Piper voice model from '%s'...", model_path)
            _LOADED_VOICE = piper.PiperVoice.load(str(model_path), str(config_path))
            _LOADED_VOICE_NAME = voice_name
            return _LOADED_VOICE
        except Exception as e:
            logger.error("Failed to load Piper voice '%s': %s", voice_name, e)
            return None


def synthesize_audio(
    text: str,
    voice_name: str = DEFAULT_VOICE,
    speed_factor: float = 1.0,
) -> tuple[np.ndarray | None, int]:
    """Synthesizes text into a float32 numpy audio array.

    Args:
        text: Text to synthesize.
        voice_name: Name of the Piper voice.
        speed_factor: Speed modifier (1.0 = normal, 1.1 = faster, 0.9 = slower).

    Returns:
        (audio_samples, sample_rate)
    """
    voice = get_piper_voice(voice_name)
    if not voice:
        return None, 22050

    try:
        from piper.config import SynthesisConfig

        # length_scale is inverse of speed: lower value = faster speech
        length_scale = 1.0 / max(0.5, min(2.0, float(speed_factor)))
        syn_config = SynthesisConfig(length_scale=length_scale)

        chunks = list(voice.synthesize(text, syn_config=syn_config))
        if not chunks:
            return None, voice.config.sample_rate

        # Concatenate audio chunks
        audio_arrays = [c.audio_float_array for c in chunks if len(c.audio_float_array) > 0]
        if not audio_arrays:
            return None, voice.config.sample_rate

        full_audio = np.concatenate(audio_arrays)
        return full_audio, voice.config.sample_rate

    except Exception as e:
        logger.error("Piper synthesis failed for '%s': %s", text[:50], e)
        return None, 22050
