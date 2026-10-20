# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build specification for Jarvis AI Assistant.

Produces a fully self-contained portable 'onedir' Windows distribution in:
  dist/Jarvis-Portable-Windows/
Bundling:
  - Python runtime & PySide6 UI framework
  - Native libraries (ctranslate2, PortAudio, win32crypt, DPAPI)
  - OpenWakeWord models & Piper neural voice runtime
  - Bundled Satoshi typography and essential UI assets
  - Centralized settings, model discovery, hardware diagnostics, and crash handlers.
"""

from pathlib import Path
import sys
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

# Fonts
fonts_dir = workspace_root / "jarvis" / "resources" / "fonts"
if fonts_dir.exists():
    for f in fonts_dir.glob("*"):
        if f.is_file():
            datas.append((str(f), "jarvis/resources/fonts"))

# Piper voices if present
piper_dir = workspace_root / "data" / "piper_voices"
if piper_dir.exists():
    for f in piper_dir.glob("*"):
        if f.is_file():
            datas.append((str(f), "data/piper_voices"))

datas += collect_data_files("openwakeword")
datas += collect_data_files("ctranslate2")
datas += collect_data_files("faster_whisper")
datas += collect_data_files("piper")
datas += collect_data_files("PySide6")

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
    "jarvis.settings",
    # Security and Vault (DPAPI)
    "jarvis.security",
    "jarvis.security.vault",
    "win32crypt",
    "win32api",
    "win32con",
    # Hardware & System
    "jarvis.system",
    "jarvis.system.hardware",
    "wmi",
    "psutil",
    # Model management & discovery
    "jarvis.models",
    "jarvis.models.discovery",
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
    # UI and typography
    "jarvis.ui",
    "jarvis.ui.fonts",
    "jarvis.ui.overlay",
    "jarvis.ui.tray",
    "jarvis.ui.widgets",
    "jarvis.ui.settings_window",
    # PySide6 components
    "PySide6",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
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
    [],
    exclude_binaries=True,
    name="jarvis",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # Console allows seeing CLI logs/help or runs hidden in background
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Jarvis-Portable-Windows",
)
