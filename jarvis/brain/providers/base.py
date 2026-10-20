"""Neutral data types and abstract interface for all LLM providers in Jarvis."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class ToolCall:
    """Represents a tool call requested by an LLM."""

    id: str
    name: str
    args: dict[str, Any]


@dataclass
class ToolResultMsg:
    """Represents the output of an executed tool call returned to the LLM."""

    call_id: str
    name: str
    output: str
    image_b64: str | None = None  # PNG, already downscaled


@dataclass
class Msg:
    """A message in the conversational history passed between the agent and LLM."""

    role: Literal["user", "assistant", "tool"]
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)  # assistant only
    tool_results: list[ToolResultMsg] = field(default_factory=list)  # role "tool" only
    images_b64: list[str] = field(default_factory=list)  # user images
    raw: Any = None  # Provider's original assistant message for exact replay


@dataclass
class LLMResponse:
    """Standardized response returned by any LLMProvider."""

    text: str
    tool_calls: list[ToolCall]
    raw: Any
    usage: dict[str, Any]


class LLMProvider(ABC):
    """Abstract base class for LLM providers (Anthropic, Gemini, Groq)."""

    name: str
    model: str
    supports_vision: bool
    supports_tools: bool

    @abstractmethod
    def chat(
        self,
        system: str,
        messages: list[Msg],
        tools: list[dict[str, Any]],
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        """Sends messages to the LLM and returns a standardized response.

        Args:
            system: The system prompt.
            messages: List of conversation messages in neutral Msg format.
            tools: List of tool schemas in standard format.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.

        Returns:
            LLMResponse containing text, tool_calls, raw object, and usage stats.
        """
        pass
