"""Anthropic provider adapter.

Wraps the official `anthropic` SDK and normalizes its response into the common
`Response` (ADR 0001 — the only place the Anthropic SDK is imported; kept thin).
The API key comes from the environment (`ANTHROPIC_API_KEY`), never config.
"""

from __future__ import annotations

from typing import Any, cast

from anthropic import AsyncAnthropic
from anthropic.types import Message, TextBlock, ToolUseBlock

from .base import Request, Response, ToolCall

_MAX_TOKENS = 4096


class AnthropicProvider:
    """A `Provider` backed by Anthropic. Serves any Claude model; `model` selects one."""

    def __init__(self, client: AsyncAnthropic | None = None) -> None:
        # Injectable for tests; otherwise built lazily from ANTHROPIC_API_KEY.
        self._client = client

    def _client_or_default(self) -> AsyncAnthropic:
        if self._client is None:
            self._client = AsyncAnthropic()  # reads ANTHROPIC_API_KEY from env
        return self._client

    async def invoke(self, request: Request, *, model: str) -> Response:
        client = self._client_or_default()
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": _MAX_TOKENS,
            "messages": [{"role": "user", "content": request.prompt}],
        }
        if request.tools:
            kwargs["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.parameters}
                for t in request.tools
            ]
        message = await client.messages.create(**kwargs)
        return self._normalize(message)

    @staticmethod
    def _normalize(message: Message) -> Response:
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in message.content:
            if isinstance(block, TextBlock):
                text_parts.append(block.text)
            elif isinstance(block, ToolUseBlock):
                arguments = cast("dict[str, Any]", block.input)
                tool_calls.append(ToolCall(name=block.name, arguments=arguments))
        return Response(text="".join(text_parts), tool_calls=tuple(tool_calls))
