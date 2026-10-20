# Architectural & Implementation Decisions

## Phase 1 Decisions
- **Python Environment**: Target is Windows 11 with Python 3.11+. Validated on Python 3.14 with standard libraries and pinned packages.
- **Logger**: Standard library `logging.handlers.RotatingFileHandler` writing formatted logs to `logs/jarvis.log` with UTF-8 encoding.
- **Config & Environment**: `config.yaml` with schema-safe dictionary access and `.env` override layer via `python-dotenv`.
- **DPI Awareness**: Initialized `ctypes.windll.shcore.SetProcessDpiAwareness(2)` in `main.py` to ensure logical/pixel coordinate fidelity across all displays.
- **LLM Abstraction**: Strict abstraction via `LLMProvider` base class and neutral `Msg`, `ToolCall`, and `ToolResultMsg` types in `jarvis/brain/providers/base.py`. `AnthropicProvider`, `GeminiProvider`, and `GroqProvider` translate between neutral types and native SDK representations.
- **Gemini Schema Sanitization**: Implemented `sanitize_schema_for_gemini()` to recursively strip fields unsupported by Gemini function calling (`additionalProperties`, `default`, `$schema`, `examples`, `title`).
- **Tool Auto-Discovery**: `jarvis/tools/__init__.py` uses `pkgutil.iter_modules` to dynamically load all tool modules in `jarvis/tools/` and register them via `@tool`.
- **Safety & Kill Switch**: Thread-safe `TASK_CANCEL_EVENT` checked at the top of the agent loop and prior to every tool call, enabling sub-2-second task cancellation.
- **Audit Logging**: `logs/audit.jsonl` logs every tool call with timestamps, parameters (truncated for long text), outcomes, and user safety decisions.

## Phase 2 Decisions
- **PyCaw Compatibility**: Target Windows 11 default multimedia endpoint using `AudioUtilities.GetSpeakers().EndpointVolume` with scalar normalization between 0.0 and 1.0.
- **Screen Scaling & Math**: Standardized downscaling to max side 1568 px (`s = orig_w / sent_w`) and verified coordinate unscaling math across 1080p, 1440p, 125%, and 150% scaling.
- **Safe File Operations**: All destructive file actions (`delete_file`, `move_file`) check `protected_paths` (`C:\Windows`, `C:\Program Files`, etc.) and delete operations route through `send2trash` to prevent irreversible loss.
- **Memory Security Guard**: Hardened `jarvis/brain/memory.py` to prevent storing credentials, passwords, or secret patterns (`sk-`, `gsk_`, tokens).
- **Window Snapping**: Used `win32api.GetMonitorInfo` to accurately retrieve the current monitor's `Work` rectangle (excluding Windows taskbar) for left/right/fullscreen snaps.
