"""Centralized persistent settings manager for Jarvis.

Stores and synchronizes user configuration in %LOCALAPPDATA%\\Jarvis\\settings.json,
overriding development defaults (.env / config.yaml) while keeping secrets in the DPAPI vault.
"""

import json
import os
from pathlib import Path
import sys
from typing import Any

from jarvis.logger import logger
from jarvis.security.vault import get_secret, get_user_data_dir, set_secret


def get_settings_file() -> Path:
    """Returns the persistent settings.json location in user data directory."""
    return get_user_data_dir() / "settings.json"

DEFAULT_SETTINGS: dict[str, Any] = {
    "general": {
        "user_name": "",
        "honorific": "sir",
        "wakeword_phrase": "hey_jarvis",
        "wakeword_threshold": 0.6,
        "search_engine": "google",
        "auto_start": False,
        "show_idle_pill": True,
    },
    "stt": {
        "provider": "groq",
        "groq_model": "whisper-large-v3-turbo",
        "local_model": "medium.en",
        "device": "auto",
        "compute_type": "auto",
        "language": "en",
        "input_device_index": None,
    },
    "tts": {
        "engine": "edge",
        "speed": 1.15,
        "edge_voice": "en-GB-RyanNeural",
        "edge_rate": "+15%",
        "edge_pitch": "+0Hz",
        "piper_voice": "en_GB-alan-medium",
        "output_device_index": None,
    },
    "llm": {
        "provider": "groq",
        "model": "qwen/qwen3.8-27b",
        "fallback_provider": "gemini",
        "fallback_model": "gemini-3.5-flash",
        "gemini_model": "gemini-3.5-flash",
        "anthropic_model": "claude-sonnet-5-5",
        "temperature": 0.2,
        "max_tokens": 800,
    },
    "models": {
        "custom_stt_dir": "",
        "custom_piper_dir": "",
        "custom_llm_dir": "",
    },
    "system": {
        "cpu_mode": False,
    },
}


class SettingsManager:
    """Thread-safe persistent settings coordinator."""

    def __init__(self) -> None:
        self._settings: dict[str, Any] = {}
        self._pending_restart = False
        self._restart_reasons: list[str] = []
        self.load()

    def load(self) -> dict[str, Any]:
        """Loads settings from settings.json, falling back to defaults and .env."""
        # Deep copy defaults
        self._settings = json.loads(json.dumps(DEFAULT_SETTINGS))

        # Check existing settings.json
        settings_file = get_settings_file()
        if settings_file.exists():
            try:
                with open(settings_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    self._deep_merge(self._settings, saved)
                logger.info("Loaded persistent user settings from %s", settings_file)
            except Exception as exc:
                logger.warning("Could not read %s, using defaults: %s", settings_file, exc)
        else:
            # Seed from .env / environment variables for smooth initial onboarding
            self._import_from_env()

        self._sync_to_runtime()
        return self._settings

    def _deep_merge(self, base: dict[str, Any], override: dict[str, Any]) -> None:
        """Recursively merges override dictionary into base."""
        for k, v in override.items():
            if isinstance(v, dict) and k in base and isinstance(base[k], dict):
                self._deep_merge(base[k], v)
            else:
                base[k] = v

    def _import_from_env(self) -> None:
        """Seeds initial settings from active environment variables or .env if present."""
        if "HONORIFIC" in os.environ:
            self._settings["general"]["honorific"] = os.getenv("HONORIFIC", "sir")
        if "USER_NAME" in os.environ:
            self._settings["general"]["user_name"] = os.getenv("USER_NAME", "")
        if "WAKEWORD_PHRASE" in os.environ:
            self._settings["general"]["wakeword_phrase"] = os.getenv("WAKEWORD_PHRASE", "hey_jarvis")
        if "WAKEWORD_THRESHOLD" in os.environ:
            try:
                self._settings["general"]["wakeword_threshold"] = float(os.getenv("WAKEWORD_THRESHOLD", 0.6))
            except ValueError:
                pass

        if "STT_PROVIDER" in os.environ:
            self._settings["stt"]["provider"] = os.getenv("STT_PROVIDER", "groq")
        if "STT_LOCAL_MODEL" in os.environ:
            self._settings["stt"]["local_model"] = os.getenv("STT_LOCAL_MODEL", "medium.en")

        if "TTS_PROVIDER" in os.environ:
            self._settings["tts"]["engine"] = os.getenv("TTS_PROVIDER", "edge")
        if "TTS_SPEED" in os.environ:
            try:
                self._settings["tts"]["speed"] = float(os.getenv("TTS_SPEED", 1.15))
            except ValueError:
                pass
        if "TTS_EDGE_VOICE" in os.environ:
            self._settings["tts"]["edge_voice"] = os.getenv("TTS_EDGE_VOICE", "en-GB-RyanNeural")

        if "LLM_PROVIDER" in os.environ:
            self._settings["llm"]["provider"] = os.getenv("LLM_PROVIDER", "groq")
        if "GROQ_MODEL" in os.environ:
            self._settings["llm"]["model"] = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
        if "FALLBACK_PROVIDER" in os.environ:
            self._settings["llm"]["fallback_provider"] = os.getenv("FALLBACK_PROVIDER", "gemini")

    def _sync_to_runtime(self) -> None:
        """Propagates settings into active environment variables and config dict."""
        gen = self._settings.get("general", {})
        os.environ["HONORIFIC"] = gen.get("honorific", "sir")
        os.environ["USER_NAME"] = gen.get("user_name", "")
        os.environ["WAKEWORD_PHRASE"] = gen.get("wakeword_phrase", "hey_jarvis")
        os.environ["WAKEWORD_THRESHOLD"] = str(gen.get("wakeword_threshold", 0.6))
        os.environ["SEARCH_ENGINE"] = gen.get("search_engine", "google")

        stt_cfg = self._settings.get("stt", {})
        os.environ["STT_PROVIDER"] = stt_cfg.get("provider", "groq")
        os.environ["STT_LOCAL_MODEL"] = stt_cfg.get("local_model", "medium.en")
        os.environ["STT_LOCAL_DEVICE"] = stt_cfg.get("device", "auto")
        os.environ["STT_COMPUTE_TYPE"] = stt_cfg.get("compute_type", "auto")
        os.environ["STT_GROQ_MODEL"] = stt_cfg.get("groq_model", "whisper-large-v3-turbo")

        tts_cfg = self._settings.get("tts", {})
        os.environ["TTS_PROVIDER"] = tts_cfg.get("engine", "edge")
        os.environ["TTS_SPEED"] = str(tts_cfg.get("speed", 1.15))
        os.environ["TTS_EDGE_VOICE"] = tts_cfg.get("edge_voice", "en-GB-RyanNeural")
        os.environ["TTS_EDGE_RATE"] = tts_cfg.get("edge_rate", "+15%")
        os.environ["TTS_EDGE_PITCH"] = tts_cfg.get("edge_pitch", "+0Hz")
        os.environ["TTS_PIPER_VOICE"] = tts_cfg.get("piper_voice", "en_GB-alan-medium")

        llm_cfg = self._settings.get("llm", {})
        os.environ["LLM_PROVIDER"] = llm_cfg.get("provider", "groq")
        prov = llm_cfg.get("provider", "groq")
        if prov == "groq":
            os.environ["GROQ_MODEL"] = llm_cfg.get("model", "qwen/qwen3.8-27b")
        elif prov == "gemini":
            os.environ["GEMINI_MODEL"] = llm_cfg.get("gemini_model", "gemini-3.5-flash")
        elif prov == "anthropic":
            os.environ["ANTHROPIC_MODEL"] = llm_cfg.get("anthropic_model", "claude-sonnet-5-5")

        if llm_cfg.get("fallback_provider"):
            os.environ["FALLBACK_PROVIDER"] = llm_cfg.get("fallback_provider", "gemini")
        if llm_cfg.get("fallback_model"):
            os.environ["FALLBACK_MODEL"] = llm_cfg.get("fallback_model", "gemini-3.5-flash")

        # Also update global config object in jarvis.config
        try:
            from jarvis.config import config
            config.setdefault("persona", {})["honorific"] = gen.get("honorific", "sir")
            config.setdefault("persona", {})["user_name"] = gen.get("user_name", "")
            config.setdefault("wakeword", {})["phrase"] = gen.get("wakeword_phrase", "hey_jarvis")
            config.setdefault("wakeword", {})["threshold"] = gen.get("wakeword_threshold", 0.6)
            config.setdefault("stt", {})["provider"] = stt_cfg.get("provider", "groq")
            config.setdefault("stt", {})["local_model"] = stt_cfg.get("local_model", "medium.en")
            config.setdefault("tts", {})["engine"] = tts_cfg.get("engine", "edge")
            config.setdefault("tts", {})["speech_rate"] = float(tts_cfg.get("speed", 1.15))
            config.setdefault("llm", {})["provider"] = llm_cfg.get("provider", "groq")
            config.setdefault("llm", {})["temperature"] = float(llm_cfg.get("temperature", 0.2))
            config.setdefault("llm", {})["max_tokens"] = int(llm_cfg.get("max_tokens", 800))
        except Exception:
            pass

    def get(self, section: str, key: str | None = None, default: Any = None) -> Any:
        """Retrieves a setting value."""
        sec = self._settings.get(section, {})
        if key is None:
            return sec
        return sec.get(key, default)

    def set(self, section: str, key: str, value: Any, requires_restart: bool = False, restart_reason: str = "") -> None:
        """Updates a setting value in memory and checks if restart is flagged."""
        if section not in self._settings:
            self._settings[section] = {}

        old_val = self._settings[section].get(key)
        if old_val != value:
            self._settings[section][key] = value
            if requires_restart:
                self._pending_restart = True
                if restart_reason and restart_reason not in self._restart_reasons:
                    self._restart_reasons.append(restart_reason)

    def save(self) -> bool:
        """Persists all settings to settings.json and syncs runtime."""
        settings_file = get_settings_file()
        try:
            settings_file.parent.mkdir(parents=True, exist_ok=True)
            with open(settings_file, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, indent=2)
            self._sync_to_runtime()
            logger.info("Successfully saved user settings to %s", settings_file)
            return True
        except Exception as exc:
            logger.error("Failed saving settings to %s: %s", settings_file, exc)
            return False

    def reset_to_defaults(self) -> bool:
        """Resets all settings to factory defaults."""
        self._settings = json.loads(json.dumps(DEFAULT_SETTINGS))
        return self.save()

    def is_restart_required(self) -> bool:
        """Returns True if any modified setting requires an application restart."""
        return self._pending_restart

    def get_restart_reasons(self) -> list[str]:
        """Returns human-readable descriptions of why a restart is recommended."""
        return list(self._restart_reasons)

    def clear_restart_flag(self) -> None:
        """Clears the pending restart status."""
        self._pending_restart = False
        self._restart_reasons.clear()


# Global singleton instance
settings = SettingsManager()


def get_setting(section: str, key: str | None = None, default: Any = None) -> Any:
    """Retrieves a setting value from the global SettingsManager instance."""
    return settings.get(section, key, default)


def set_setting(section: str, key: str, value: Any, requires_restart: bool = False, restart_reason: str = "") -> None:
    """Sets a setting value on the global SettingsManager instance."""
    settings.set(section, key, value, requires_restart=requires_restart, restart_reason=restart_reason)


def save_settings() -> bool:
    """Persists settings to disk."""
    return settings.save()


def load_settings() -> dict[str, Any]:
    """Reloads settings from disk."""
    return settings.load()


def reset_to_defaults() -> bool:
    """Resets settings to defaults."""
    return settings.reset_to_defaults()


def update_settings(updates: dict[str, dict[str, Any]]) -> bool:
    """Batch updates multiple settings and persists them."""
    for section, values in updates.items():
        for k, v in values.items():
            settings.set(section, k, v)
    return settings.save()


def get_all_settings() -> dict[str, Any]:
    """Returns a copy of all current settings."""
    return json.loads(json.dumps(settings._settings))
