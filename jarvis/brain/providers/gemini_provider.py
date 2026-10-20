"""Gemini LLM provider adapter using the official google-genai SDK."""

import base64
import os
import uuid
from typing import Any
from google import genai
from google.genai import types

from jarvis.brain.providers.base import (
    LLMProvider,
    LLMResponse,
    Msg,
    ToolCall,
)
from jarvis.logger import logger


def sanitize_schema_for_gemini(schema: dict[str, Any]) -> dict[str, Any]:
    """Recursively removes schema attributes unsupported by Gemini.

    Strips: additionalProperties, default, $schema, examples, title.
    """
    disallowed_keys = {"additionalProperties", "default", "$schema", "examples", "title"}
    sanitized: dict[str, Any] = {}

    for k, v in schema.items():
        if k in disallowed_keys:
            continue
        if isinstance(v, dict):
            sanitized[k] = sanitize_schema_for_gemini(v)
        elif isinstance(v, list):
            sanitized[k] = [
                sanitize_schema_for_gemini(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            sanitized[k] = v

    return sanitized


class GeminiProvider(LLMProvider):
    """Adapter for Google Gemini models via google-genai SDK."""

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self.name = "gemini"
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.client = genai.Client(api_key=key) if key else None
        self.supports_vision = True
        self.supports_tools = True

    def _convert_messages(self, messages: list[Msg]) -> list[types.Content]:
        """Converts internal Msg list into Gemini Content objects."""
        contents: list[types.Content] = []

        for msg in messages:
            if msg.role == "user":
                parts: list[types.Part] = []
                if msg.text:
                    parts.append(types.Part.from_text(text=msg.text))
                for img_b64 in msg.images_b64:
                    try:
                        raw_bytes = base64.b64decode(img_b64)
                        parts.append(types.Part.from_bytes(data=raw_bytes, mime_type="image/png"))
                    except Exception as e:
                        logger.warning("Failed to decode user image b64: %s", e)
                contents.append(types.Content(role="user", parts=parts))

            elif msg.role == "assistant":
                if msg.raw is not None and isinstance(msg.raw, types.Content):
                    contents.append(msg.raw)
                else:
                    parts = []
                    if msg.text:
                        parts.append(types.Part.from_text(text=msg.text))
                    for tc in msg.tool_calls:
                        parts.append(
                            types.Part.from_function_call(name=tc.name, args=tc.args)
                        )
                    contents.append(types.Content(role="model", parts=parts))

            elif msg.role == "tool":
                func_parts: list[types.Part] = []
                image_parts: list[types.Part] = []
                for res in msg.tool_results:
                    func_parts.append(
                        types.Part.from_function_response(
                            name=res.name,
                            response={"output": res.output},
                        )
                    )
                    if res.image_b64:
                        try:
                            raw_bytes = base64.b64decode(res.image_b64)
                            image_parts.append(
                                types.Part.from_bytes(data=raw_bytes, mime_type="image/png")
                            )
                        except Exception as e:
                            logger.warning("Failed to decode tool image b64: %s", e)

                if func_parts:
                    contents.append(types.Content(role="user", parts=func_parts))
                if image_parts:
                    contents.append(types.Content(role="user", parts=image_parts))

        return contents

    def chat(
        self,
        system: str,
        messages: list[Msg],
        tools: list[dict[str, Any]],
        max_tokens: int = 1500,
        temperature: float = 0.2,
    ) -> LLMResponse:
        """Sends chat request to Gemini API."""
        if not self.client:
            raise ValueError("GEMINI_API_KEY is not configured.")

        contents = self._convert_messages(messages)

        func_decls = []
        for t in tools:
            sanitized_schema = sanitize_schema_for_gemini(t.get("input_schema", {}))
            func_decls.append({
                "name": t["name"],
                "description": t["description"],
                "parameters": sanitized_schema,
            })

        gen_tools = [types.Tool(function_declarations=func_decls)] if func_decls else None

        config = types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            temperature=temperature,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            tools=gen_tools,
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=config,
        )

        extracted_text = ""
        tool_calls: list[ToolCall] = []
        raw_content = None

        if response.candidates and response.candidates[0].content:
            raw_content = response.candidates[0].content
            for part in raw_content.parts:
                if part.text:
                    extracted_text += part.text
                if part.function_call:
                    fc = part.function_call
                    call_id = f"call_{uuid.uuid4().hex[:8]}"
                    tool_calls.append(
                        ToolCall(
                            id=call_id,
                            name=fc.name,
                            args=fc.args if isinstance(fc.args, dict) else {},
                        )
                    )

        usage = {}
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            usage = {
                "input_tokens": getattr(response.usage_metadata, "prompt_token_count", 0),
                "output_tokens": getattr(response.usage_metadata, "candidates_token_count", 0),
            }

        return LLMResponse(
            text=extracted_text,
            tool_calls=tool_calls,
            raw=raw_content,
            usage=usage,
        )
