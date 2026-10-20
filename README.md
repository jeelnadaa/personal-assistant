# Jarvis - Voice-Controlled AI Assistant for Windows 11

Jarvis is a voice-controlled personal AI assistant for Windows 11 that runs in the background, listens for a wake word, interacts using local or cloud LLMs, and executes system automation tools safely.

---

## Current Status (Phase 2: Full Tool Set)

- **Completed Phases**:
  - **Phase 1: Skeleton + Text Brain** (Foundation, LLM adapters, CLI, test loop)
  - **Phase 2: Full Tool Set** (Complete system automation tools)

### Available Tools:
- **Applications (`apps.py`)**: `open_app`, `close_app`, `list_running_apps`
- **Window Management (`windows_mgmt.py`)**: `list_windows`, `focus_window`, `minimize_window`, `maximize_window`, `snap_window` (left, right, fullscreen), `get_active_window`
- **System Controls (`system.py`)**: `set_volume`, `get_volume`, `mute`, `set_brightness`, `get_brightness`, `get_system_info`, `lock_screen`, `shutdown_pc`, `toggle_wifi`, `toggle_bluetooth`, `open_settings_page`, `switch_llm_provider`, `get_llm_info`
- **File System (`files.py`)**: `search_files`, `read_text_file`, `write_text_file`, `list_folder`, `open_file`, `move_file`, `copy_file`, `delete_file` (via Recycle Bin), `create_folder`
- **Web & Search (`web.py`)**: `open_url`, `web_search`, `browser_get_page_text`
- **Mouse & Keyboard (`input_control.py`)**: `type_text`, `press_key`, `hotkey`, `click`, `move_mouse`, `scroll`, `drag`, `wait`
- **Screen & Vision (`screen.py`)**: `take_screenshot`, `get_screen_size`, `get_ui_elements`, `click_ui_element`, `read_screen_text`, `find_and_click`
- **Clipboard (`clipboard.py`)**: `get_clipboard`, `set_clipboard`
- **Shell (`shell.py`)**: `run_command` (PowerShell / Command Prompt)
- **Long-term Memory (`memory_tools.py`)**: `remember`, `recall`, `forget`

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

---

## Running Jarvis (Text Mode)

### Interactive Console
```powershell
python main.py --text
```

### Direct Automation Commands
```powershell
# Adjust master volume
python main.py --text "set volume to 30"

# Web search
python main.py --text "open chrome and search for python tutorials"

# File search
python main.py --text "find files named resume in my documents"

# Window positioning
python main.py --text "snap notepad to the left"
```

### Run Active Provider Self-Test
```powershell
python main.py --test-provider
```

---

## Running Tests
Run the test suite using `pytest`:
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

- **DPI and Scaling**: Jarvis sets process DPI awareness (`ctypes.windll.shcore.SetProcessDpiAwareness(2)`) at startup to ensure coordinates correspond to real physical pixels.
- **Provider API Keys**: If `validate_env()` fails on startup, verify that `.env` exists and contains the appropriate key for `LLM_PROVIDER`.
- **Logs**: All runtime operations are logged to `logs/jarvis.log` and tool executions to `logs/audit.jsonl`.
