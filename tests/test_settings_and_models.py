"""Tests for centralized settings, DPAPI vault, model discovery, and hardware diagnostics."""

import os
from pathlib import Path
import pytest

from jarvis.security.vault import get_secret, set_secret, has_secret, mask_secret
from jarvis.models.discovery import (
    ensure_model_directories,
    get_models_root_dir,
    get_stt_models_dir,
    get_piper_models_dir,
    get_llm_models_dir,
    discover_piper_voices,
    discover_local_stt_models,
    discover_local_llm_models,
)
from jarvis.settings import (
    get_setting,
    update_settings,
    save_settings,
    load_settings,
    reset_to_defaults,
    get_all_settings,
)
from jarvis.system.hardware import (
    get_system_specs,
    get_gpu_info,
    is_cuda_available,
)


def test_vault_roundtrip():
    """Verifies that secrets can be stored, retrieved, checked, and masked."""
    test_key = "TEST_JARVIS_SECRET_KEY"
    test_val = "sk-test-super-secret-token-12345"

    set_secret(test_key, test_val)
    assert has_secret(test_key) is True
    assert get_secret(test_key) == test_val

    # Masking test
    masked = mask_secret(test_val)
    assert "super-secret" not in masked
    assert masked.startswith("sk-t")
    assert masked.endswith("2345")

    # Clear secret
    set_secret(test_key, "")
    assert has_secret(test_key) is False
    assert get_secret(test_key) == ""


def test_model_directories_and_discovery(tmp_path, monkeypatch):
    """Verifies that model folders are created and model discovery accurately verifies companion files."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    ensure_model_directories()

    piper_dir = get_piper_models_dir()
    stt_dir = get_stt_models_dir()
    llm_dir = get_llm_models_dir()

    assert piper_dir.exists()
    assert stt_dir.exists()
    assert llm_dir.exists()

    # Count initially available
    init_voices = len(discover_piper_voices())
    init_stt = len(discover_local_stt_models())
    init_llm = len(discover_local_llm_models())

    # Test Piper voice: requires BOTH .onnx and .onnx.json
    dummy_onnx = piper_dir / "en_US-amy-medium.onnx"
    dummy_onnx.write_text("model data")
    # Only .onnx exists -> should NOT be discovered yet
    assert len(discover_piper_voices()) == init_voices

    dummy_json = piper_dir / "en_US-amy-medium.onnx.json"
    dummy_json.write_text('{"sample_rate": 22050}')
    # Both exist -> should now be discovered
    discovered_voices = discover_piper_voices()
    assert len(discovered_voices) == init_voices + 1
    assert any(v["id"] == "en_US-amy-medium" for v in discovered_voices)

    # Test STT model: requires directory with model.bin and config.json
    model_folder = stt_dir / "whisper-base"
    model_folder.mkdir()
    (model_folder / "model.bin").write_text("bin")
    # Missing config.json -> should NOT be discovered
    assert len(discover_local_stt_models()) == init_stt

    (model_folder / "config.json").write_text("{}")
    discovered_stt = discover_local_stt_models()
    assert len(discovered_stt) == init_stt + 1
    assert any("Base" in s["name"] or "whisper-base" in s["id"] for s in discovered_stt)

    # Test Local LLM: requires .gguf file
    gguf_file = llm_dir / "llama-3-8b-instruct.Q4_K_M.gguf"
    gguf_file.write_text("gguf")
    discovered_llm = discover_local_llm_models()
    assert len(discovered_llm) == init_llm + 1
    assert any("llama-3-8b-instruct" in m["name"] for m in discovered_llm)


def test_settings_persistence(tmp_path, monkeypatch):
    """Verifies that settings can be loaded, updated, and reset to defaults."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    # Load defaults
    settings = load_settings()
    assert "general" in settings
    assert "stt" in settings
    assert "tts" in settings
    assert "llm" in settings

    # Update a setting
    update_settings({"general": {"wakeword_phrase": "computer", "show_idle_pill": False}})
    assert get_setting("general", "wakeword_phrase") == "computer"
    assert get_setting("general", "show_idle_pill") is False

    # Check persistence by reloading fresh
    fresh_settings = load_settings()
    assert fresh_settings["general"]["wakeword_phrase"] == "computer"

    # Reset to defaults
    reset_to_defaults()
    assert get_setting("general", "wakeword_phrase") == "hey_jarvis"


def test_hardware_specs():
    """Verifies hardware and GPU detection returns valid data structures."""
    specs = get_system_specs()
    assert "ram_total_gb" in specs
    assert specs["ram_total_gb"] > 0
    assert "cpu_cores" in specs

    gpu_info = get_gpu_info()
    assert "cuda_available" in gpu_info
    assert isinstance(is_cuda_available(), bool)
