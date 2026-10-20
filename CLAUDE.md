# Jarvis - Voice-Controlled AI Assistant for Windows 11

## 0. Rules for Coding Agent

1. **Work in phases.** Build Phase 1, run its tests, make them pass, `git commit`, then go to the next phase. Never start a phase until the previous phase's acceptance tests pass.
2. **Run the code yourself.** After writing code, run it. If it errors, read the error, fix it, and run again. Do not ask me to debug unless you have failed 5 times in a row on the same error.
3. **No fake code.** Every function must really work. No `pass`, no `# implement later`, no mock results presented as real.
4. **One responsibility per file.** Keep files short (under 250 lines where possible).
5. **Type hints and docstrings** on every function.
6. **Log everything** to `logs/jarvis.log` (rotating file). Never use bare `print` for runtime info except in the CLI.
7. **Never hardcode secrets.** API keys go in `.env` (loaded with `python-dotenv`). Provide `.env.example`.
8. **Windows only.** Target Windows 11, Python 3.11+. Use `pathlib`, not string paths.
9. **After each phase**, update `README.md` with how to run and test what exists so far, and tick the phase in `PROGRESS.md`.
10. **Ask before installing anything outside `requirements.txt`.**

## Architecture Summary

```
[idle] -> wake word detected ("hey jarvis")
       -> show overlay + beep
       -> record speech until silence (webrtcvad)
       -> speech-to-text (faster-whisper / Groq) -> user_text
       -> AGENT LOOP:
            messages = [system_prompt, memory_context, user_text]
            repeat (max 25 iterations):
                response = LLM(messages, tools=tool_schemas)
                if response has tool calls:
                    for each tool call:
                        if tool is dangerous -> ask user for confirmation (voice or button)
                        result = run_tool(name, args)
                        append tool result to messages
                    continue
                else:
                    final_text = response.text
                    break
       -> text-to-speech(final_text) (edge-tts / pyttsx3)
       -> hide overlay -> [idle]
```

### Core Components
- **Audio pipeline**: `mic.py` (sounddevice), `wakeword.py` (openwakeword), `stt.py` (faster-whisper), `tts.py` (edge-tts / pyttsx3 fallback), `sounds.py` (numpy synth beeps).
- **Brain**: `agent.py` (loop), `llm.py` (retry, fallback, vision routing), `providers/` (Anthropic, Gemini, Groq), `prompts.py`, `context.py`, `memory.py` (sqlite3).
- **Tools**: auto-discovered registry in `tools/__init__.py`, `@tool` decorator, granular PC automation modules (`apps`, `windows_mgmt`, `system`, `files`, `web`, `input_control`, `screen`, `clipboard`, `shell`, `memory_tools`).
- **Safety**: `policy.py`, `confirm.py`, `audit.py` (JSONL log), Ctrl+Alt+J global kill switch.
- **UI**: `overlay.py` (PySide6 translucent non-activating window), `tray.py` (pystray).
- **App state machine**: `app.py` wiring states IDLE, LISTENING, PROCESSING, SPEAKING, CONFIRMING, PAUSED.
