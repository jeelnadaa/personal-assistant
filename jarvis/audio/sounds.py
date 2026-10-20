"""Audio sound effects generated dynamically using NumPy and SoundDevice."""

import numpy as np
import sounddevice as sd
from jarvis.logger import logger

SAMPLE_RATE = 16000


def _generate_tone(freq: float, duration_s: float, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Generates a sine wave tone with linear attack and decay envelope."""
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    wave = np.sin(2 * np.pi * freq * t)

    # Apply 10ms envelope at edges to prevent clicking
    ramp_len = min(int(sample_rate * 0.01), len(wave) // 4)
    if ramp_len > 0:
        ramp = np.linspace(0, 1, ramp_len)
        wave[:ramp_len] *= ramp
        wave[-ramp_len:] *= ramp[::-1]

    return (wave * 0.3).astype(np.float32)


def play_wake_sound(block: bool = True) -> None:
    """Rising two-tone beep played when wake word is detected."""
    try:
        t1 = _generate_tone(587.33, 0.09)  # D5
        t2 = _generate_tone(880.00, 0.12)  # A5
        beep = np.concatenate([t1, t2])
        sd.play(beep, samplerate=SAMPLE_RATE, blocking=block)
    except Exception as e:
        logger.warning("Could not play wake sound: %s", e)


def play_done_sound(block: bool = False) -> None:
    """Soft pleasant chime played when a task completes."""
    try:
        t1 = _generate_tone(783.99, 0.08)  # G5
        t2 = _generate_tone(1046.50, 0.14)  # C6
        chime = np.concatenate([t1, t2])
        sd.play(chime, samplerate=SAMPLE_RATE, blocking=block)
    except Exception as e:
        logger.warning("Could not play done sound: %s", e)


def play_error_sound(block: bool = True) -> None:
    """Low tone played on error or silence timeout."""
    try:
        tone = _generate_tone(220.00, 0.20)  # A3 low tone
        sd.play(tone, samplerate=SAMPLE_RATE, blocking=block)
    except Exception as e:
        logger.warning("Could not play error sound: %s", e)
