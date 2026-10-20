"""Groq LLM provider adapter using the official groq SDK."""

import json
import os
from typing import Any
import groq

from jarvis.brain.providers.base import (
    LLMProvider,
    LLMResponse,
    Msg,
    ToolCall,
)
from jarvis.logger import logger


class GroqProvider(LLMProvider):
    """Adapter for Groq-hosted open-weights models."""

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self.name = "groq"
        self.model = model or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        key = api_key or os.getenv("GROQ_API_KEY", "")
        self.client = groq.Groq(api_key=key) if key else None

        # Check vision support from env or model name
        force_vision = os.getenv("FORCE_VISION", "").strip().lower()
        if force_vision in ("true", "1", "yes"):
            self.supports_vision = True
        elif force_vision in ("false", "0", "no"):
            self.supports_vision = False
        else:
            self.supports_vision = "vision" in self.model.lower()

        self.supports_tools = True

    def _convert_messages(self, messages: list[Msg]) -> list[dict[str, Any]]:
        """Converts internal Msg list to OpenAI/Groq chat completion messages."""
        api_messages: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role == "user":
                if msg.images_b64 and self.supports_vision:
                    content: list[dict[str, Any]] = []
                    if msg.text:
                        content.append({"type": "text", "text": msg.text})
                    for img_b64 in msg.images_b64:
                        content.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                        })
                    api_messages.append({"role": "user", "content": content})
                else:
                    api_messages.append({"role": "user", "content": msg.text})

            elif msg.role == "assistant":
                if msg.raw is not None and isinstance(msg.raw, dict):
                    api_messages.append(msg.raw)
                else:
                    item: dict[str, Any] = {"role": "assistant", "content": msg.text or None}
                    if msg.tool_calls:
                        item["tool_calls"] = [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.name,
                                    "arguments": json.dumps(tc.args),
                                },
                            }
                            for tc in msg.tool_calls
                        ]
                    api_messages.append(item)

            elif msg.role == "tool":
                for res in msg.tool_results:
                    api_messages.append({
                        "role": "tool",
                        "tool_call_id": res.call_id,
                        "name": res.name,
                        "content": res.output,
                    })
                    if res.image_b64 and self.supports_vision:
                        api_messages.append({
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/png;base64,{res.image_b64}"},
                                }
                            ],
                        })

        return api_messages

    def chat(
        self,
        system: str,
        messages: list[Msg],
        tools: list[dict[str, Any]],
        max_tokens: int = 1500,
        temperature: float = 0.2,
    ) -> LLMResponse:
        """Sends chat completion request to Groq API."""
        if not self.client:
            raise ValueError("GROQ_API_KEY is not configured.")

        converted_messages = [{"role": "system", "content": system}]
        converted_messages.extend(self._convert_messages(messages))

        formatted_tools = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                },
            }
            for t in tools
        ]

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": converted_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if formatted_tools:
            kwargs["tools"] = formatted_tools
            kwargs["tool_choice"] = "auto"

        response = self.client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        msg = choice.message

        extracted_text = msg.content or ""
        tool_calls: list[ToolCall] = []

        if msg.tool_calls:
            for tc in msg.tool_calls:
                parsed_args: dict[str, Any] = {}
                try:
                    if tc.function.arguments:
                        parsed_args = json.loads(tc.function.arguments)
                except Exception as err:
                    logger.warning("Failed to parse arguments JSON from Groq for %s: %s", tc.function.name, err)
                    parsed_args = {"_error": f"Invalid JSON arguments: {tc.function.arguments}"}

                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        args=parsed_args,
                    )
                )

        usage = {}
        if response.usage:
            usage = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            }

        return LLMResponse(
            text=extracted_text,
            tool_calls=tool_calls,
            raw=msg.model_dump() if hasattr(msg, "model_dump") else msg,
            usage=usage,
        )
