"""Confirmation prompt handling for dangerous operations."""

import sys
from typing import Callable
from jarvis.logger import logger

_CUSTOM_CONFIRM_HANDLER: Callable[[str], bool] | None = None


def set_confirm_handler(handler: Callable[[str], bool] | None) -> None:
    """Sets a custom confirmation handler (e.g. GUI dialog or voice prompt)."""
    global _CUSTOM_CONFIRM_HANDLER
    _CUSTOM_CONFIRM_HANDLER = handler


def ask(description: str) -> bool:
    """Asks the user for approval to execute a potentially dangerous action.

    Args:
        description: Readable summary of the action requesting execution.

    Returns:
        True if approved, False otherwise.
    """
    logger.info("Requesting confirmation for: %s", description)

    if _CUSTOM_CONFIRM_HANDLER is not None:
        try:
            decision = _CUSTOM_CONFIRM_HANDLER(description)
            logger.info("Custom confirm handler returned: %s", decision)
            return decision
        except Exception as e:
            logger.error("Error in custom confirm handler: %s", e)
            return False

    # Fallback to console prompt
    try:
        print(f"\n[SECURITY] Jarvis wants to: {description}")
        resp = input("Allow this action? [y/N]: ").strip().lower()
        allowed = resp in ("y", "yes")
        logger.info("Console confirmation decision: %s", allowed)
        return allowed
    except (EOFError, KeyboardInterrupt):
        return False
