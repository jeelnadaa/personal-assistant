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

## Phase 5 Decisions
- **PySide6 Floating Overlay**: Frameless, translucent, always-on-top window positioned at the bottom center of the primary display (`jarvis/ui/overlay.py`). Styled with dark glassmorphic card aesthetics, drop shadow, and animated Qt canvas graphics (pulsing orb for listening, spinning arc for thinking, audio waveform bars for speaking, amber alert shield for confirmations, green check for completion, red for errors).
- **Signal/Slot Thread Bridge**: Thread-safe communication between agent worker threads and Qt main thread using `OverlayBridge(QtCore.QObject)` with custom signals.
- **Main Thread Event Pumping**: In `confirm.ask()` and `ask_confirmation()`, if executed on the main Qt GUI thread, dynamically pumps `app.processEvents()` in a 20ms poll loop to prevent thread deadlock while awaiting user action.
- **Unified Dual-Mode Confirmation**: Allow/Deny buttons on the overlay and voice confirmation listener (`_voice_confirm_worker`) both update a single `overlay._confirm_result` and trigger `overlay._confirm_event`, supporting both button clicks and spoken affirmative/negative responses (`yes`, `yeah`, `sure`, etc.) within a 15-second timeout.
- **System Tray**: `pystray` icon running in a dedicated background daemon thread (`jarvis/ui/tray.py`), providing quick actions: Status, Pause/Resume listening, Text mode guidance, Open logs folder, Stop current task, and Clean Quit.

## Phase 6 Decisions
- **DPI Scaling & Coordinate Precision**: Set Windows process DPI awareness to Per-Monitor V2 (`SetProcessDpiAwareness(2)`). Screenshots are captured with `mss`, downscaled so the longest side is <= 1568px (`s = orig_w / sent_w`), and vision click coordinates are mapped back via `scale_coordinates(x, y, s)`. Validated on simulated 100%, 125%, and 150% displays.
- **Older Screenshot Pruning**: In `jarvis/brain/agent.py`, `_prune_older_screenshots(messages, keep_count=3)` retains base64 images only on the 3 most recent screenshots, replacing earlier image data with a placeholder to conserve token usage while maintaining visual context.
- **Native UI Automation First**: Dedicated tools `get_ui_elements` and `click_ui_element` leverage `pywinauto` with the UIA backend to inspect control hierarchies, names, types, and bounding rectangles. Ampersand accelerator keys are normalized and windows are brought to focus prior to interaction.
- **Vision Routing & Graceful Fallback**: For providers without image vision support, `read_screen_text` and `take_screenshot` provide structural descriptions based on active window and visible windows without crashing or sending raw images to text-only LLMs.

## Phase 7 Decisions
- **Persistent Long-Term SQLite Memory**: Database stored at `data/memory.db` with `facts` (key, value, created_at, updated_at) and `history` (role, content, timestamp) tables. Includes thread-safe locking and automatic migrations.
- **Sensitive Credential Shielding**: Memory manager regex and keyword filters unconditionally reject attempts to store credentials, tokens, passwords, or API keys (`sk-`, `gsk_`, `token`, `bearer`, etc.).
- **Automatic Context History & Fact Injection**: System prompts dynamically incorporate stored facts up to a 1500-character budget. Every assistant turn automatically archives exchanges into the persistent history table.
- **Persistent Playwright Automation**: Profile stored at `data/browser_profile` to preserve cookies, sessions, and state across restarts. Browser launches headed by default for user visibility, falling back seamlessly to headless mode when running in headless environments.
- **URL Scheme Normalization**: Implemented `_normalize_url` helper in `jarvis/tools/web.py` supporting `http://`, `https://`, `data:`, `file://`, and `about:` schemas without prepending redundant protocol prefixes.
## Phase 8 Decisions
- **Silent Windows Startup Registration**: Implemented `scripts/install_startup.py` configuring `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`. Points directly to `pythonw.exe` so Jarvis initializes silently on logon without spawning an intrusive console terminal window. Supports `--install`, `--uninstall`, and `--status` flags.
- **Named Mutex Single-Instance Lock**: Implemented `SingleInstanceMutex` in `jarvis/platform/mutex.py` using Windows `CreateMutexW` (`Local\JarvisDesktopAssistantSingleInstanceMutex`). If `ERROR_ALREADY_EXISTS` is reported, process exits immediately without corrupting shared resources.
- **Rate-Limited Crash Supervisor**: Implemented `CrashSupervisor` in `jarvis/crash_recovery.py` capturing unhandled exceptions, logging full tracebacks, and persisting crash timestamps in `data/crash_history.json`. Allows up to 3 automated restarts within a 1-hour rolling window before halting to prevent infinite failure loops.
- **Pre-Flight Diagnostic Verification**: Implemented `jarvis/setup_check.py` and `scripts/setup_check.py` (`python main.py --check-setup`) verifying active LLM API keys and model configuration, audio input devices via `sounddevice`, ONNX wake word models via `openwakeword`, speech synthesis via `edge-tts`/`pyttsx3`, and Playwright Chromium automation.
- **Graceful Multi-Component Teardown**: Updated `JarvisApp.stop()` to cleanly close the Playwright browser session, stop audio input streams, release the global kill switch hotkey, stop the system tray thread, and release the Windows named mutex.

## Local AI & Core Improvements Decisions
- **Hardware-Aware Local STT**: Detected NVIDIA GeForce RTX 3070 Laptop GPU (8GB VRAM) via `ctranslate2.get_cuda_device_count()`. Configured `faster-whisper` with `medium.en` model running on CUDA `float16` for near real-time, highly accurate English transcription. If CUDA is unavailable or initialization fails, automatically falls back to CPU `int8`.
- **Offline Neural TTS with Piper**: Integrated `piper-tts` using the `en_GB-alan-medium` ONNX neural model. Synthesis yields 22,050 Hz float32 PCM streams fed into `sounddevice`, avoiding intermediate file I/O. Multi-engine priority is configured as `piper` -> `edge-tts` -> `pyttsx3` with dynamic fallback and user-adjustable `speech_rate` and `volume`.
- **Universal Application Discovery (`AppResolver`)**: Decoupled application resolution into `jarvis/services/app_resolver.py`. Discovers executables across:
  1. System and user Start Menu `.lnk` shortcuts
  2. Public and user Desktop shortcuts
  3. Windows Registry `HKLM` and `HKCU\Software\Microsoft\Windows\CurrentVersion\App Paths`
  4. Windows Registry `Uninstall` entries
  5. Windows UWP / Store application links
  Discovered targets are cached in `data/apps_cache.json` with thread-safe persistence and automatic or manual refresh. Built-in alias precedence is maintained so common utility names (e.g. `editor` -> Notepad) are preserved. Disambiguation returns multiple matches when queries are ambiguous.
- **Hybrid Customizable Wake Words**: Built-in openWakeWord models (`hey_jarvis`, `alexa`, etc.) are supported out-of-the-box. For arbitrary custom phrases (e.g. `hey bro`, `hello assistant`), implemented a two-stage hybrid detector in `jarvis/audio/wakeword.py`:
  1. Stage 1: WebRTC VAD detects incoming speech segments in continuous 16kHz audio.
  2. Stage 2: Segment is verified via local Whisper transcription against normalized target phrases.
- **Phonetic Spoken URL Normalization**: Added `normalize_spoken_url()` in `jarvis/tools/web.py` to convert spoken URL patterns (e.g. "github dot com", "slash pull request") into valid HTTP URLs while preserving explicit schemes like `data:`, `file://`, and `about:`.
- **Expanded Windows System Automation**: Added `media_control` using Windows virtual key codes (`VK_MEDIA_PLAY_PAUSE`, `VK_MEDIA_NEXT_TRACK`, `VK_MEDIA_PREV_TRACK`, `VK_MEDIA_STOP`), `get_network_info` for interface status and IP address diagnostics, and `cancel_shutdown` (`shutdown /a`).
