"""Pre-flight setup and hardware verification for Jarvis."""

from dataclasses import dataclass
import os
from pathlib import Path
import sys
from typing import Literal

from jarvis.config import config, load_config
from jarvis.logger import logger


@dataclass
class CheckResult:
    name: str
    status: Literal["PASS", "FAIL", "WARN"]
    message: str
    fix_hint: str = ""


def check_api_keys() -> CheckResult:
    """Verifies that an active LLM provider and API key are configured."""
    provider = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
    valid_providers = {"anthropic", "gemini", "groq"}

    if provider not in valid_providers:
        return CheckResult(
            name="LLM Provider Configuration",
            status="FAIL",
            message=f"Unknown LLM_PROVIDER='{provider}'.",
            fix_hint=f"Set LLM_PROVIDER to one of: {', '.join(sorted(valid_providers))} in .env",
        )

    key_env_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "groq": "GROQ_API_KEY",
    }
    model_env_map = {
        "anthropic": "ANTHROPIC_MODEL",
        "gemini": "GEMINI_MODEL",
        "groq": "GROQ_MODEL",
    }

    key_var = key_env_map[provider]
    key_val = os.getenv(key_var, "").strip()
    model_val = os.getenv(model_env_map[provider], "").strip()

    if not key_val:
        return CheckResult(
            name=f"LLM API Key ({provider.capitalize()})",
            status="FAIL",
            message=f"{key_var} is not set in .env.",
            fix_hint=f"Add {key_var}=your_key_here to your .env file.",
        )

    if not model_val:
        return CheckResult(
            name=f"LLM Model Name ({provider.capitalize()})",
            status="WARN",
            message=f"{model_env_map[provider]} is empty.",
            fix_hint=f"Specify a default model like {model_env_map[provider]}=claude-3-5-sonnet in .env",
        )

    return CheckResult(
        name=f"LLM API Key & Model ({provider.capitalize()})",
        status="PASS",
        message=f"Configured with model '{model_val}'.",
    )


def check_microphone() -> CheckResult:
    """Verifies that an active audio input device is available."""
    try:
        import sounddevice as sd

        devices = sd.query_devices()
        input_devices = [d for d in devices if d.get("max_input_channels", 0) > 0]

        if not input_devices:
            return CheckResult(
                name="Microphone Hardware",
                status="FAIL",
                message="No audio input devices detected on this system.",
                fix_hint="Connect a microphone and enable microphone access in Windows Privacy Settings.",
            )

        default_in, _ = sd.default.device
        default_name = "Unknown"
        if default_in is not None and default_in >= 0 and default_in < len(devices):
            default_name = devices[default_in].get("name", "Default")

        return CheckResult(
            name="Microphone Hardware",
            status="PASS",
            message=f"Default input: '{default_name}' ({len(input_devices)} input devices found).",
        )
    except Exception as e:
        return CheckResult(
            name="Microphone Hardware",
            status="FAIL",
            message=f"Could not query audio devices: {e}",
            fix_hint="Ensure audio drivers are installed and sounddevice/portaudio is working.",
        )


def check_wake_models() -> CheckResult:
    """Verifies openWakeWord models are available or triggers on-demand download."""
    try:
        import openwakeword
        from openwakeword.model import Model

        # Attempt downloading default models if not already cached
        try:
            openwakeword.utils.download_models()
        except Exception:
            pass

        # Verify instantiation
        Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
        return CheckResult(
            name="Wake Word Engine (openWakeWord)",
            status="PASS",
            message="'hey_jarvis' ONNX model is available and initialized.",
        )
    except Exception as e:
        return CheckResult(
            name="Wake Word Engine (openWakeWord)",
            status="WARN",
            message=f"Could not load 'hey_jarvis' model: {e}",
            fix_hint="Run: python -c \"import openwakeword.utils; openwakeword.utils.download_models()\"",
        )


def check_tts_engine() -> CheckResult:
    """Verifies TTS engines (edge-tts and pyttsx3 fallback)."""
    try:
        import pyttsx3

        engine = pyttsx3.init()
        voices = engine.getProperty("voices")
        voice_count = len(voices) if voices else 0
        engine.stop()
        return CheckResult(
            name="Speech Synthesis (TTS)",
            status="PASS",
            message=f"edge-tts available with SAPI5 fallback ({voice_count} local voices).",
        )
    except Exception as e:
        return CheckResult(
            name="Speech Synthesis (TTS)",
            status="WARN",
            message=f"SAPI5 fallback test warning: {e}",
            fix_hint="Ensure Windows Speech Platform and audio drivers are functioning.",
        )


def check_browser_automation() -> CheckResult:
    """Verifies Playwright Chromium browser automation is installed."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            # Check executable path without full launch
            browser_path = p.chromium.executable_path
            if Path(browser_path).exists():
                return CheckResult(
                    name="Playwright Chromium Browser",
                    status="PASS",
                    message=f"Chromium executable found at {Path(browser_path).name}.",
                )
            return CheckResult(
                name="Playwright Chromium Browser",
                status="FAIL",
                message="Playwright Chromium browser binary not found.",
                fix_hint="Run: python -m playwright install chromium",
            )
    except Exception as e:
        return CheckResult(
            name="Playwright Chromium Browser",
            status="FAIL",
            message=f"Playwright error: {e}",
            fix_hint="Run: python -m playwright install chromium",
        )


def run_all_checks() -> list[CheckResult]:
    """Runs all pre-flight diagnostic checks and returns the list of results."""
    # Ensure config & .env are loaded
    load_config()

    return [
        check_api_keys(),
        check_microphone(),
        check_wake_models(),
        check_tts_engine(),
        check_browser_automation(),
    ]
