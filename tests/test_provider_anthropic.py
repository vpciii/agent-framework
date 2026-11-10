"""Anthropic adapter.

Verifies SC-3 (Anthropic half): the adapter round-trips a request to a
normalized Response. The Anthropic SDK is mocked at the *transport* layer with
a realistic Messages API response — the real SDK parses it, the adapter
normalizes its objects. No live calls.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
import pytest
from anthropic import AnthropicError, AsyncAnthropic

from agent_framework.errors import ProviderError
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


@pytest.fixture
def no_credentials(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Nothing in the environment, and no profile on disk, for the SDK to
    find a credential in."""
    for name in [n for n in os.environ if n.startswith("ANTHROPIC_")]:
        monkeypatch.delenv(name)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))


async def test_missing_credentials_are_a_provider_error(no_credentials: None) -> None:
    """Regression (found 2026-11-10): with no credentials anywhere the SDK
    raises a bare TypeError as it builds the request, which escaped `invoke`
    — a traceback from the gate's CLI instead of "could not judge". The
    adapter reports it as the typed error, the SDK's own chained. No call
    is made: the SDK stops before it sends anything."""
    with pytest.raises(ProviderError, match="api_key") as raised:
        await AnthropicProvider().invoke(Request(prompt="x"), model="any")

    assert isinstance(raised.value.__cause__, TypeError)


async def test_credentials_that_cannot_be_loaded_are_a_provider_error(
    no_credentials: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression (found 2026-11-10): pointed at a profile that does not
    exist, the SDK refuses to build a client, and its own error escaped
    `invoke` the same way. No call is made: there is no client to make one."""
    monkeypatch.setenv("ANTHROPIC_PROFILE", "no-such-profile")

    with pytest.raises(ProviderError, match="no Anthropic client") as raised:
        await AnthropicProvider().invoke(Request(prompt="x"), model="any")

    assert isinstance(raised.value.__cause__, AnthropicError)
