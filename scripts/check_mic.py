"""Diagnostic script to list microphone devices and test recording and playback."""

import time
import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
DURATION_SECONDS = 3.0


def list_microphones() -> list[dict]:
    """Lists all available input audio devices."""
    devices = sd.query_devices()
    default_in, _ = sd.default.device

    print("=" * 60)
    print(" Available Audio Input Devices")
    print("=" * 60)

    input_devices = []
    for idx, dev in enumerate(devices):
        if dev["max_input_channels"] > 0:
            is_def = " (DEFAULT)" if idx == default_in else ""
            print(f"[{idx:2d}] {dev['name']} - {dev['hostapi']} (Inputs: {dev['max_input_channels']}){is_def}")
            input_devices.append({"id": idx, "name": dev["name"], "is_default": idx == default_in})

    print("=" * 60)
    return input_devices


def test_microphone(device_id: int | None = None) -> None:
    """Records 3 seconds from the microphone and tests playback."""
    print(f"\nRecording {DURATION_SECONDS:.0f} seconds of audio... Speak now!")
    time.sleep(0.5)

    try:
        recording = sd.rec(
            int(DURATION_SECONDS * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            device=device_id,
        )
        sd.wait()
        print("Recording finished!")

        # Compute volume metrics
        samples = recording.flatten()
        peak = int(np.max(np.abs(samples)))
        rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))

        print(f"\nAudio Analysis:")
        print(f"- Max Peak Amplitude: {peak} / 32767")
        print(f"- RMS Volume Level:   {rms:.1f}")

        if peak < 200:
            print("[WARNING] Very low audio signal detected! Check microphone volume or mute switch.")
        else:
            print("[SUCCESS] Good audio signal detected.")

        print("\nPlaying back recorded audio through your speakers...")
        sd.play(recording, samplerate=SAMPLE_RATE)
        sd.wait()
        print("Playback complete.\n")

    except Exception as e:
        print(f"[ERROR] Microphone test failed: {e}")


def main() -> None:
    list_microphones()
    test_microphone()


if __name__ == "__main__":
    main()
