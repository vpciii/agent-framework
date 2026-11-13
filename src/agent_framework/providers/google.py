"""Google provider adapter.

Wraps the official `google-genai` SDK and normalizes its response into the
common `Response` (ADR 0001 — the only place the Google SDK is imported; kept
thin). The API key comes from the environment (`GEMINI_API_KEY`), never config.
"""

from __future__ import annotations

import os

from google import genai
from google.genai import errors as genai_errors
from google.genai.types import (
    FunctionCallingConfigMode,
    GenerateContentConfigDict,
    GenerateContentResponse,
    ThinkingLevel,
)

from ..errors import ProviderError
from .base import Request, Response, StopReason, ToolCall, Usage


class GoogleProvider:
    """A `Provider` backed by Google. Serves any Gemini model; `model` selects one."""

    def __init__(self, client: genai.Client | None = None) -> None:
        # Injectable for tests; otherwise built lazily from GEMINI_API_KEY.
        self._client = client

    def _client_or_default(self) -> genai.Client:
        if self._client is None:
            # Key from the environment, never config (ADR 0001 / secrets rule).
            try:
                self._client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
            except ValueError as e:
                # The SDK refuses to build a client it has no credentials
                # for. That is a request the provider cannot serve, not a
                # bug to show as a traceback.
                raise ProviderError(
                    f"no Google client (is GEMINI_API_KEY set?): {type(e).__name__}: {e}"
                ) from e
        return self._client

    async def invoke(self, request: Request, *, model: str) -> Response:
        client = self._client_or_default()
        config: GenerateContentConfigDict = {}
        if request.tools:
            config["tools"] = [
                {
                    "function_declarations": [
                        {
                            "name": t.name,
                            "description": t.description,
                            "parameters_json_schema": t.parameters,
                        }
                        for t in request.tools
                    ]
                }
            ]
        if request.require_tool is not None:
            # The provider enforces the required answer: it must call a
            # function, and only this one is allowed.
            config["tool_config"] = {
                "function_calling_config": {
                    "mode": FunctionCallingConfigMode.ANY,
                    "allowed_function_names": [request.require_tool],
                }
            }
        if request.max_output_tokens is not None:
            config["max_output_tokens"] = request.max_output_tokens
        if request.effort is not None:
            # The provider's control for how much to reason is its thinking
            # level: the most the model may think, not what it must.
            config["thinking_config"] = {
                "thinking_level": ThinkingLevel(request.effort.upper())
            }
        try:
            response = await client.aio.models.generate_content(
                model=model, contents=request.prompt, config=config or None
            )
        except genai_errors.APIError as e:
            raise ProviderError(f"{type(e).__name__}: {e}") from e
        return self._normalize(response)

    async def list_models(self) -> tuple[str, ...]:
        """Model IDs the API serves (`ModelCatalog`), without the `models/` prefix."""
        client = self._client_or_default()
        pager = await client.aio.models.list()
        return tuple([(m.name or "").removeprefix("models/") async for m in pager])

    async def probe_model(self, model: str) -> str | None:
        """The `model_version` Gemini reports for a 1-token request (`ModelProbe`)."""
        client = self._client_or_default()
        response = await client.aio.models.generate_content(
            model=model, contents="ok", config={"max_output_tokens": 1}
        )
        return response.model_version

    @staticmethod
    def _normalize(response: GenerateContentResponse) -> Response:
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        candidates = response.candidates or []
        content = candidates[0].content if candidates else None
        for part in content.parts or [] if content is not None else []:
            if part.text is not None:
                text_parts.append(part.text)
            elif part.function_call is not None:
                call = part.function_call
                tool_calls.append(
                    ToolCall(name=call.name or "", arguments=dict(call.args or {}))
                )

        finish = candidates[0].finish_reason if candidates else None
        detail = finish.name if finish is not None else ""
        if not candidates:
            # No candidate at all: the prompt itself was blocked.
            block = response.prompt_feedback.block_reason if response.prompt_feedback else None
            detail = block.name if block is not None else "NO_CANDIDATES"
            stop: StopReason = "refused" if block is not None else "other"
        else:
            stop = _STOP.get(detail, "other") if detail else "complete"

        meta = response.usage_metadata
        usage = (
            Usage(
                input_tokens=meta.prompt_token_count or 0,
                # Thinking is output the provider bills for, counted separately.
                output_tokens=(meta.candidates_token_count or 0) + (meta.thoughts_token_count or 0),
            )
            if meta is not None
            else None
        )
        return Response(
            text="".join(text_parts), tool_calls=tuple(tool_calls),
            stop=stop, stop_detail=detail, usage=usage,
        )


# The provider's finish reasons, in the interface's vocabulary. Anything not
# listed is "other".
_STOP: dict[str, StopReason] = {
    "STOP": "complete",
    "MAX_TOKENS": "truncated",
    "SAFETY": "refused",
    "RECITATION": "refused",
    "BLOCKLIST": "refused",
    "PROHIBITED_CONTENT": "refused",
    "SPII": "refused",
}
