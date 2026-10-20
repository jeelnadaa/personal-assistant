"""Unit tests for Jarvis persistent SQLite memory and security filtering."""

from pathlib import Path
import pytest
from jarvis.brain.memory import (
    delete_fact,
    get_fact,
    get_memory_context,
    is_potentially_sensitive,
    search_facts,
    set_fact,
)
from jarvis.tools.memory_tools import forget, recall, remember


def test_memory_secret_rejection():
    """Verifies that secrets, API keys, and passwords cannot be stored in memory."""
    ok1, msg1 = set_fact("my_api_key", "sk-1234567890abcdef1234567890abcdef")
    assert ok1 is False
    assert "Refused" in msg1

    ok2, msg2 = set_fact("user_password", "MyP@ssw0rd123!")
    assert ok2 is False
    assert "Refused" in msg2


def test_memory_crud_operations():
    """Verifies storing, retrieving, searching, and deleting user facts."""
    # Store
    ok, msg = set_fact("favorite_editor", "VS Code")
    assert ok is True

    # Retrieve
    val = get_fact("favorite_editor")
    assert val == "VS Code"

    # Search
    matches = search_facts("editor")
    assert any(k == "favorite_editor" and v == "VS Code" for k, v in matches)

    # Delete
    deleted = delete_fact("favorite_editor")
    assert deleted is True
    assert get_fact("favorite_editor") is None


def test_memory_context_formatting():
    """Verifies that get_memory_context produces formatted text within character limit."""
    set_fact("preferred_language", "Python")
    ctx = get_memory_context()
    assert "Stored Facts:" in ctx
    assert "preferred_language: Python" in ctx
    assert len(ctx) <= 1500

    # Cleanup
    delete_fact("preferred_language")


def test_memory_tools():
    """Verifies the @tool wrappers for memory."""
    res_rem = remember(key="coffee_order", value="Iced Americano")
    assert res_rem.ok is True
    assert "Remembered" in res_rem.output

    res_rec = recall(query="coffee")
    assert res_rec.ok is True
    assert "Iced Americano" in res_rec.output

    res_for = forget(key="coffee_order")
    assert res_for.ok is True
    assert "Forgot" in res_for.output
