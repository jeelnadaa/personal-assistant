"""Local AI Model directory management and dynamic model discovery.

Discovers ONLY models that are physically downloaded, complete, and verified
on disk for Piper TTS, Faster-Whisper STT, and Local LLMs.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from jarvis.logger import logger
from jarvis.security.vault import get_user_data_dir


def get_models_root_dir() -> Path:
    """Returns the user-writable root models directory (%LOCALAPPDATA%\\Jarvis\\models)."""
    p = get_user_data_dir() / "models"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_stt_models_dir() -> Path:
    """Returns directory for local Faster-Whisper models."""
    p = get_models_root_dir() / "stt"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_piper_models_dir() -> Path:
    """Returns directory for local Piper neural voice models."""
    p = get_models_root_dir() / "piper"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_llm_models_dir() -> Path:
    """Returns directory for local LLM models (e.g. GGUF weights)."""
    p = get_models_root_dir() / "llm"
    p.mkdir(parents=True, exist_ok=True)
    return p


def ensure_model_directories() -> dict[str, Path]:
    """Ensures all model directories exist on disk and returns their paths."""
    dirs = {
        "root": get_models_root_dir(),
        "stt": get_stt_models_dir(),
        "piper": get_piper_models_dir(),
        "llm": get_llm_models_dir(),
    }
    for p in dirs.values():
        p.mkdir(parents=True, exist_ok=True)
    return dirs


# --- Piper TTS Model Discovery ---

def discover_piper_voices() -> list[dict[str, Any]]:
    """Scans user models and bundled application directories for valid Piper voices.

    A valid Piper voice requires both a '.onnx' model file and a corresponding
    '.onnx.json' configuration file.

    Returns:
        List of dicts with keys: id, name, onnx_path, json_path, language, quality.
    """
    search_dirs: list[Path] = [
        get_piper_models_dir(),
        Path(__file__).resolve().parent.parent.parent / "data" / "piper_voices",
    ]

    # Also check PyInstaller bundled directory if frozen
    if hasattr(sys, "_MEIPASS"):
        search_dirs.append(Path(sys._MEIPASS) / "data" / "piper_voices")
    if getattr(sys, "frozen", False):
        search_dirs.append(Path(sys.executable).resolve().parent / "data" / "piper_voices")

    discovered: dict[str, dict[str, Any]] = {}

    for folder in search_dirs:
        if not folder.exists():
            continue

        try:
            for onnx_file in folder.glob("*.onnx"):
                json_file = onnx_file.with_name(f"{onnx_file.name}.json")
                if not json_file.exists():
                    # Check without double extension (e.g. voice.json)
                    alt_json = onnx_file.with_suffix(".json")
                    if alt_json.exists():
                        json_file = alt_json
                    else:
                        continue  # Incomplete model missing configuration

                voice_id = onnx_file.stem
                if voice_id in discovered:
                    continue

                # Read metadata from JSON
                readable_name = voice_id.replace("_", " ").replace("-", " ").title()
                lang = "en"
                quality = "medium"

                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                        if "dataset" in meta:
                            readable_name = f"{meta.get('dataset')} ({voice_id})"
                        if "language" in meta:
                            lang = meta["language"].get("code", lang)
                        if "audio" in meta:
                            quality = meta.get("audio", {}).get("quality", quality)
                except Exception:
                    pass

                discovered[voice_id] = {
                    "id": voice_id,
                    "name": readable_name,
                    "onnx_path": str(onnx_file.resolve()),
                    "json_path": str(json_file.resolve()),
                    "language": lang,
                    "quality": quality,
                    "folder": str(folder),
                }
        except Exception as exc:
            logger.debug("Error scanning directory %s for Piper voices: %s", folder, exc)

    return list(discovered.values())


# --- Local STT (Faster-Whisper) Discovery ---

def discover_local_stt_models() -> list[dict[str, Any]]:
    """Scans local directories and HuggingFace cache for complete faster-whisper models.

    A valid faster-whisper model folder contains 'model.bin' and 'config.json'.

    Returns:
        List of dicts with keys: id, name, path, size_mb.
    """
    search_dirs: list[Path] = [get_stt_models_dir()]

    # Check HuggingFace hub cache
    hf_hub = Path.home() / ".cache" / "huggingface" / "hub"
    if hf_hub.exists():
        search_dirs.append(hf_hub)

    discovered: dict[str, dict[str, Any]] = {}

    for folder in search_dirs:
        if not folder.exists():
            continue

        try:
            for item in folder.iterdir():
                if not item.is_dir():
                    continue

                target_dir = item
                # Check for HuggingFace snapshots directory
                snapshots_dir = item / "snapshots"
                if snapshots_dir.exists():
                    sub_dirs = [s for s in snapshots_dir.iterdir() if s.is_dir()]
                    if sub_dirs:
                        target_dir = sub_dirs[0]

                # Check for required files
                has_model = (target_dir / "model.bin").exists() or (target_dir / "model.safetensors").exists()
                has_cfg = (target_dir / "config.json").exists()

                if has_model and has_cfg:
                    # Compute size
                    size_bytes = sum(f.stat().st_size for f in target_dir.glob("*") if f.is_file())
                    size_mb = round(size_bytes / (1024 * 1024), 1)

                    model_name = item.name.replace("models--Systran--faster-whisper-", "").replace("faster-whisper-", "")
                    discovered[model_name] = {
                        "id": model_name,
                        "name": f"{model_name.capitalize()} (~{size_mb} MB)",
                        "path": str(target_dir.resolve()),
                        "size_mb": size_mb,
                    }
        except Exception as exc:
            logger.debug("Error scanning directory %s for STT models: %s", folder, exc)

    return list(discovered.values())


# --- Local LLM Discovery ---

def discover_local_llm_models() -> list[dict[str, Any]]:
    """Scans local directory for GGUF model files and checks local Ollama endpoints.

    Returns:
        List of dicts with keys: id, name, type ('gguf' or 'ollama'), path_or_endpoint.
    """
    discovered: list[dict[str, Any]] = []

    # 1. Scan GGUF files in models/llm
    llm_dir = get_llm_models_dir()
    if llm_dir.exists():
        try:
            for gguf_file in llm_dir.glob("*.gguf"):
                size_gb = round(gguf_file.stat().st_size / (1024 ** 3), 2)
                discovered.append({
                    "id": gguf_file.stem,
                    "name": f"{gguf_file.stem} ({size_gb} GB GGUF)",
                    "type": "gguf",
                    "path": str(gguf_file.resolve()),
                })
        except Exception as exc:
            logger.debug("Error scanning GGUF directory: %s", exc)

    # 2. Check local Ollama server if running
    try:
        import urllib.request
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags", headers={"User-Agent": "Jarvis"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                models = data.get("models", [])
                for m in models:
                    m_name = m.get("name", "")
                    if m_name:
                        discovered.append({
                            "id": f"ollama:{m_name}",
                            "name": f"Ollama - {m_name}",
                            "type": "ollama",
                            "path": "http://127.0.0.1:11434",
                        })
    except Exception:
        pass  # Ollama not running locally

    return discovered


# --- Helper Utilities ---

def open_folder_in_explorer(folder_path: Path | str) -> bool:
    """Opens a folder in Windows Explorer."""
    path = Path(folder_path).resolve()
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
    try:
        os.startfile(str(path))
        return True
    except Exception as exc:
        logger.warning("Failed opening folder %s: %s", path, exc)
        return False


def copy_to_clipboard(text: str) -> bool:
    """Copies text to the system clipboard."""
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except Exception:
        try:
            from PySide6.QtWidgets import QApplication
            cb = QApplication.clipboard()
            if cb:
                cb.setText(text)
                return True
        except Exception:
            pass
    return False
