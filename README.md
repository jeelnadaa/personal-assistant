# Jarvis - Voice-Controlled AI Assistant for Windows 11

Jarvis is a voice-controlled personal AI assistant for Windows 11 that runs in the background, listens for a wake word, interacts using local or cloud LLMs, and executes system automation tools safely.

---

## Current Status (Phase 6: Screen Vision & UI Automation)

- **Completed Phases**:
  - **Phase 1: Skeleton + Text Brain** (Foundation, LLM adapters, CLI, test loop)
  - **Phase 2: Full Tool Set** (Complete system automation tools)
  - **Phase 3: Safety Layer** (Policy enforcement, user confirmation prompts, audit logging, Ctrl+Alt+J global kill switch)
  - **Phase 4: Voice Pipeline** (OpenWakeWord, 16kHz mic stream with VAD, Groq/faster-whisper STT, Edge-TTS/pyttsx3 TTS, state machine)
  - **Phase 5: UI** (PySide6 frameless translucent overlay with animations, Allow/Deny buttons, voice confirmations, and pystray system tray)
  - **Phase 6: Screen Vision** (DPI awareness, coordinate unscaling, pywinauto UIA controls inspection & clicking, screenshot downscaling, and older screenshot pruning)

---

## Safety & Security Architecture

1. **Policy Enforcement (`jarvis/safety/policy.py`)**:
   - Dangerous operations (e.g. deleting files, moving files, overwriting files, modifying system paths, shutting down the PC, running shell commands, closing unsaved apps) automatically request user approval before execution.
   - Protected paths (`C:\Windows`, `C:\Program Files`, `C:\Program Files (x86)`) cannot be modified or deleted.
   - Deletions are sent to the Windows Recycle Bin via `send2trash`, never permanently unlinked.
2. **Interactive Confirmation (`jarvis/safety/confirm.py`)**:
   - Prompts user in the console (`[y/N]`) or via GUI/voice with action summary and target details.
3. **Global Kill Switch (`jarvis/safety/killswitch.py`)**:
   - System-wide **Ctrl+Alt+J** hotkey immediately halts LLM thinking, tool calls, and speech within milliseconds.
4. **Audit Logging (`logs/audit.jsonl`)**:
   - Rotating JSONL log recording every executed tool, parameters (redacted for long strings), status, and confirmation outcomes.

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

## Running Tests
Run the entire test suite using `pytest`:
```powershell
python -m pytest tests/ -v
```

---

## How to Add a New Tool

Create a new python file in `jarvis/tools/` or add to an existing module:

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

- **Kill Switch**: If Ctrl+Alt+J fails to register, ensure no other software is using the hotkey or run as user with standard input privileges.
- **DPI and Scaling**: Jarvis sets process DPI awareness (`ctypes.windll.shcore.SetProcessDpiAwareness(2)`) at startup to ensure coordinates correspond to real physical pixels.
- **Provider API Keys**: If `validate_env()` fails on startup, verify that `.env` exists and contains the appropriate key for `LLM_PROVIDER`.
- **Logs**: All runtime operations are logged to `logs/jarvis.log` and tool executions to `logs/audit.jsonl`.
