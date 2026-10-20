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
