"""Provider package for Jarvis LLMs.

Exposes factory function get_provider() to instantiate configured adapter.
"""

import os
from typing import Literal
from jarvis.brain.providers.base import (
    LLMProvider,
    LLMResponse,
    Msg,
    ToolCall,
    ToolResultMsg,
)
from jarvis.brain.providers.anthropic_provider import AnthropicProvider
from jarvis.brain.providers.gemini_provider import GeminiProvider
from jarvis.brain.providers.groq_provider import GroqProvider

_PROVIDER_MAP = {
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "groq": GroqProvider,
}


def get_provider(
    name: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> LLMProvider:
    """Factory function to get the appropriate LLM provider instance.

    Args:
        name: Provider name ('anthropic', 'gemini', 'groq'). Defaults to LLM_PROVIDER env.
        model: Specific model name override.
        api_key: Specific API key override.

    Returns:
        Configured LLMProvider instance.
    """
    prov_name = (name or os.getenv("LLM_PROVIDER", "anthropic")).strip().lower()
    provider_cls = _PROVIDER_MAP.get(prov_name)
    if not provider_cls:
        raise ValueError(
            f"Unsupported LLM provider: '{prov_name}'. Choose from: {list(_PROVIDER_MAP.keys())}"
        )
    return provider_cls(model=model, api_key=api_key)


__all__ = [
    "LLMProvider",
    "LLMResponse",
    "Msg",
    "ToolCall",
    "ToolResultMsg",
    "AnthropicProvider",
    "GeminiProvider",
    "GroqProvider",
    "get_provider",
]
