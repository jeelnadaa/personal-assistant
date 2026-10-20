"""Configuration loader and validator for Jarvis.

Loads environment variables from .env first, then config.yaml, allowing
environment variables to override YAML configuration.
"""

from pathlib import Path
import os
import sys
from typing import Any
import yaml
from dotenv import load_dotenv

from jarvis.logger import logger

def get_base_dir() -> Path:
    """Returns the base directory for user configuration, data, and logs.

    When running inside a frozen PyInstaller binary, this points to the directory
    containing the executable so user config persists and can be edited.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_bundled_dir() -> Path:
    """Returns the directory of bundled resources inside PyInstaller or source tree."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


# Base directory for configuration and data
BASE_DIR = get_base_dir()


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """Loads settings from .env and config.yaml.

    Args:
        config_path: Optional path to config.yaml. Defaults to BASE_DIR / "config.yaml".

    Returns:
        A dictionary containing merged configuration settings.
    """
    global BASE_DIR
    BASE_DIR = get_base_dir()

    env_path = BASE_DIR / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=True)
    else:
        # If frozen and .env is missing, attempt to copy .env.example
        if getattr(sys, "frozen", False):
            bundled_env = get_bundled_dir() / ".env.example"
            if bundled_env.exists() and not env_path.exists():
                try:
                    import shutil
                    shutil.copy2(bundled_env, env_path)
                    logger.info("Copied initial .env template to %s", env_path)
                except Exception as e:
                    logger.warning("Could not create initial .env: %s", e)
        load_dotenv(override=True)

    cfg_file = config_path or (BASE_DIR / "config.yaml")
    config_dict: dict[str, Any] = {}
    if cfg_file.exists():
        with open(cfg_file, "r", encoding="utf-8") as f:
            config_dict = yaml.safe_load(f) or {}
    else:
        # Check bundled fallback
        bundled_cfg = get_bundled_dir() / "config.yaml"
        if bundled_cfg.exists() and bundled_cfg != cfg_file:
            try:
                with open(bundled_cfg, "r", encoding="utf-8") as f:
                    config_dict = yaml.safe_load(f) or {}
                # Copy template next to exe for easy user editing without rebuild
                try:
                    import shutil
                    shutil.copy2(bundled_cfg, cfg_file)
                    logger.info("Extracted default config.yaml to %s for user editing", cfg_file)
                except Exception:
                    pass
            except Exception as e:
                logger.warning("Error reading bundled config.yaml: %s", e)
        else:
            logger.warning("config.yaml not found at %s, using defaults", cfg_file)

    # Allow .env overrides for runtime configuration
    if "LLM_PROVIDER" in os.environ:
        config_dict.setdefault("llm", {})["provider"] = os.getenv("LLM_PROVIDER")

    if "STT_PROVIDER" in os.environ:
        config_dict.setdefault("stt", {})["provider"] = os.getenv("STT_PROVIDER")

    stt_model = os.getenv("STT_LOCAL_MODEL") or os.getenv("STT_MODEL")
    if stt_model:
        config_dict.setdefault("stt", {})["local_model"] = stt_model

    stt_device = os.getenv("STT_LOCAL_DEVICE") or os.getenv("STT_DEVICE")
    if stt_device:
        config_dict.setdefault("stt", {})["device"] = stt_device

    stt_compute = os.getenv("STT_COMPUTE_TYPE")
    if stt_compute:
        config_dict.setdefault("stt", {})["compute_type"] = stt_compute

    stt_groq_model = os.getenv("STT_GROQ_MODEL") or os.getenv("GROQ_STT_MODEL")
    if stt_groq_model:
        config_dict.setdefault("stt", {})["groq_model"] = stt_groq_model

    if "TTS_PROVIDER" in os.environ:
        config_dict.setdefault("tts", {})["engine"] = os.getenv("TTS_PROVIDER")

    piper_voice = os.getenv("TTS_PIPER_VOICE") or os.getenv("PIPER_VOICE")
    if piper_voice:
        config_dict.setdefault("tts", {})["piper_model_path"] = f"data/piper_voices/{piper_voice}.onnx"
        config_dict.setdefault("tts", {})["piper_voice"] = piper_voice

    if "TTS_SPEED" in os.environ:
        try:
            config_dict.setdefault("tts", {})["speech_rate"] = float(os.getenv("TTS_SPEED", 1.0))
        except ValueError:
            pass

    if "WAKEWORD_PHRASE" in os.environ:
        config_dict.setdefault("wakeword", {})["phrase"] = os.getenv("WAKEWORD_PHRASE")

    if "SEARCH_ENGINE" in os.environ:
        config_dict.setdefault("browser", {})["search_engine"] = os.getenv("SEARCH_ENGINE")

    if "USER_NAME" in os.environ:
        config_dict.setdefault("persona", {})["user_name"] = os.getenv("USER_NAME")

    if "HONORIFIC" in os.environ:
        config_dict.setdefault("persona", {})["honorific"] = os.getenv("HONORIFIC")

    return config_dict


def reload_config() -> dict[str, Any]:
    """Reloads environment variables and config.yaml into the global config dictionary."""
    new_cfg = load_config()
    config.clear()
    config.update(new_cfg)
    logger.info("Configuration reloaded successfully.")
    return config


def get_config_summary() -> dict[str, Any]:
    """Returns a sanitized summary of active configuration without disclosing secrets."""
    provider = os.getenv("LLM_PROVIDER", config.get("llm", {}).get("provider", "groq"))
    model = (
        os.getenv(f"{provider.upper()}_MODEL")
        or config.get("llm", {}).get("model", "")
    )
    tts_engine = os.getenv("TTS_PROVIDER", config.get("tts", {}).get("engine", "edge"))
    return {
        "base_dir": str(BASE_DIR),
        "config_file": str(BASE_DIR / "config.yaml"),
        "config_file_exists": (BASE_DIR / "config.yaml").exists(),
        "env_file": str(BASE_DIR / ".env"),
        "env_file_exists": (BASE_DIR / ".env").exists(),
        "llm_provider": provider,
        "llm_model": model,
        "stt_provider": os.getenv("STT_PROVIDER", config.get("stt", {}).get("provider", "local")),
        "stt_model": (
            os.getenv("STT_LOCAL_MODEL")
            or os.getenv("STT_MODEL")
            or config.get("stt", {}).get("local_model", "medium.en")
        ),
        "stt_device": (
            os.getenv("STT_LOCAL_DEVICE")
            or os.getenv("STT_DEVICE")
            or config.get("stt", {}).get("device", "auto")
        ),
        "tts_engine": tts_engine,
        "tts_speed": float(os.getenv("TTS_SPEED", config.get("tts", {}).get("speech_rate", 1.0))),
        "wakeword_phrase": os.getenv("WAKEWORD_PHRASE", config.get("wakeword", {}).get("phrase", "hey_jarvis")),
        "search_engine": os.getenv("SEARCH_ENGINE", config.get("browser", {}).get("search_engine", "google")),
    }



def validate_env() -> None:
    """Validates that the active LLM provider has an API key and model configured.

    Exits cleanly with a user-friendly error message if configuration is missing.
    Never prints or logs secret key values.
    """
    provider = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
    valid_providers = {"anthropic", "gemini", "groq"}

    if provider not in valid_providers:
        print(
            f"Error: Invalid LLM_PROVIDER='{provider}'. Must be one of: {', '.join(sorted(valid_providers))}.",
            file=sys.stderr,
        )
        sys.exit(1)

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
    model_var = model_env_map[provider]

    key_val = os.getenv(key_var, "").strip()
    model_val = os.getenv(model_var, "").strip()

    if not key_val:
        print(f"Error: LLM_PROVIDER={provider} but {key_var} is empty. Please set it in .env", file=sys.stderr)
        sys.exit(1)

    if not model_val:
        print(f"Error: LLM_PROVIDER={provider} but {model_var} is empty. Please set it in .env", file=sys.stderr)
        sys.exit(1)

    fallback = os.getenv("FALLBACK_PROVIDER", "").strip().lower()
    if fallback:
        if fallback not in valid_providers:
            print(
                f"Error: Invalid FALLBACK_PROVIDER='{fallback}'. Must be one of: {', '.join(sorted(valid_providers))}.",
                file=sys.stderr,
            )
            sys.exit(1)
        fb_key_var = key_env_map[fallback]
        fb_model_var = model_env_map[fallback]
        if not os.getenv(fb_key_var, "").strip():
            print(f"Error: FALLBACK_PROVIDER={fallback} but {fb_key_var} is empty. Please set it in .env", file=sys.stderr)
            sys.exit(1)
        if not os.getenv(fb_model_var, "").strip():
            print(f"Error: FALLBACK_PROVIDER={fallback} but {fb_model_var} is empty. Please set it in .env", file=sys.stderr)
            sys.exit(1)


# Global configuration instance
config = load_config()
