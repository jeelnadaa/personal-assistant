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

## Quickstart & Installation

### 1. Requirements
- Windows 11 (64-bit)
- Python 3.11+
- Virtual environment or system Python with dependencies installed:
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

## Running Jarvis (Voice Mode)
Launch the voice assistant:
```powershell
python main.py
```
- Say **"Hey Jarvis"** to wake the assistant.
- You will hear a rising two-tone wake beep.
- Speak your command (e.g. *"open calculator"* or *"search for flight tickets"*).
- Jarvis records until natural silence, transcribes the speech, executes the tools, and speaks the confirmation aloud.
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

