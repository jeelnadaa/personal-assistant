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

# Base directory for configuration and data
BASE_DIR = Path(__file__).resolve().parent.parent


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """Loads settings from .env and config.yaml.

    Args:
        config_path: Optional path to config.yaml. Defaults to BASE_DIR / "config.yaml".

    Returns:
        A dictionary containing merged configuration settings.
    """
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    else:
        # Load from system environment if .env doesn't exist
        load_dotenv()

    cfg_file = config_path or (BASE_DIR / "config.yaml")
    config: dict[str, Any] = {}
    if cfg_file.exists():
        with open(cfg_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    else:
        logger.warning("config.yaml not found at %s, using defaults", cfg_file)

    # Allow .env overrides for specific config values
    if "LLM_PROVIDER" in os.environ:
        config.setdefault("llm", {})["provider"] = os.getenv("LLM_PROVIDER")

    if "STT_PROVIDER" in os.environ:
        config.setdefault("stt", {})["provider"] = os.getenv("STT_PROVIDER")

    if "TTS_PROVIDER" in os.environ:
        config.setdefault("tts", {})["provider"] = os.getenv("TTS_PROVIDER")

    if "USER_NAME" in os.environ:
        config.setdefault("persona", {})["user_name"] = os.getenv("USER_NAME")

    if "HONORIFIC" in os.environ:
        config.setdefault("persona", {})["honorific"] = os.getenv("HONORIFIC")

    return config


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
