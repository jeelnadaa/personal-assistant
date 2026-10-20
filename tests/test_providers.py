"""Unit tests for message conversion logic of Anthropic, Gemini, and Groq adapters."""

from jarvis.brain.providers.anthropic_provider import AnthropicProvider
from jarvis.brain.providers.base import Msg, ToolCall, ToolResultMsg
from jarvis.brain.providers.gemini_provider import GeminiProvider, sanitize_schema_for_gemini
from jarvis.brain.providers.groq_provider import GroqProvider


def test_anthropic_message_conversion():
    """Verifies Anthropic adapter converts user, assistant, and tool result messages properly."""
    provider = AnthropicProvider(api_key="test_dummy_key")

    messages = [
        Msg(role="user", text="Open Notepad"),
        Msg(
            role="assistant",
            text="Opening it now.",
            tool_calls=[ToolCall(id="call_1", name="open_app", args={"name": "notepad"})],
        ),
        Msg(
            role="tool",
            tool_results=[ToolResultMsg(call_id="call_1", name="open_app", output="Launched notepad.")],
        ),
    ]

    converted = provider._convert_messages(messages)
    assert len(converted) == 3

    # User message
    assert converted[0]["role"] == "user"
    assert converted[0]["content"][0]["text"] == "Open Notepad"

    # Assistant message with tool_use block
    assert converted[1]["role"] == "assistant"
    blocks = converted[1]["content"]
    assert any(b["type"] == "tool_use" and b["name"] == "open_app" for b in blocks)

    # Tool result message (sent as role="user" with tool_result block in Anthropic)
    assert converted[2]["role"] == "user"
    assert converted[2]["content"][0]["type"] == "tool_result"
    assert converted[2]["content"][0]["tool_use_id"] == "call_1"


def test_gemini_schema_sanitization():
    """Verifies that sanitize_schema_for_gemini strips unsupported keys."""
    raw_schema = {
        "title": "DummySchema",
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {
                "type": "string",
                "title": "NameTitle",
                "default": "sample",
                "examples": ["val1"],
            }
        },
        "required": ["name"],
    }

    sanitized = sanitize_schema_for_gemini(raw_schema)
    assert "title" not in sanitized
    assert "$schema" not in sanitized
    assert "additionalProperties" not in sanitized
    assert "default" not in sanitized["properties"]["name"]
    assert "examples" not in sanitized["properties"]["name"]
    assert sanitized["properties"]["name"]["type"] == "string"


def test_gemini_message_conversion():
    """Verifies Gemini adapter converts Msg list to Content objects."""
    provider = GeminiProvider(api_key="test_dummy_key")

    messages = [
        Msg(role="user", text="Check battery"),
        Msg(
            role="assistant",
            text="",
            tool_calls=[ToolCall(id="call_123", name="get_system_info", args={})],
        ),
        Msg(
            role="tool",
            tool_results=[
                ToolResultMsg(call_id="call_123", name="get_system_info", output="Battery: 90%")
            ],
        ),
    ]

    contents = provider._convert_messages(messages)
    assert len(contents) >= 3
    assert contents[0].role == "user"
    assert contents[1].role == "model"
    assert contents[2].role == "user"


def test_groq_message_conversion():
    """Verifies Groq adapter converts messages into OpenAI format with role='tool'."""
    provider = GroqProvider(api_key="test_dummy_key")

    messages = [
        Msg(role="user", text="Search flights"),
        Msg(
            role="assistant",
            text=None,
            tool_calls=[ToolCall(id="call_groq_1", name="open_url", args={"url": "https://google.com"})],
        ),
        Msg(
            role="tool",
            tool_results=[
                ToolResultMsg(call_id="call_groq_1", name="open_url", output="Opened browser")
            ],
        ),
    ]

    converted = provider._convert_messages(messages)
    assert len(converted) == 3

    assert converted[0]["role"] == "user"
    assert converted[0]["content"] == "Search flights"

    assert converted[1]["role"] == "assistant"
    assert converted[1]["tool_calls"][0]["id"] == "call_groq_1"
    assert converted[1]["tool_calls"][0]["function"]["name"] == "open_url"

    assert converted[2]["role"] == "tool"
    assert converted[2]["tool_call_id"] == "call_groq_1"
    assert converted[2]["content"] == "Opened browser"
