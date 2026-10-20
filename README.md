# Jarvis - Voice-Controlled AI Assistant for Windows 11

Jarvis is a voice-controlled personal AI assistant for Windows 11 that runs in the background, listens for a wake word, interacts using local or cloud LLMs, and executes system automation tools safely.

---

## Current Status (Phase 1: Skeleton + Text Brain)

- **Completed**:
  - Full modular project structure
  - Dynamic tool registry with `@tool` decorator
  - Phase 1 core tools: `open_app`, `get_system_info`, `open_url`
  - Multi-provider LLM abstraction layer (`anthropic`, `gemini`, `groq`)
  - Agent decision and tool-calling execution loop with cancellation, audit logging, and infinite loop protection
  - CLI text mode (`python main.py --text`)
  - Provider self-test command (`python main.py --test-provider`)
  - Unit test suite for tools, loop, and provider conversions

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
LLM_PROVIDER=anthropic
ANTHROPIC_MODEL=claude-sonnet-5-5
ANTHROPIC_API_KEY=your_key_here
```
> **Guidance on LLM Selection**: Small, fast models can be weak at multi-step PC control and tool-calling. For reliable desktop actions, use a strong tool-calling model (e.g. Claude Sonnet 3.5/3.7, Gemini 2.5 Flash / Pro, or Llama 3.3 70B).

---

## Running Jarvis (Phase 1)

### Text Mode (Interactive)
```powershell
python main.py --text
```

### Text Mode (Single Command)
```powershell
python main.py --text "what time is it and how much battery do I have"
```
```powershell
python main.py --text "open notepad"
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
