"""Unit tests for the agent loop using a mock LLM provider."""

from typing import Any
import pytest

from jarvis.brain.agent import cancel_current_task, reset_cancel_event, run_task
from jarvis.brain.providers.base import (
    LLMProvider,
    LLMResponse,
    Msg,
    ToolCall,
)
from jarvis.tools.base import ToolResult, tool


class FakeLLMProvider(LLMProvider):
    """Mock LLM Provider that plays back predefined LLM responses."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self.name = "fake_llm"
        self.model = "fake_model"
        self.supports_vision = True
        self.supports_tools = True
        self.responses = list(responses)
        self.recorded_calls: list[dict[str, Any]] = []

    def chat(
        self,
        system: str,
        messages: list[Msg],
        tools: list[dict[str, Any]],
        max_tokens: int = 1500,
        temperature: float = 0.2,
    ) -> LLMResponse:
        self.recorded_calls.append({
            "system": system,
            "messages": messages,
            "tools": tools,
        })
        if self.responses:
            return self.responses.pop(0)
        return LLMResponse(text="Default final reply", tool_calls=[], raw=None, usage={})


def test_agent_loop_tool_execution_and_completion():
    """Verifies that the agent loop executes tool calls and terminates with final text."""
    # Step 1: LLM requests get_system_info
    # Step 2: LLM receives tool output and returns final spoken answer
    resp1 = LLMResponse(
        text="",
        tool_calls=[ToolCall(id="call_123", name="get_system_info", args={})],
        raw=None,
        usage={"input_tokens": 10, "output_tokens": 15},
    )
    resp2 = LLMResponse(
        text="The current time is 10:00 PM and battery is at 95 percent.",
        tool_calls=[],
        raw=None,
        usage={"input_tokens": 40, "output_tokens": 20},
    )

    fake_provider = FakeLLMProvider([resp1, resp2])
    reply = run_task("what time is it and how much battery do I have", provider=fake_provider)

    assert "10:00 PM" in reply
    assert len(fake_provider.recorded_calls) == 2

    # Second call should include the tool result message
    last_messages = fake_provider.recorded_calls[1]["messages"]
    tool_msgs = [m for m in last_messages if m.role == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0].tool_results[0].call_id == "call_123"
    assert "CPU Usage:" in tool_msgs[0].tool_results[0].output


def test_agent_loop_infinite_loop_protection():
    """Verifies that calling the same tool with identical arguments 3 times aborts cleanly."""
    resp = LLMResponse(
        text="",
        tool_calls=[ToolCall(id="loop_call", name="get_system_info", args={})],
        raw=None,
        usage={},
    )
    fake_provider = FakeLLMProvider([resp, resp, resp, resp])
    reply = run_task("test infinite loop", provider=fake_provider)

    assert "stuck repeating" in reply


def test_agent_loop_kill_switch():
    """Verifies that setting the cancel event stops the task."""
    resp = LLMResponse(
        text="",
        tool_calls=[ToolCall(id="call_1", name="get_system_info", args={})],
        raw=None,
        usage={},
    )
    fake_provider = FakeLLMProvider([resp])

    # Cancel before running
    cancel_current_task()
    reply = run_task("test cancel", provider=fake_provider)
    assert "stopped" in reply

    # Mid-task cancellation via progress callback
    fake_provider2 = FakeLLMProvider([resp, resp])
    reply2 = run_task(
        "test cancel mid task",
        ui_callback=lambda status: cancel_current_task() if "running" in status else None,
        provider=fake_provider2,
    )
    assert "stopped" in reply2
    reset_cancel_event()

