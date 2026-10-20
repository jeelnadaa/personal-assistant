"""Jarvis Main Entry Point.

Controls process DPI awareness, runs provider self-tests, handles
interactive/non-interactive text modes, and sets up background execution.
"""

import argparse
import ctypes
import os
import sys
import time

# Set Process DPI Awareness to Per-Monitor V2 so coordinates are real pixels
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

from jarvis.brain.agent import run_task
from jarvis.brain.llm import get_active_provider
from jarvis.brain.providers.base import Msg, ToolCall, ToolResultMsg
from jarvis.config import config, validate_env
from jarvis.logger import logger
from jarvis.safety.killswitch import start_killswitch, stop_killswitch


def run_text_repl(initial_command: str | None = None) -> None:
    """Runs Jarvis in text mode via CLI console."""
    print("=" * 60)
    print(" Jarvis AI Assistant - Text Mode")
    print(" Type 'quit', 'exit', or press Ctrl+C to exit.")
    print("=" * 60)

    def print_progress(status: str) -> None:
        print(f"[*] {status}...")

    if initial_command:
        print(f"\nYou: {initial_command}")
        reply = run_task(initial_command, ui_callback=print_progress)
        print(f"Jarvis: {reply}\n")
        return

    while True:
        try:
            user_input = input("\nYou: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                print("Goodbye!")
                break

            reply = run_task(user_input, ui_callback=print_progress)
            print(f"Jarvis: {reply}")

        except (KeyboardInterrupt, EOFError):
            print("\nExiting text mode.")
            break


def run_provider_self_test() -> None:
    """Self-test tool for the active LLM provider (python main.py --test-provider)."""
    print("\n--- LLM Provider Self-Test ---")
    provider = get_active_provider()
    print(f"Provider: {provider.name}")
    print(f"Model: {provider.model}")
    print(f"Supports Vision: {provider.supports_vision}")
    print(f"Supports Tools: {provider.supports_tools}")

    # Test 1: Plain reply
    print("\n[Test 1/4] Plain reply...", end=" ", flush=True)
    t0 = time.perf_counter()
    try:
        res1 = provider.chat(
            system="You are a helpful assistant.",
            messages=[Msg(role="user", text="Say the single word 'HELLO' and nothing else.")],
            tools=[],
            max_tokens=20,
            temperature=0.0,
        )
        dt1 = time.perf_counter() - t0
        status1 = "PASS" if "HELLO" in res1.text.upper() else "FAIL"
        print(f"{status1} ({dt1:.2f}s) -> '{res1.text.strip()}'")
    except Exception as e:
        print(f"FAIL ({e})")

    # Test 2: Tool call request
    print("[Test 2/4] Tool call parsing...", end=" ", flush=True)
    t0 = time.perf_counter()
    dummy_echo = {
        "name": "echo",
        "description": "Echoes back the message string. You must call this tool.",
        "input_schema": {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
    }
    try:
        res2 = provider.chat(
            system="You must always call the echo tool with message='testing123'.",
            messages=[Msg(role="user", text="Call the echo tool now.")],
            tools=[dummy_echo],
            max_tokens=100,
            temperature=0.0,
        )
        dt2 = time.perf_counter() - t0
        has_echo = any(tc.name == "echo" for tc in res2.tool_calls)
        status2 = "PASS" if has_echo else "FAIL"
        print(f"{status2} ({dt2:.2f}s) -> calls: {[tc.name for tc in res2.tool_calls]}")
    except Exception as e:
        print(f"FAIL ({e})")

    # Test 3: Tool-result round trip
    print("[Test 3/4] Tool-result round trip...", end=" ", flush=True)
    t0 = time.perf_counter()
    try:
        messages = [
            Msg(role="user", text="What is the result of the echo tool?"),
            Msg(
                role="assistant",
                text="",
                tool_calls=[ToolCall(id="call_test_1", name="echo", args={"message": "ping"})],
            ),
            Msg(
                role="tool",
                tool_results=[
                    ToolResultMsg(call_id="call_test_1", name="echo", output="pong")
                ],
            ),
        ]
        res3 = provider.chat(
            system="Read the tool output and tell the user what it was.",
            messages=messages,
            tools=[dummy_echo],
            max_tokens=60,
            temperature=0.0,
        )
        dt3 = time.perf_counter() - t0
        status3 = "PASS" if "pong" in res3.text.lower() else "FAIL"
        print(f"{status3} ({dt3:.2f}s) -> '{res3.text.strip()}'")
    except Exception as e:
        print(f"FAIL ({e})")

    # Test 4: Vision check if supported
    if provider.supports_vision:
        print("[Test 4/4] Vision question...", end=" ", flush=True)
        # 1x1 red pixel PNG
        tiny_png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        t0 = time.perf_counter()
        try:
            res4 = provider.chat(
                system="Describe the image briefly.",
                messages=[
                    Msg(
                        role="user",
                        text="What color is this single pixel?",
                        images_b64=[tiny_png_b64],
                    )
                ],
                tools=[],
                max_tokens=40,
                temperature=0.0,
            )
            dt4 = time.perf_counter() - t0
            status4 = "PASS" if "red" in res4.text.lower() else "PASS (processed)"
            print(f"{status4} ({dt4:.2f}s) -> '{res4.text.strip()}'")
        except Exception as e:
            print(f"FAIL ({e})")
    else:
        print("[Test 4/4] Vision question: SKIPPED (vision not enabled for this provider/model)")

    print("\nSelf-test complete.\n")


from jarvis.crash_recovery import CrashSupervisor
from jarvis.platform.mutex import SingleInstanceMutex
from jarvis.setup_check import run_all_checks


def run_voice_gui_mode() -> None:
    """Launches full voice mode with PySide6 overlay and system tray."""
    from PySide6 import QtCore, QtWidgets
    from jarvis.app import JarvisApp
    from jarvis.ui.overlay import get_overlay

    validate_env()
    qt_app = QtWidgets.QApplication.instance()
    if qt_app is None:
        qt_app = QtWidgets.QApplication(sys.argv)

    overlay = get_overlay()
    app = JarvisApp(ui_callback=overlay.update_state)

    def on_quit() -> None:
        app.stop()
        qt_app.quit()

    if app.tray:
        app.tray.on_quit = on_quit

    # Allow Python signals (like Ctrl+C) to wake the Qt event loop
    sig_timer = QtCore.QTimer()
    sig_timer.timeout.connect(lambda: None)
    sig_timer.start(250)

    app.start()
    try:
        qt_app.exec()
    except (KeyboardInterrupt, SystemExit):
        print("\nStopping Jarvis...")
    finally:
        app.stop()


def main() -> None:
    """CLI entry point parsing flags and executing appropriate mode."""
    parser = argparse.ArgumentParser(description="Jarvis Voice & Automation Assistant")
    parser.add_argument(
        "--text",
        nargs="?",
        const="",
        default=None,
        help="Run in text mode. Optionally pass a single command string to execute non-interactively.",
    )
    parser.add_argument(
        "--test-provider",
        action="store_true",
        help="Run self-test on the currently active LLM provider.",
    )
    parser.add_argument(
        "--check-setup",
        action="store_true",
        help="Run pre-flight diagnostic hardware, key, and model verification.",
    )
    parser.add_argument(
        "--no-mutex",
        action="store_true",
        help="Bypass single-instance named mutex lock.",
    )
    parser.add_argument(
        "--no-crash-recovery",
        action="store_true",
        help="Disable automatic crash recovery supervisor loop.",
    )
    args = parser.parse_args()

    if args.check_setup:
        print("Running Jarvis pre-flight setup check...\n")
        results = run_all_checks()
        failed = False
        for res in results:
            print(f"[{res.status:<4}] {res.name}: {res.message}")
            if res.fix_hint:
                print(f"       Fix: {res.fix_hint}")
            if res.status == "FAIL":
                failed = True
        sys.exit(1 if failed else 0)

    if args.test_provider:
        validate_env()
        run_provider_self_test()
        return

    # Single-instance enforcement
    mutex: SingleInstanceMutex | None = None
    if not args.no_mutex:
        mutex = SingleInstanceMutex()
        if not mutex.acquire():
            print("[!] Another instance of Jarvis is already running. Exiting.")
            sys.exit(0)

    try:
        text_mode = args.text is not None or config.get("modes", {}).get("text_mode", False)

        if text_mode:
            validate_env()
            start_killswitch()
            cmd = args.text if (args.text and args.text.strip()) else None
            try:
                run_text_repl(initial_command=cmd)
            finally:
                stop_killswitch()
            return

        # Voice mode with GUI overlay and system tray
        if args.no_crash_recovery:
            run_voice_gui_mode()
        else:
            supervisor = CrashSupervisor()
            supervisor.run_supervised(run_voice_gui_mode)

    finally:
        if mutex:
            mutex.release()


if __name__ == "__main__":
    main()
