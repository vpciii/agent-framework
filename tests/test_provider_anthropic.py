"""Anthropic adapter.

Verifies SC-3 (Anthropic half): the adapter round-trips a request to a
normalized Response. The Anthropic SDK is mocked at the *transport* layer with
a realistic Messages API response — the real SDK parses it, the adapter
normalizes its objects. No live calls.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from anthropic import AsyncAnthropic

from agent_framework.providers.anthropic import AnthropicProvider
from agent_framework.providers.base import Request, Response, ToolCall, ToolDef

_API_RESPONSE: dict[str, Any] = {
    "id": "msg_test",
    "type": "message",
    "role": "assistant",
    "model": "claude-fable-5",
    "content": [
        {"type": "text", "text": "hello from claude"},
        {"type": "tool_use", "id": "toolu_1", "name": "noop", "input": {"x": 1}},
    ],
    "stop_reason": "tool_use",
    "stop_sequence": None,
    "usage": {"input_tokens": 5, "output_tokens": 3},
}


async def test_sc3_anthropic_adapter_round_trips_to_normalized_response() -> None:
    """SC-3: request → normalized Response; the outgoing request is built correctly too."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/messages"
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_API_RESPONSE)

    client = AsyncAnthropic(
        api_key="test-key",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    provider = AnthropicProvider(client=client)

    request = Request(prompt="hi", tools=(ToolDef("noop", "does nothing", {}),))
    response = await provider.invoke(request, model="claude-fable-5")

    # Response normalized from the SDK's parsed blocks.
    assert isinstance(response, Response)
    assert response.text == "hello from claude"
    assert response.tool_calls == (ToolCall("noop", {"x": 1}),)

    # Request built correctly (model + tool passed through).
    assert captured["body"]["model"] == "claude-fable-5"
    assert captured["body"]["messages"] == [{"role": "user", "content": "hi"}]
    assert captured["body"]["tools"][0]["name"] == "noop"
    assert captured["body"]["tools"][0]["input_schema"] == {}
