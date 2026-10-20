"""Anthropic LLM provider adapter using the official anthropic SDK."""

import os
from typing import Any
import anthropic

from jarvis.brain.providers.base import (
    LLMProvider,
    LLMResponse,
    Msg,
    ToolCall,
)
from jarvis.logger import logger


from jarvis.security.vault import get_secret


class AnthropicProvider(LLMProvider):
    """Adapter for Anthropic Claude models."""

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self.name = "anthropic"
        self.model = model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
        key = api_key or get_secret("ANTHROPIC_API_KEY", "")
        self.client = anthropic.Anthropic(api_key=key) if key else None
        self.supports_vision = True
        self.supports_tools = True

    def _convert_messages(self, messages: list[Msg]) -> list[dict[str, Any]]:
        """Converts internal Msg objects to Anthropic message format."""
        api_messages: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role == "user":
                content_blocks: list[dict[str, Any]] = []
                if msg.text:
                    content_blocks.append({"type": "text", "text": msg.text})
                for img_b64 in msg.images_b64:
                    content_blocks.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": img_b64,
                        },
                    })
                api_messages.append({"role": "user", "content": content_blocks})

            elif msg.role == "assistant":
                if msg.raw is not None and hasattr(msg.raw, "content"):
                    api_messages.append({"role": "assistant", "content": msg.raw.content})
                else:
                    blocks: list[dict[str, Any]] = []
                    if msg.text:
                        blocks.append({"type": "text", "text": msg.text})
                    for tc in msg.tool_calls:
                        blocks.append({
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.args,
                        })
                    api_messages.append({"role": "assistant", "content": blocks})

            elif msg.role == "tool":
                # Anthropic groups all tool results of one step into a single user message
                tool_result_blocks: list[dict[str, Any]] = []
                for res in msg.tool_results:
                    if res.image_b64:
                        content: list[dict[str, Any]] = [
                            {"type": "text", "text": res.output},
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": res.image_b64,
                                },
                            },
                        ]
                    else:
                        content = [{"type": "text", "text": res.output}]

                    tool_result_blocks.append({
                        "type": "tool_result",
                        "tool_use_id": res.call_id,
                        "content": content,
                    })
                api_messages.append({"role": "user", "content": tool_result_blocks})

        return api_messages

    def chat(
        self,
        system: str,
        messages: list[Msg],
        tools: list[dict[str, Any]],
        max_tokens: int = 1500,
        temperature: float = 0.2,
    ) -> LLMResponse:
        """Sends chat request to Anthropic API."""
        if not self.client:
            raise ValueError("ANTHROPIC_API_KEY is not configured.")

        converted_messages = self._convert_messages(messages)
        formatted_tools = [
            {
                "name": t["name"],
                "description": t["description"],
                "input_schema": t["input_schema"],
            }
            for t in tools
        ]

        kwargs: dict[str, Any] = {
            "model": self.model,
            "system": system,
            "messages": converted_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if formatted_tools:
            kwargs["tools"] = formatted_tools

        response = self.client.messages.create(**kwargs)

        extracted_text = ""
        tool_calls: list[ToolCall] = []

        for block in response.content:
            if block.type == "text":
                extracted_text += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        args=block.input if isinstance(block.input, dict) else {},
                    )
                )

        usage = {
            "input_tokens": getattr(response.usage, "input_tokens", 0),
            "output_tokens": getattr(response.usage, "output_tokens", 0),
        }

        return LLMResponse(
            text=extracted_text,
            tool_calls=tool_calls,
            raw=response,
            usage=usage,
        )
