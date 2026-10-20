"""Secure credential storage for Jarvis using Windows Data Protection API (DPAPI).

Encrypts and decrypts sensitive API keys for the current logged-in Windows user,
preventing plaintext leakage in settings files, source control, or crash logs.
"""

import base64
import json
import os
from pathlib import Path
import sys

from jarvis.logger import logger

try:
    import win32crypt
except ImportError:
    win32crypt = None


def get_user_data_dir() -> Path:
    """Returns the persistent, user-writable data directory (%LOCALAPPDATA%\\Jarvis)."""
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        base = Path(local_app_data) / "Jarvis"
    else:
        base = Path.home() / "AppData" / "Local" / "Jarvis"

    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception:
        # Fallback to local user home
        base = Path.home() / ".jarvis"
        base.mkdir(parents=True, exist_ok=True)

    return base


def _get_vault_file() -> Path:
    """Returns the path to the encrypted DPAPI vault file."""
    return get_user_data_dir() / "vault.bin"


def _encrypt_bytes(data: bytes) -> bytes:
    """Encrypts bytes using Windows DPAPI for the current Windows user."""
    if win32crypt:
        return win32crypt.CryptProtectData(data, "JarvisCredentialVault", None, None, None, 0)
    # Fallback encoding if win32crypt unavailable (e.g. non-Windows unit test environment)
    return base64.b64encode(data)


def _decrypt_bytes(encrypted_data: bytes) -> bytes:
    """Decrypts bytes using Windows DPAPI."""
    if win32crypt:
        return win32crypt.CryptUnprotectData(encrypted_data, None, None, None, 0)[1]
    return base64.b64decode(encrypted_data)


def _read_vault() -> dict[str, str]:
    """Reads and decrypts all key-value secrets from the vault file."""
    vault_path = _get_vault_file()
    if not vault_path.exists():
        return {}

    try:
        raw_bytes = vault_path.read_bytes()
        if not raw_bytes:
            return {}
        decrypted_bytes = _decrypt_bytes(raw_bytes)
        return json.loads(decrypted_bytes.decode("utf-8"))
    except Exception as exc:
        logger.warning("Could not read DPAPI credential vault: %s", exc)
        return {}


def _write_vault(secrets: dict[str, str]) -> bool:
    """Encrypts and writes key-value secrets to the vault file."""
    vault_path = _get_vault_file()
    try:
        raw_json = json.dumps(secrets).encode("utf-8")
        encrypted_bytes = _encrypt_bytes(raw_json)
        vault_path.write_bytes(encrypted_bytes)
        return True
    except Exception as exc:
        logger.error("Failed to write to DPAPI credential vault: %s", exc)
        return False


def get_secret(key_name: str, default: str = "") -> str:
    """Retrieves a secret from the DPAPI vault, falling back to environment variables.

    Args:
        key_name: Secret name (e.g. 'GROQ_API_KEY', 'GEMINI_API_KEY').
        default: Fallback value if not found.

    Returns:
        The decrypted plaintext secret value, or default.
    """
    secrets = _read_vault()
    if key_name in secrets and secrets[key_name]:
        return secrets[key_name]

    # Fallback to os.environ / .env
    env_val = os.getenv(key_name)
    if env_val:
        return env_val.strip()

    return default


def set_secret(key_name: str, value: str) -> bool:
    """Encrypts and stores a secret in the DPAPI vault and updates runtime os.environ.

    Args:
        key_name: Secret identifier (e.g. 'GROQ_API_KEY').
        value: Plaintext secret value.

    Returns:
        True if stored successfully, False otherwise.
    """
    secrets = _read_vault()
    clean_val = value.strip()
    if clean_val:
        secrets[key_name] = clean_val
        os.environ[key_name] = clean_val
    else:
        secrets.pop(key_name, None)
        os.environ.pop(key_name, None)

    return _write_vault(secrets)


def has_secret(key_name: str) -> bool:
    """Returns True if the credential is configured in the vault or environment."""
    val = get_secret(key_name)
    return bool(val and len(val.strip()) > 3)


def mask_secret(value: str) -> str:
    """Returns a masked representation of a secret (e.g. 'gsk_...7890' or '••••••••')."""
    if not value:
        return ""
    if len(value) <= 8:
        return "••••••••"
    prefix = value[:4]
    suffix = value[-4:]
    return f"{prefix}••••{suffix}"
