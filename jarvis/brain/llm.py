"""Provider-agnostic LLM execution orchestrator with retries, timeout, and fallback."""

import os
import time
from typing import Any
from jarvis.brain.providers import get_provider, LLMProvider, LLMResponse, Msg
from jarvis.config import config
from jarvis.logger import logger


def get_active_provider() -> LLMProvider:
    """Returns the primary LLMProvider configured in environment."""
    return get_provider()


def get_vision_provider() -> LLMProvider:
    """Returns the vision provider for image reading tasks.

    Uses VISION_PROVIDER and VISION_MODEL if set, otherwise defaults to primary provider.
    """
    vision_prov_name = os.getenv("VISION_PROVIDER", "").strip().lower()
    vision_model = os.getenv("VISION_MODEL", "").strip() or None

    if vision_prov_name:
        try:
            return get_provider(name=vision_prov_name, model=vision_model)
        except Exception as e:
            logger.warning("Failed to initialize vision provider '%s': %s", vision_prov_name, e)

    return get_active_provider()


def chat_with_retry(
    provider: LLMProvider,
    system: str,
    messages: list[Msg],
    tools: list[dict[str, Any]],
    max_tokens: int | None = None,
    temperature: float | None = None,
    on_fallback: Any = None,
) -> LLMResponse:
    """Executes chat with 3 retries, exponential backoff, latency logging, and fallback.

    Args:
        provider: Active LLMProvider instance.
        system: System prompt string.
        messages: List of conversation Msg objects.
        tools: List of tool specifications.
        max_tokens: Max tokens to generate.
        temperature: Sampling temperature.
        on_fallback: Optional callback called if switching to fallback provider.

    Returns:
        LLMResponse from provider.
    """
    llm_cfg = config.get("llm", {})
    tokens = max_tokens or llm_cfg.get("max_tokens", 1500)
    temp = temperature if temperature is not None else llm_cfg.get("temperature", 0.2)

    max_retries = 3
    delay = 1.0

    current_provider = provider
    last_exception: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            start_time = time.perf_counter()
            response = current_provider.chat(
                system=system,
                messages=messages,
                tools=tools,
                max_tokens=tokens,
                temperature=temp,
            )
            latency = time.perf_counter() - start_time

            logger.info(
                "LLM call succeeded | provider: %s | model: %s | latency: %.2fs | tokens: %s",
                current_provider.name,
                current_provider.model,
                latency,
                response.usage,
            )
            return response

        except Exception as exc:
            last_exception = exc
            logger.warning(
                "LLM call failed (attempt %d/%d) on %s (%s): %s",
                attempt,
                max_retries,
                current_provider.name,
                current_provider.model,
                exc,
            )
            if attempt < max_retries:
                time.sleep(delay)
                delay *= 2.0

    # Primary provider failed after all retries; check for fallback provider
    fallback_name = os.getenv("FALLBACK_PROVIDER", "").strip().lower()
    if fallback_name and fallback_name != current_provider.name:
        logger.warning(
            "Primary provider '%s' failed. Initiating fallback to '%s'",
            current_provider.name,
            fallback_name,
        )
        if callable(on_fallback):
            on_fallback("Switching to my backup brain.")

        try:
            fallback_provider = get_provider(name=fallback_name)
            start_time = time.perf_counter()
            response = fallback_provider.chat(
                system=system,
                messages=messages,
                tools=tools,
                max_tokens=tokens,
                temperature=temp,
            )
            latency = time.perf_counter() - start_time
            logger.info(
                "Fallback LLM call succeeded | provider: %s | model: %s | latency: %.2fs",
                fallback_provider.name,
                fallback_provider.model,
                latency,
            )
            return response
        except Exception as fb_exc:
            logger.error("Fallback provider '%s' also failed: %s", fallback_name, fb_exc)
            raise fb_exc

    raise RuntimeError(
        f"LLM request failed on {current_provider.name} after {max_retries} attempts: {last_exception}"
    )
