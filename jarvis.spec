# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build specification for Jarvis AI Assistant.

Bundles all runtime dependencies, native libraries (ctranslate2, PortAudio),
ONNX models (openwakeword), phoneme databases (piper), and Qt plugins into a
standalone Windows executable.
"""

import sys
from pathlib import Path
from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

block_cipher = None

# Workspace root
workspace_root = Path.cwd().resolve()

# 1. Collect data files
datas = [
    (str(workspace_root / "config.yaml"), "."),
    (str(workspace_root / ".env.example"), "."),
]
datas += collect_data_files("openwakeword")
datas += collect_data_files("ctranslate2")
datas += collect_data_files("faster_whisper")
datas += collect_data_files("piper")

# 2. Collect native dynamic libraries (.dll)
binaries = []
binaries += collect_dynamic_libs("ctranslate2")
binaries += collect_dynamic_libs("piper")
binaries += collect_dynamic_libs("_sounddevice_data")

# 3. Collect hidden imports
hiddenimports = [
    # Core Jarvis packages
    "jarvis",
    "jarvis.app",
    "jarvis.config",
    "jarvis.logger",
    "jarvis.crash_recovery",
    "jarvis.setup_check",
    # Audio pipeline
    "jarvis.audio",
    "jarvis.audio.mic",
    "jarvis.audio.sounds",
    "jarvis.audio.stt",
    "jarvis.audio.tts",
    "jarvis.audio.piper_tts",
    "jarvis.audio.wakeword",
    # Brain and LLM providers
    "jarvis.brain",
    "jarvis.brain.agent",
    "jarvis.brain.context",
    "jarvis.brain.llm",
    "jarvis.brain.memory",
    "jarvis.brain.prompts",
    "jarvis.brain.providers",
    "jarvis.brain.providers.base",
    "jarvis.brain.providers.anthropic_provider",
    "jarvis.brain.providers.gemini_provider",
    "jarvis.brain.providers.groq_provider",
    # Services
    "jarvis.services",
    "jarvis.services.app_resolver",
    # Tools
    "jarvis.tools",
    "jarvis.tools.base",
    "jarvis.tools.apps",
    "jarvis.tools.clipboard",
    "jarvis.tools.files",
    "jarvis.tools.input_control",
    "jarvis.tools.memory_tools",
    "jarvis.tools.screen",
    "jarvis.tools.shell",
    "jarvis.tools.system",
    "jarvis.tools.web",
    "jarvis.tools.windows_mgmt",
    # Safety and platform
    "jarvis.safety",
    "jarvis.safety.audit",
    "jarvis.safety.confirm",
    "jarvis.safety.killswitch",
    "jarvis.safety.policy",
    "jarvis.platform",
    "jarvis.platform.mutex",
    # UI
    "jarvis.ui",
    "jarvis.ui.overlay",
    "jarvis.ui.tray",
    "jarvis.ui.widgets",
    # System and third-party dependencies
    "ctranslate2",
    "faster_whisper",
    "openwakeword",
    "openwakeword.model",
    "openwakeword.utils",
    "openwakeword.vad",
    "piper",
    "piper.voice",
    "webrtcvad",
    "sounddevice",
    "_sounddevice_data",
    "pystray",
    "pystray._win32",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "pywinauto",
    "pywinauto.findwindows",
    "pywinauto.controls",
    "pywinauto.uia_element_info",
    "pycaw",
    "pycaw.pycaw",
    "comtypes",
    "comtypes.client",
    "yaml",
    "dotenv",
    "groq",
    "anthropic",
    "google.genai",
    "send2trash",
    "miniaudio",
    "pyttsx3",
    "pyttsx3.drivers",
    "pyttsx3.drivers.sapi5",
    "scipy",
    "scipy.signal",
]
hiddenimports += collect_submodules("pystray")
hiddenimports += collect_submodules("openwakeword")

# 4. Exclude unnecessary bulky training packages to reduce executable size
excludes = [
    "torch",
    "torchvision",
    "torchaudio",
    "piper.train",
    "matplotlib",
    "tkinter",
    "IPython",
    "notebook",
    "jupyter",
    "pytest",
]

a = Analysis(
    ["main.py"],
    pathex=[str(workspace_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(workspace_root / "hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="jarvis",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Console is automatically hidden when voice mode is launched, and toggleable via tray
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
