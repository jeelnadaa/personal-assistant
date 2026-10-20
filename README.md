# Jarvis - Voice-Controlled AI Assistant for Windows 11

Jarvis is a voice-controlled personal AI assistant for Windows 11 that runs in the background, listens for a wake word, interacts using local or cloud LLMs, and executes system automation tools safely.

---

## Current Status: Production Ready (All 8 Phases Completed)

- **Completed Phases**:
  - **Phase 1: Skeleton + Text Brain** (Foundation, LLM adapters, CLI, test loop)
  - **Phase 2: Full Tool Set** (Complete system automation tools)
  - **Phase 3: Safety Layer** (Policy enforcement, user confirmation prompts, audit logging, Ctrl+Alt+J global kill switch)
  - **Phase 4: Voice Pipeline** (OpenWakeWord, 16kHz mic stream with VAD, Groq/faster-whisper STT, Edge-TTS/pyttsx3 TTS, state machine)
  - **Phase 5: UI** (PySide6 frameless translucent overlay with animations, Allow/Deny buttons, voice confirmations, and pystray system tray)
  - **Phase 6: Screen Vision** (DPI awareness, coordinate unscaling, pywinauto UIA controls inspection & clicking, screenshot downscaling, and older screenshot pruning)
  - **Phase 7: Memory & Browser Automation** (SQLite persistent memory with credential filtering, Playwright persistent browser automation)
  - **Phase 8: Startup & Polish** (Silent Windows logon startup with `pythonw.exe`, named mutex single-instance lock, crash recovery supervisor, and pre-flight setup diagnostics)

---

## Safety & Security Architecture

1. **Policy Enforcement (`jarvis/safety/policy.py`)**:
   - Dangerous operations (e.g. deleting files, moving files, overwriting files, modifying system paths, shutting down the PC, running shell commands, closing unsaved apps) automatically request user approval before execution.
   - Protected paths (`C:\Windows`, `C:\Program Files`, `C:\Program Files (x86)`) cannot be modified or deleted.
   - Deletions are sent to the Windows Recycle Bin via `send2trash`, never permanently unlinked.
2. **Interactive Confirmation (`jarvis/safety/confirm.py`)**:
   - Prompts user in the console (`[y/N]`) or via floating GUI overlay buttons or spoken voice responses (`yes`, `sure`, `no`, etc.) with a 15-second timeout.
3. **Global Kill Switch (`jarvis/safety/killswitch.py`)**:
   - System-wide **Ctrl+Alt+J** hotkey immediately halts LLM thinking, active tool calls, and speech within milliseconds (< 2s).
4. **Audit Logging (`logs/audit.jsonl`)**:
   - Rotating JSONL log recording every executed tool, parameters (redacted for long strings), status, and confirmation outcomes.
5. **Credential Shielding (`jarvis/brain/memory.py`)**:
   - Persistent memory strictly rejects attempts to store API keys, tokens, or passwords (`sk-`, `gsk_`, `token`, `bearer`, etc.).
6. **Single-Instance Enforcement (`jarvis/platform/mutex.py`)**:
   - Uses a Windows Named Mutex (`Local\JarvisDesktopAssistantSingleInstanceMutex`) to prevent duplicate instances from running simultaneously.
7. **Crash Recovery Supervisor (`jarvis/crash_recovery.py`)**:
   - Automatically catches unhandled exceptions, records diagnostic tracebacks, and recovers the voice loop (rate-limited to a maximum of 3 restarts per hour).

---

## Local AI Inference & Hardware Acceleration

Jarvis is configured to run entirely local, privacy-first audio and voice processing with GPU acceleration:

1. **Local Speech-to-Text (STT) via faster-whisper**:
   - **Model**: `medium.en` (~1.4 GB, high accuracy English model).
   - **Backend**: Auto-detects NVIDIA CUDA GPU via `ctranslate2` (`float16` precision) with automatic fallback to CPU (`int8` quantization).
   - **Hardware Support**: Fully tested on NVIDIA GeForce RTX 3070 Laptop GPU (8GB VRAM).
   - **Cloud Fallback**: Optional Groq Whisper API support if local inference is disabled or unavailable.

2. **Local Neural Text-to-Speech (TTS) via Piper**:
   - **Engine**: 100% offline neural TTS powered by Piper ONNX runtime (`piper-tts`).
   - **Voice**: `en_GB-alan-medium` (~63 MB) — natural, confident, slightly futuristic British voice fitting the Jarvis persona.
   - **Audio Quality**: 22,050 Hz high-fidelity synthesis streamed via `sounddevice`.
   - **Configuration**: Configurable `speech_rate` (0.5x - 2.0x) and `volume` (0.0 - 1.0) in `config.yaml`.
   - **Fallbacks**: Graceful multi-engine fallback to Edge-TTS (`en-GB-RyanNeural`) and Windows SAPI5 (`pyttsx3`).

3. **Fully Customizable Wake Word**:
   - **Built-in Models**: OpenWakeWord models (`hey_jarvis`, `alexa`, etc.) running on ONNX.
   - **Arbitrary Custom Phrases**: Hybrid two-stage wake trigger combining WebRTC VAD speech segmentation with fast local Whisper phonetic verification. Set `wake_word_phrase: "hey bro"` or `"hello assistant"` in `config.yaml` with zero custom model training required!

4. **Universal Application Resolver (`AppResolver`)**:
   - Discovers applications installed anywhere across Windows 11, including applications **not in system `PATH`**.
   - Scans Start Menu shortcuts (`.lnk`), Desktop shortcuts, Windows Registry `App Paths` (`HKLM` & `HKCU`), Windows `Uninstall` registries, and UWP apps.
   - Caches discovered apps to `data/apps_cache.json` with background refresh and fuzzy name resolution.
   - Handles disambiguation when multiple matching apps are found.

---

## Quickstart & Installation

### 1. Requirements
- Windows 11 (64-bit)
- Python 3.11+
- NVIDIA GPU with CUDA drivers (optional, automatic CPU fallback provided)
- Dependencies installed:
  ```powershell
  python -m pip install -r requirements.txt
  ```

### 2. Configuration
Copy the template `.env.example` to `.env`:
```powershell
copy .env.example .env
```
Open `.env` and set your active provider and API key:
```ini
LLM_PROVIDER=groq
GROQ_MODEL=qwen/qwen3.8-27b
GROQ_API_KEY=your_key_here
```
> **Guidance on LLM Selection**: Small, fast models can be weak at multi-step PC control and tool-calling. For reliable desktop actions, use a strong tool-calling model (e.g. Claude Sonnet 3.5/3.7, Gemini 2.5 Flash / Pro, or Qwen 3.8 27B / Llama 3.3 70B).

### 3. Local Voice & Model Setup
Run the pre-flight setup check to verify your environment and automatically validate Piper TTS and local STT:
```powershell
python scripts/setup_check.py
```
To download or change Piper voices:
1. Voices are stored in `data/piper_voices/`.
2. The default model is `en_GB-alan-medium.onnx` and `en_GB-alan-medium.onnx.json` from [rhasspy/piper](https://github.com/rhasspy/piper).
3. Update `audio.piper_model_path` in `config.yaml` to switch voices.

---

## Standalone Executable & Rebuilding

Jarvis can be compiled into a standalone Windows executable (`dist/jarvis.exe`) that bundles all dependencies (PySide6, CTranslate2, faster-whisper, openWakeWord, Piper TTS, pystray, Playwright) into a single portable binary.

### Command to Rebuild the App
To compile or re-compile the standalone executable:
```powershell
python scripts/build_exe.py
```
To perform a clean rebuild from scratch:
```powershell
python scripts/build_exe.py --clean
```

### In-App Configuration (No Rebuilding Required)
You **never** need to recompile the executable to change settings. Jarvis dynamically reads its configuration from the files adjacent to `jarvis.exe`:
- **`dist/config.yaml`**: Edit wake phrase, STT/TTS engine, volume, speech rate, search engine, and UI preferences.
- **`dist/.env`**: Edit API keys, active LLM provider, and model names.
- **`dist/data/`**: Holds your persistent SQLite memory (`memory.db`), application index cache (`apps_cache.json`), and offline Piper voice models (`piper_voices/`).

### System Tray Resident Operation
When launched, `jarvis.exe` minimizes to the Windows System Tray (Taskbar Notification Area):
- The animated PySide6 overlay appears only when listening, processing, speaking, or asking for confirmation.
- The assistant stays alive in the system tray even when the overlay window is hidden.
- Right-click the Jarvis tray icon for instant in-app management:
  - **Status**: View active provider, model, wake phrase, and audio status.
  - **Configure (config.yaml)**: Opens `config.yaml` in your default text editor.
  - **Configure Keys (.env)**: Opens `.env` in Notepad for easy API key edits.
  - **Reload Configuration**: Live-reloads settings and wake words into memory without restarting!
  - **Toggle Console Window**: Shows or hides the attached command prompt window for viewing live logs.
  - **Open Data / Logs Folder**: One-click access to stored memories, voice models, and audit logs.
  - **Stop Current Task (Ctrl+Alt+J)**: Instantly halts active tools or speech.
  - **Quit Jarvis**: Cleanly tears down the assistant and releases system resources.

---

## Running Jarvis (Voice Mode)
Launch the voice assistant from python or the standalone executable:
```powershell
# Using the standalone binary:
dist\jarvis.exe

# Or using python:
python main.py
```
- Say **"Hey Jarvis"** (or your custom wake phrase from `config.yaml`) to wake the assistant.
- You will hear a rising two-tone wake beep.
- Speak your command (e.g. *"open discord"*, *"set volume to 40"*, *"play music"*).
- Jarvis records until natural silence, transcribes the speech with local GPU STT, executes the tools, and speaks the confirmation aloud with Piper neural TTS.
- Turnaround latency is measured and logged to `logs/jarvis.log` and the terminal.
- Press **Ctrl+Alt+J** at any moment to immediately stop tasks and speech.

### Testing Audio Hardware & Microphone
To verify input devices, volume sensitivity, and playback:
```powershell
python scripts/check_mic.py
```

---

## Running Jarvis (Text Mode)

### Interactive Console
```powershell
python main.py --text
```

### Safety Tests & Automation
```powershell
# Dangerous action triggers confirmation:
python main.py --text "delete the file test.txt in my downloads"

# Adjust master volume
python main.py --text "set volume to 30"

# Web search
python main.py --text "open chrome and search for python tutorials"

# Window positioning
python main.py --text "snap notepad to the left"
```

### Kill Switch
- Press **Ctrl+Alt+J** at any time to instantly stop active tasks.

### Run Active Provider Self-Test
```powershell
python main.py --test-provider
```

---

### Pre-Flight Setup Diagnostics
To verify your API key, microphone hardware, speech recognition, speech synthesis, and browser automation:
```powershell
python scripts/setup_check.py
# or
python main.py --check-setup
```

### Windows Startup Registration (Run Silently on Login)
Configure Jarvis to launch silently on Windows login using `pythonw.exe`:
```powershell
# Register Jarvis to start with Windows:
python scripts/install_startup.py --install

# Check current startup status:
python scripts/install_startup.py --status

# Remove Jarvis from Windows startup:
python scripts/install_startup.py --uninstall
```

---

## Long-Term Memory & Browser Automation

### Durable Memory
Jarvis maintains a persistent SQLite database in `data/memory.db`. Facts and preferences persist across reboots and sessions:
- *"Remember that my favorite music app is Spotify"* -> Saved to SQLite.
- *"What is my favorite music app?"* -> Recalled from memory.
- *"Forget my favorite music app"* -> Removed.
> **Security Guard**: API keys, credentials, tokens, and passwords are unconditionally rejected and never written to memory.

### Persistent Browser Automation
Powered by Playwright Chromium with persistent user profiles stored in `data/browser_profile`:
- Keeps cookies, logins, and sessions active between restarts.
- Launches headed by default so you can watch automated navigation in real-time.
- Tools available to the assistant: `browser_open`, `browser_click`, `browser_type`, `browser_read`, and `browser_close`.
- Try: *"Open youtube.com and search for lo-fi chill beats"*

---

## Modern Voice UI & Floating Widgets

Jarvis features a sleek dark glassmorphic interface styled precisely to modern Windows 11 aesthetics:

1. **Floating Idle Pill (`IdlePillWidget`)**:
   - Compact 52x28 capsule widget (`#2B2B2B`, 14px border radius, `#454545` border, `#BDBDBD` mic icon) floating right above the Windows taskbar.
   - **Click to Wake**: Click the pill directly to start listening without saying the wake phrase.
   - **Draggable**: Drag the pill anywhere on your screen. Double-click to reset back to bottom-center.
   - **Hide / Re-appear**: Right-click the pill and choose **"Hide Floating Pill"**, or toggle visibility anytime from the System Tray menu (**"Hide/Show Floating Pill"**).

2. **Active State Popup (`ActivePopupCard`)**:
   - 440px wide dark card (`#2B2B2B`, 8px border radius, `#454545` border, soft drop shadow).
   - **Listening**: 20x20 white mic icon, user speech prompt, and 5 animated cyan waveform bars (`#60CDFF`).
   - **Transcribing**: Rotating 20x20 cyan spinner arc on a dark track and transcribed query text.
   - **Answer**: Original question at top (`13px #A8A8A8`), response text (`16px #FFFFFF`), and shortcut footer:
     - **`Esc`**: Closes the answer card and returns to the floating Idle state pill.
     - **`Ctrl+C`**: Copies the assistant response text directly to the Windows clipboard with interactive visual "Copied!" feedback.

3. **Wake Word Barge-In During Transcribing & Thinking**:
   - Saying the wake phrase (e.g. *"Hey Jarvis"*) while Jarvis is transcribing or thinking immediately interrupts the active cycle and transitions straight back into Listening mode.

---

## Running Tests
Run the entire test suite across all 8 phases using `pytest`:
```powershell
python -m pytest tests/ -v
```

---

## How to Add a New Tool

Drop a Python file in `jarvis/tools/` or add to an existing module:

```python
# jarvis/tools/example.py
from .base import tool, ToolResult

@tool(
    name="say_hello",
    description="Returns a greeting for a name. Use only for testing.",
    input_schema={
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Person to greet"}},
        "required": ["name"],
    },
    dangerous=False,
    category="demo",
)
def say_hello(name: str) -> ToolResult:
    return ToolResult(ok=True, output=f"Hello, {name}!")
```

Dropping a file like this in `jarvis/tools/` makes it available automatically on next start.

---

## Troubleshooting

- **Microphone Not Found / No Input Devices**:
  - Run `python scripts/check_mic.py` to inspect available input devices and volume sensitivity.
  - Open **Windows Settings > Privacy & security > Microphone** and ensure "Microphone access" and "Let desktop apps access your microphone" are toggled **ON**.
  - Ensure correct default input device is configured in Windows Sound Settings.
- **Wake Word Sensitivity & False Triggers**:
  - Open `config.yaml` and adjust `audio.vad_aggressiveness` (values 0-3; 2 is balanced, 3 is strict).
  - You can increase the openWakeWord threshold in `config.yaml` if you experience false positives in noisy rooms.
- **DPI Scaling & Coordinate Accuracy**:
  - Jarvis automatically applies Per-Monitor V2 DPI awareness (`ctypes.windll.shcore.SetProcessDpiAwareness(2)`) at launch.
  - Screenshots are captured at physical pixel resolution and downscaled to 1568px max side; click coordinates are automatically translated back via `scale_coordinates(x, y, scale)`.
  - Works consistently across 100%, 125%, 150%, and multi-monitor setups.
- **Playwright Chromium Not Installed**:
  - If browser automation reports missing binaries, run:
    ```powershell
    python -m playwright install chromium
    ```
- **Single Instance Mutex Collision**:
  - If Jarvis fails to launch with *"Another instance of Jarvis is already running"*, check the Windows System Tray or Task Manager for an existing background process, or pass `--no-mutex` to bypass the lock for development.
- **Crash Recovery & Restarts**:
  - The supervisor automatically recovers from unhandled exceptions up to 3 times per hour. If crashes persist, check `logs/jarvis.log` and `data/crash_history.json`.
- **Global Kill Switch (Ctrl+Alt+J)**:
  - If Ctrl+Alt+J fails to register, ensure no other software (such as keyboard utilities) is intercepting the hotkey. Run Jarvis in the active user session.
- **Audit Logs**:
  - Detailed tool actions, parameters, and user confirmations are recorded in `logs/audit.jsonl`.

