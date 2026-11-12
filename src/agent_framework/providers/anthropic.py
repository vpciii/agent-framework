"""Anthropic provider adapter.

Wraps the official `anthropic` SDK and normalizes its response into the common
`Response` (ADR 0001 — the only place the Anthropic SDK is imported; kept thin).
Credentials come from the environment (`ANTHROPIC_API_KEY`, or Workload Identity
Federation variables), never config.
"""

from __future__ import annotations

import json
from typing import Any, cast

from anthropic import AnthropicError, APIError, AsyncAnthropic
from anthropic.types import Message, TextBlock, ToolUseBlock

from ..errors import ProviderError
from .base import Request, Response, StopReason, ToolCall, ToolDef, Usage

# The output limit when a request names none. Thinking is always on for the
# provider's current models and is counted against the limit, so a small
# default truncates ordinary answers (specs/judgment-reliability).
DEFAULT_MAX_OUTPUT_TOKENS = 16_000

# The provider's stop reasons, in the interface's vocabulary. Anything not
# listed is "other".
_STOP: dict[str, StopReason] = {
    "end_turn": "complete",
    "tool_use": "complete",
    "stop_sequence": "complete",
    "max_tokens": "truncated",
    "refusal": "refused",
}


class AnthropicProvider:
    """A `Provider` backed by Anthropic. Serves any Claude model; `model` selects one."""

    def __init__(self, client: AsyncAnthropic | None = None) -> None:
        # Injectable for tests; otherwise built lazily from the environment.
        self._client = client

    def _client_or_default(self) -> AsyncAnthropic:
        if self._client is None:
            try:
                self._client = AsyncAnthropic()  # API key or federation, from env
            except AnthropicError as e:
                # The SDK refuses to build a client from credentials it was
                # pointed at and cannot load: a request the provider cannot
                # serve, not a bug to show as a traceback.
                raise ProviderError(f"no Anthropic client: {type(e).__name__}: {e}") from e
        return self._client

    async def invoke(self, request: Request, *, model: str) -> Response:
        client = self._client_or_default()
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": request.max_output_tokens or DEFAULT_MAX_OUTPUT_TOKENS,
            "messages": [{"role": "user", "content": request.prompt}],
        }
        required = request.required()
        if required is not None:
            # The provider enforces the required answer as structured output:
            # the tool's parameter schema is the required format, and the JSON
            # that comes back is returned as a call to the tool. This holds on
            # every model the provider serves — including those that refuse a
            # forced tool choice — so no model is named here. No tools are
            # offered alongside it: the answer *is* the call.
            kwargs["output_config"] = {
                "format": {"type": "json_schema", "schema": required.parameters}
            }
        elif request.tools:
            kwargs["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.parameters}
                for t in request.tools
            ]
        if request.effort is not None:
            # The provider's control for how much to reason is the output
            # effort; it rides beside the answer format when there is one.
            kwargs.setdefault("output_config", {})["effort"] = request.effort
        try:
            message = await client.messages.create(**kwargs)
        except (APIError, TypeError) as e:
            # TypeError is how the SDK says it found no credentials: it is
            # raised as the request is built, before anything is sent.
            raise ProviderError(f"{type(e).__name__}: {e}") from e
        return self._normalize(message, required)

    async def list_models(self) -> tuple[str, ...]:
        """Model IDs this account can use (`ModelCatalog`). No probe: an
        Anthropic request costs tokens and the response echoes the request."""
        client = self._client_or_default()
        return tuple([m.id async for m in client.models.list()])

    @staticmethod
    def _normalize(message: Message, required: ToolDef | None = None) -> Response:
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in message.content:
            if isinstance(block, TextBlock):
                text_parts.append(block.text)
            elif isinstance(block, ToolUseBlock):
                arguments = cast("dict[str, Any]", block.input)
                tool_calls.append(ToolCall(name=block.name, arguments=arguments))
        text = "".join(text_parts)

        detail = message.stop_reason or ""
        stop: StopReason = _STOP.get(detail, "other") if detail else "complete"

        if required is not None and stop == "complete":
            # A complete structured answer is the required tool's arguments.
            # A cut-off or declined response carries no answer: its text is
            # left as text for the caller to report.
            try:
                answer: object = json.loads(text)
            except json.JSONDecodeError:
                answer = None
            if isinstance(answer, dict):
                tool_calls.append(ToolCall(name=required.name, arguments=answer))
                text = ""

        used = message.usage
        usage = Usage(
            # Cached input is still input the provider read.
            input_tokens=used.input_tokens
            + (used.cache_creation_input_tokens or 0)
            + (used.cache_read_input_tokens or 0),
            output_tokens=used.output_tokens,
        )
        return Response(
            text=text, tool_calls=tuple(tool_calls), stop=stop, stop_detail=detail, usage=usage
        )
