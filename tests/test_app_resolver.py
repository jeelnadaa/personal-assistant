"""Unit tests for the Universal AppResolver service."""

import json
from pathlib import Path
import pytest

from jarvis.services.app_resolver import AppInfo, AppResolver, normalize_app_name


def test_normalize_app_name():
    """Verifies that app queries are properly normalized."""
    assert normalize_app_name("Chrome.exe") == "chrome"
    assert normalize_app_name("Google Chrome (64-bit)") == "google chrome"
    assert normalize_app_name("  Visual_Studio-Code  ") == "visual studio code"


def test_app_resolver_exact_and_alias_match(tmp_path: Path):
    """Verifies exact and alias matching in AppResolver."""
    cache_file = tmp_path / "apps_cache.json"
    resolver = AppResolver(cache_file=cache_file)

    # Notepad is discovered from Windows Start Menu / builtin
    app, candidates = resolver.resolve("notepad")
    assert app is not None
    assert "notepad" in app.target.lower()
    assert len(candidates) == 0

    # Alias "editor" -> Notepad
    app_alias, _ = resolver.resolve("editor")
    assert app_alias is not None
    assert app_alias.name == "Notepad"


def test_app_resolver_fuzzy_matching(tmp_path: Path):
    """Verifies fuzzy matching when query has slight typo."""
    cache_file = tmp_path / "apps_cache.json"
    resolver = AppResolver(cache_file=cache_file)

    # Add custom app
    resolver.apps["cadcraft"] = AppInfo(
        name="CADCraft Pro",
        target="C:\\Program Files\\CADCraft\\cadcraft.exe",
        source="app_paths",
        aliases=["cadcraft", "cadcraft pro"],
    )

    app, candidates = resolver.resolve("cadcraf")
    assert app is not None
    assert app.name == "CADCraft Pro"


def test_app_resolver_disambiguation(tmp_path: Path):
    """Verifies that ambiguous queries return candidate matches for clarification."""
    cache_file = tmp_path / "apps_cache.json"
    resolver = AppResolver(cache_file=cache_file)

    # Seed multiple apps with same prefix
    resolver.apps["microsoft office word"] = AppInfo("Microsoft Office Word", "winword.exe", "test")
    resolver.apps["microsoft office excel"] = AppInfo("Microsoft Office Excel", "excel.exe", "test")
    resolver.apps["microsoft office powerpoint"] = AppInfo("Microsoft Office PowerPoint", "powerpnt.exe", "test")

    app, candidates = resolver.resolve("microsoft office")
    assert app is None
    assert len(candidates) >= 2


def test_app_resolver_cache_persistence(tmp_path: Path):
    """Verifies that the app index persists to and loads from disk cache."""
    cache_file = tmp_path / "test_cache.json"
    resolver = AppResolver(cache_file=cache_file)
    resolver.apps["customapp"] = AppInfo("Custom App", "C:\\custom.exe", "test")
    resolver.cache_file = cache_file

    # Save
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump({"customapp": {"name": "Custom App", "target": "C:\\custom.exe", "source": "test", "aliases": []}}, f)

    # Reload in new instance
    new_resolver = AppResolver(cache_file=cache_file)
    assert "customapp" in new_resolver.apps
    assert new_resolver.apps["customapp"].name == "Custom App"
