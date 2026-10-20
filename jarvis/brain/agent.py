"""Core agent loop orchestrating LLM tool calling, safety policies, and execution."""

import base64
import json
from pathlib import Path
import threading
from typing import Any, Callable

from jarvis.brain.context import context_manager
from jarvis.brain.llm import chat_with_retry, get_active_provider
from jarvis.brain.prompts import build_system_prompt
from jarvis.brain.providers.base import LLMProvider, Msg, ToolCall, ToolResultMsg
from jarvis.config import config
from jarvis.logger import logger
from jarvis.safety import confirm, policy
from jarvis.tools import get_tool_schemas, run_tool
from jarvis.tools.base import ToolResult

# Global cancel event for kill switch
TASK_CANCEL_EVENT = threading.Event()


def cancel_current_task() -> None:
    """Signals the agent loop to cancel current task immediately."""
    TASK_CANCEL_EVENT.set()
    try:
        from jarvis.ui.overlay import get_overlay
        overlay = get_overlay()
        if hasattr(overlay, "_confirm_event"):
            overlay._confirm_result = False
            overlay._confirm_event.set()
    except Exception:
        pass


def reset_cancel_event() -> None:
    """Resets the task cancellation event."""
    TASK_CANCEL_EVENT.clear()


def is_task_cancelled() -> bool:
    """Checks if cancellation has been signaled."""
    return TASK_CANCEL_EVENT.is_set()


def _describe_action(name: str, args: dict[str, Any]) -> str:
    """Generates a human-friendly description of a tool action for confirmation."""
    if name == "close_app":
        return f"close the application '{args.get('name')}'"
    if name == "delete_file":
        return f"send '{args.get('path')}' to the Recycle Bin"
    if name == "run_command":
        return f"execute shell command '{args.get('command')}'"
    if name == "shutdown_pc":
        return f"perform {args.get('action', 'shutdown')} on your PC"
    if name == "write_text_file":
        return f"write/overwrite file at '{args.get('path')}'"
    if name == "move_file":
        return f"move '{args.get('src')}' to '{args.get('dst')}'"
    if name == "hotkey":
        return f"press keyboard shortcut {args.get('keys')}"
    return f"execute {name} with arguments {json.dumps(args)}"


def _summarize_action(tc: ToolCall, result: ToolResult) -> str:
    """Summarizes a completed tool execution for context tracking."""
    status = "ok" if result.ok else "failed"
    return f"{tc.name} ({status})"


def _encode_image_b64(image_path: str) -> str | None:
    """Reads, downscales to max 1568px keeping aspect ratio, and encodes image as base64 string."""
    try:
        p = Path(image_path)
        if p.exists():
            import io
            from PIL import Image
            from jarvis.tools.screen import calculate_downscale_dimensions

            with Image.open(p) as im:
                orig_w, orig_h = im.size
                sent_w, sent_h, scale = calculate_downscale_dimensions(orig_w, orig_h, max_side=1568)
                if scale != 1.0:
                    im = im.resize((sent_w, sent_h), Image.Resampling.LANCZOS)
                buf = io.BytesIO()
                im.save(buf, format="PNG")
                return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as exc:
        logger.warning("Failed to encode image at %s: %s", image_path, exc)
    return None


def _prune_older_screenshots(messages: list[Msg], keep_count: int = 3) -> None:
    """Retains only the latest N screenshots in messages, replacing older ones with a token placeholder."""
    screenshot_entries: list[tuple[Msg, ToolResultMsg]] = []
    for msg in messages:
        if msg.role == "tool":
            for tr in msg.tool_results:
                if tr.image_b64:
                    screenshot_entries.append((msg, tr))

    if len(screenshot_entries) > keep_count:
        to_prune = screenshot_entries[:-keep_count]
        for _, tr in to_prune:
            tr.image_b64 = None
            tr.output += "\n[old screenshot removed]"


def run_task(
    user_text: str,
    ui_callback: Callable[[str], None] | None = None,
    provider: LLMProvider | None = None,
) -> str:
    """Runs the main agent loop for a user request.

    Repeats LLM calls, validates safety, executes tools, updates context,
    and returns a short conversational response.

    Args:
        user_text: Spoken or typed user instruction.
        ui_callback: Optional progress reporter (e.g. 'thinking', 'running open_app').
        provider: Optional LLMProvider override (used in unit tests).

    Returns:
        Spoken confirmation or answer string.
    """
    if is_task_cancelled():
        reset_cancel_event()
        return "Task was stopped."

    reset_cancel_event()

    def notify(state: str) -> None:
        if ui_callback:
            try:
                ui_callback(state)
            except Exception:
                pass

    try:
        active_provider = provider or get_active_provider()
        system = build_system_prompt()
        messages = context_manager.get_history_messages()
        messages.append(Msg(role="user", text=user_text))

        llm_cfg = config.get("llm", {})
        safety_cfg = config.get("safety", {})
        max_iterations = llm_cfg.get("max_iterations", 25)
        max_actions = safety_cfg.get("max_actions_per_task", 40)

        actions_taken: list[str] = []
        action_count = 0
        recent_calls: list[tuple[str, str]] = []

        for _ in range(max_iterations):
            if is_task_cancelled():
                return "Task was stopped."

            notify("thinking")
            response = chat_with_retry(
                provider=active_provider,
                system=system,
                messages=messages,
                tools=get_tool_schemas(),
                on_fallback=lambda msg: notify(msg),
            )

            messages.append(
                Msg(
                    role="assistant",
                    text=response.text,
                    tool_calls=response.tool_calls,
                    raw=response.raw,
                )
            )

            if not response.tool_calls:
                context_manager.save_exchange(user_text, response.text, actions_taken)
                return response.text

            results: list[ToolResultMsg] = []
            for tc in response.tool_calls:
                if is_task_cancelled():
                    return "Task was stopped."

                # Infinite loop protection: same tool and arguments 3 times in a row
                call_sig = (tc.name, json.dumps(tc.args, sort_keys=True))
                recent_calls.append(call_sig)
                if len(recent_calls) >= 3 and recent_calls[-1] == recent_calls[-2] == recent_calls[-3]:
                    logger.warning("Detected repeated identical tool call: %s", tc.name)
                    return f"I stopped because I got stuck repeating the {tc.name} action."

                action_count += 1
                if action_count > max_actions:
                    logger.warning("Exceeded maximum actions per task (%d)", max_actions)
                    return "I stopped because the task required too many actions."

                notify(f"running {tc.name}")

                if policy.requires_confirmation(tc.name, tc.args):
                    desc = _describe_action(tc.name, tc.args)
                    approved = confirm.ask(desc)
                    if not approved:
                        result = ToolResult(
                            ok=False,
                            output="User denied this action. Do not retry it. Inform the user you stopped.",
                        )
                    else:
                        result = run_tool(tc.name, tc.args)
                else:
                    result = run_tool(tc.name, tc.args)

                actions_taken.append(_summarize_action(tc, result))
                context_manager.update_session_state(tc, result)

                img_b64 = _encode_image_b64(result.image_path) if result.image_path else None
                results.append(
                    ToolResultMsg(
                        call_id=tc.id,
                        name=tc.name,
                        output=result.output,
                        image_b64=img_b64,
                    )
                )

            messages.append(Msg(role="tool", tool_results=results))
            _prune_older_screenshots(messages, keep_count=3)

        summary = ", ".join(actions_taken[-5:]) if actions_taken else "none"
        return f"I reached the step limit before completing everything. Recent actions: {summary}."

    except Exception as exc:
        logger.exception("Unhandled error in agent run_task: %s", exc)
        return "I'm sorry, I ran into an error while trying to complete that."
