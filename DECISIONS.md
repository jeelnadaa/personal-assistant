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

## Phase 3 Decisions
- **Global Kill Switch (Ctrl+Alt+J)**: Implemented in `jarvis/safety/killswitch.py` using Windows `user32.RegisterHotKey` (ID 0x4A01, MOD_CONTROL | MOD_ALT, VK_J) and a daemon message queue thread. When triggered, sets `TASK_CANCEL_EVENT` to abort active tool iterations and agent thinking within milliseconds (< 2s).
- **Confirmation Precedence**: In `jarvis/safety/policy.py`, checks for allowed shell commands and safe application names take precedence over base dangerous flags so trusted safe actions run without friction while untrusted commands always prompt.
- **Interactive & Headless Fallbacks**: `jarvis/safety/confirm.py` supports pluggable custom confirmation handlers (voice/GUI) with fallback to terminal console `[y/N]` prompt.

## Phase 4 Decisions
- **Audio Capture & VAD**: Standardized mic stream on 16kHz mono int16 with 30ms frames in `jarvis/audio/mic.py`. Used `webrtcvad` for silence detection with a 1.2s silence threshold and 6.0s speech timeout.
- **Dual-Engine Wake Word**: Implemented `WakeWordDetector` in `jarvis/audio/wakeword.py` using `openwakeword` with local ONNX model caching. Includes thread-safe pause/resume so wake detection is paused during recording and speaking to prevent feedback.
- **STT Fast Path & Local Fallback**: In `jarvis/audio/stt.py`, requests route to Groq Whisper (`whisper-large-v3-turbo`) for fast transcription, falling back to local `faster-whisper` (`small.en`) if network or credentials are unavailable.
- **TTS Pipeline & Text Sanitization**: In `jarvis/audio/tts.py`, speech is synthesized via `edge-tts` with miniaudio PCM decode, with automatic offline fallback to Windows SAPI5 (`pyttsx3`). Text is cleaned to remove markdown asterisks, backticks, URLs, and formatting before speech.
- **Synthesized UI Sounds**: `jarvis/audio/sounds.py` uses NumPy sine wave synthesis for wake (rising two-tone), done (soft chime), and error (low tone) beeps without requiring external audio asset files.
- **Turnaround Latency Measurement**: Logged exact turnaround time from end-of-speech to start-of-reply in `logs/jarvis.log` and console.
- **Responsive Waiting**: `wait` tool polls `is_task_cancelled()` in 50ms intervals so global kill switch (Ctrl+Alt+J) aborts immediately.
- **EnumWindows Compatibility**: Handled 64-bit Windows LPARAM conversion in `windows_mgmt.py` and `apps.py` by returning `True` from enum callbacks and passing integer `0`.

