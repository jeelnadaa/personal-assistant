"""Security and credential management package for Jarvis."""

from jarvis.security.vault import (
    get_secret,
    set_secret,
    has_secret,
    mask_secret,
    get_user_data_dir,
)

__all__ = [
    "get_secret",
    "set_secret",
    "has_secret",
    "mask_secret",
    "get_user_data_dir",
]
