"""Google provider adapter.

Wraps the official `google-genai` SDK and normalizes its response into the
common `Response` (ADR 0001 — the only place the Google SDK is imported; kept
thin). The API key comes from the environment (`GEMINI_API_KEY`), never config.
"""

from __future__ import annotations

import os

from google import genai
from google.genai.types import GenerateContentConfigDict, GenerateContentResponse

from .base import Request, Response, ToolCall


class GoogleProvider:
    """A `Provider` backed by Google. Serves any Gemini model; `model` selects one."""

    def __init__(self, client: genai.Client | None = None) -> None:
        # Injectable for tests; otherwise built lazily from GEMINI_API_KEY.
        self._client = client

    def _client_or_default(self) -> genai.Client:
        if self._client is None:
            # Key from the environment, never config (ADR 0001 / secrets rule).
            self._client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        return self._client

    async def invoke(self, request: Request, *, model: str) -> Response:
        client = self._client_or_default()
        config: GenerateContentConfigDict | None = None
        if request.tools:
            config = {
                "tools": [
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
            }
        response = await client.aio.models.generate_content(
            model=model, contents=request.prompt, config=config
        )
        return self._normalize(response)

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
        return Response(text="".join(text_parts), tool_calls=tuple(tool_calls))
