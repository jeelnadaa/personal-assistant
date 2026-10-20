"""Unit tests for multi-session conversation context and natural dialogue handling."""

from datetime import datetime, timezone
import pytest

from jarvis.brain.context import ContextManager
from jarvis.brain.memory import (
    add_history,
    clear_all_history,
    get_recent_history,
    set_fact,
    delete_fact,
)
from jarvis.brain.prompts import build_system_prompt
from jarvis.brain.providers.base import LLMProvider, LLMResponse, Msg
from jarvis.brain.agent import run_task
from jarvis.tools.memory_tools import clear_history


class ConversationalMockProvider(LLMProvider):
    """Mock LLM Provider that answers conversationally and checks provided message history."""

    def __init__(self, reply: str) -> None:
        self.name = "mock_chat"
        self.model = "mock_chat_model"
        self.supports_vision = False
        self.supports_tools = True
        self.reply = reply
        self.received_messages: list[Msg] = []

    def chat(self, system: str, messages: list[Msg], tools: list[dict], max_tokens=800, temperature=0.2) -> LLMResponse:
        self.received_messages = list(messages)
        return LLMResponse(text=self.reply, tool_calls=[], raw=None, usage={})


def test_cross_session_context_persistence():
    """Verifies that conversation turns are stored in SQLite and automatically loaded into new ContextManager sessions."""
    # Clear any previous test history
    clear_all_history()

    # Session 1: User has a conversation
    ctx_session1 = ContextManager()
    ctx_session1.save_exchange(
        user_text="I'm planning to bake sourdough bread today.",
        assistant_reply="Sounds wonderful, sir. Remember to give the dough adequate fermentation time.",
    )

    # Verify saved in SQLite history
    history = get_recent_history(limit=5)
    assert len(history) >= 1
    assert "sourdough bread" in history[-1]["user_text"]
    assert "fermentation time" in history[-1]["assistant_reply"]

    # Session 2: User closes app and opens fresh session (simulating restart / new day)
    ctx_session2 = ContextManager()
    history_msgs = ctx_session2.get_history_messages()
    assert len(history_msgs) >= 2
    assert any("sourdough bread" in m.text for m in history_msgs if m.role == "user")
    assert any("fermentation time" in m.text for m in history_msgs if m.role == "assistant")

    # Cleanup
    clear_all_history()


def test_agent_loop_conversational_turn_with_history():
    """Verifies that run_task sends past conversation history to the LLM and records the new conversational turn."""
    clear_all_history()

    # Seed past exchange
    add_history("What is your favorite color?", "I quite fancy British racing green, sir.")

    # Fresh ContextManager will load that turn
    from jarvis.brain.context import context_manager
    context_manager.load_from_storage()

    mock = ConversationalMockProvider("I am functioning with optimal efficiency, sir. How may I assist you?")
    reply = run_task("Good morning Jarvis, how are you?", provider=mock)

    assert "optimal efficiency" in reply

    # Verify mock provider received the past turn in its message list
    user_msgs = [m.text for m in mock.received_messages if m.role == "user"]
    assert any("favorite color" in text for text in user_msgs)
    assert any("Good morning Jarvis" in text for text in user_msgs)

    # Verify the new turn was persisted
    history = get_recent_history(limit=5)
    assert any("Good morning Jarvis" in h["user_text"] for h in history)

    # Cleanup
    clear_all_history()


def test_clear_history_tool():
    """Verifies that the clear_history tool purges active and persistent context."""
    add_history("Tell me a secret", "I cannot do that, sir.")
    from jarvis.brain.context import context_manager
    context_manager.load_from_storage()
    assert len(context_manager.exchanges) >= 1

    res = clear_history(clear_all=True)
    assert res.ok is True
    assert "Cleared all past and active" in res.output

    assert len(context_manager.exchanges) == 0
    assert len(get_recent_history()) == 0


def test_conversational_system_prompt_guidance():
    """Verifies that system prompt incorporates conversational instructions and personality."""
    prompt = build_system_prompt()
    assert "Normal Conversation" in prompt or "CONVERSATION" in prompt
    assert "Context Across Sessions" in prompt or "previous topics" in prompt
