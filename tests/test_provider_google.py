"""Google adapter.

Verifies SC-3 (Google half): the adapter round-trips a request to a normalized
Response. The google-genai SDK is mocked at the *transport* layer with a
realistic generateContent response — the real SDK parses it, the adapter
normalizes its objects. No live calls.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from google import genai
from google.genai import types

from agent_framework.providers.base import Request, Response, ToolCall, ToolDef
from agent_framework.providers.google import GoogleProvider

_API_RESPONSE: dict[str, Any] = {
    "candidates": [
        {
            "content": {
                "role": "model",
                "parts": [
                    {"text": "hello from gemini"},
                    {"functionCall": {"name": "noop", "args": {"x": 1}}},
                ],
            },
            "finishReason": "STOP",
            "index": 0,
        }
    ],
    "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 3, "totalTokenCount": 8},
    "modelVersion": "gemini-3-pro",
}


async def test_sc3_google_adapter_round_trips_to_normalized_response() -> None:
    """SC-3: request → normalized Response; the outgoing request is built correctly too."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith(":generateContent")
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_API_RESPONSE)

    client = genai.Client(
        api_key="test-key",
        http_options=types.HttpOptions(
            async_client_args={"transport": httpx.MockTransport(handler)}
        ),
    )
    provider = GoogleProvider(client=client)

    request = Request(prompt="hi", tools=(ToolDef("noop", "does nothing", {}),))
    response = await provider.invoke(request, model="gemini-3-pro")

    # Response normalized from the SDK's parsed parts.
    assert isinstance(response, Response)
    assert response.text == "hello from gemini"
    assert response.tool_calls == (ToolCall("noop", {"x": 1}),)

    # Request built correctly (model in the path, prompt + tool passed through).
    assert captured["path"] == "/v1beta/models/gemini-3-pro:generateContent"
    assert captured["body"]["contents"] == [{"parts": [{"text": "hi"}], "role": "user"}]
    assert captured["body"]["tools"][0]["functionDeclarations"][0]["name"] == "noop"
