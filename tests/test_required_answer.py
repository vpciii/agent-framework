"""The provider interface's required answer, stop reason and usage
(specs/judgment-reliability).

Both vendor SDKs are mocked at the *transport* layer: the real SDK builds
the request and parses the response; the adapter normalizes. No live calls.
Each test's docstring names the one criterion it verifies.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from anthropic import AsyncAnthropic
from google import genai
from google.genai import types

from agent_framework.dispatch import dispatch
from agent_framework.errors import RequestError
from agent_framework.providers.anthropic import AnthropicProvider
from agent_framework.providers.base import Request, Response, ToolCall, ToolDef, Usage
from agent_framework.providers.google import GoogleProvider
from agent_framework.providers.registry import ProviderRegistry
from agent_framework.roster import Roster

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}
_ANSWER = ToolDef("answer", "Give the answer.", _SCHEMA)
_OTHER = ToolDef("lookup", "Look something up.", {"type": "object", "properties": {}})


def _google(reply: dict[str, Any]) -> tuple[GoogleProvider, dict[str, Any]]:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=reply)

    client = genai.Client(
        api_key="test-key",
        http_options=types.HttpOptions(
            async_client_args={"transport": httpx.MockTransport(handler)}
        ),
    )
    return GoogleProvider(client=client), captured


def _anthropic(reply: dict[str, Any]) -> tuple[AnthropicProvider, dict[str, Any]]:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=reply)

    client = AsyncAnthropic(
        api_key="test-key",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    return AnthropicProvider(client=client), captured


def _google_reply(finish: str, parts: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "candidates": [
            {"content": {"role": "model", "parts": parts}, "finishReason": finish, "index": 0}
        ],
        "usageMetadata": {
            "promptTokenCount": 120, "candidatesTokenCount": 30, "thoughtsTokenCount": 12,
            "totalTokenCount": 162,
        },
        "modelVersion": "judge-model",
    }


def _anthropic_reply(stop_reason: str, content: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": "msg_test", "type": "message", "role": "assistant", "model": "judge-model",
        "content": content, "stop_reason": stop_reason, "stop_sequence": None,
        "usage": {"input_tokens": 200, "output_tokens": 55},
    }


async def test_sc1_google_enforces_the_required_answer_and_reports_stop_and_usage() -> None:
    """SC-1 here: must-call mode restricted to the one tool, the size limit
    sent, the stop reason and token counts reported."""
    provider, captured = _google(
        _google_reply("STOP", [{"functionCall": {"name": "answer", "args": {"ok": True}}}])
    )
    request = Request(
        prompt="judge", tools=(_ANSWER, _OTHER), require_tool="answer", max_output_tokens=900
    )

    response = await provider.invoke(request, model="judge-model")

    calling = captured["body"]["toolConfig"]["functionCallingConfig"]
    assert calling["mode"] == "ANY"
    assert calling["allowedFunctionNames"] == ["answer"]
    assert captured["body"]["generationConfig"]["maxOutputTokens"] == 900
    assert response.tool_calls == (ToolCall("answer", {"ok": True}),)
    assert (response.stop, response.stop_detail) == ("complete", "STOP")
    assert response.usage == Usage(input_tokens=120, output_tokens=42)  # candidates + thoughts


@pytest.mark.parametrize(
    ("finish", "stop"),
    [("MAX_TOKENS", "truncated"), ("SAFETY", "refused"), ("PROHIBITED_CONTENT", "refused"),
     ("MALFORMED_FUNCTION_CALL", "other")],
)
async def test_sc1_google_stop_reasons_are_normalized(finish: str, stop: str) -> None:
    """SC-1 here: a response the provider marks as cut off is truncated;
    a declined one is refused; the provider's own word is kept."""
    provider, _ = _google(_google_reply(finish, [{"text": "partial"}]))

    response = await provider.invoke(Request(prompt="judge"), model="judge-model")

    assert (response.stop, response.stop_detail) == (stop, finish)


async def test_sc1_google_without_the_new_fields_sends_neither() -> None:
    """SC-1 here: no required answer and no limit → no tool config, no size limit."""
    provider, captured = _google(_google_reply("STOP", [{"text": "hi"}]))

    await provider.invoke(Request(prompt="judge", tools=(_OTHER,)), model="judge-model")

    assert "toolConfig" not in captured["body"]
    assert "maxOutputTokens" not in captured["body"].get("generationConfig", {})


async def test_sc2_anthropic_enforces_the_required_answer_as_structured_output() -> None:
    """SC-2 here: the tool's schema is the required output format, no tool
    choice is forced, and the JSON answer comes back as a call to the tool."""
    provider, captured = _anthropic(
        _anthropic_reply("end_turn", [
            {"type": "thinking", "thinking": "", "signature": "sig"},
            {"type": "text", "text": '{"ok": true}'},
        ])
    )
    request = Request(prompt="judge", tools=(_ANSWER, _OTHER), require_tool="answer")

    response = await provider.invoke(request, model="judge-model")

    body = captured["body"]
    assert body["output_config"]["format"] == {"type": "json_schema", "schema": _SCHEMA}
    assert "tool_choice" not in body
    assert response.tool_calls == (ToolCall("answer", {"ok": True}),)
    assert response.text == ""  # the answer is the call, not prose
    assert (response.stop, response.stop_detail) == ("complete", "end_turn")
    assert response.usage == Usage(input_tokens=200, output_tokens=55)


@pytest.mark.parametrize(
    ("stop_reason", "content", "stop"),
    [
        ("max_tokens", [{"type": "text", "text": '{"ok": tr'}], "truncated"),
        ("refusal", [], "refused"),
    ],
)
async def test_sc2_anthropic_truncated_and_refused_carry_no_answer(
    stop_reason: str, content: list[dict[str, Any]], stop: str
) -> None:
    """SC-2 here: a stop at the output limit is truncated, a declined
    request is refused — and neither is passed off as a call to the tool."""
    provider, _ = _anthropic(_anthropic_reply(stop_reason, content))

    response = await provider.invoke(
        Request(prompt="judge", tools=(_ANSWER,), require_tool="answer"), model="judge-model"
    )

    assert (response.stop, response.stop_detail) == (stop, stop_reason)
    assert response.tool_calls == ()


async def test_sc2_anthropic_output_limit_is_the_default_or_the_callers() -> None:
    """SC-2 here: no limit → the adapter's documented default; a limit → that."""
    provider, captured = _anthropic(_anthropic_reply("end_turn", [{"type": "text", "text": "x"}]))

    await provider.invoke(Request(prompt="judge"), model="judge-model")
    assert captured["body"]["max_tokens"] == 16_000

    await provider.invoke(Request(prompt="judge", max_output_tokens=512), model="judge-model")
    assert captured["body"]["max_tokens"] == 512


async def test_sc2_anthropic_without_a_required_answer_offers_tools_as_before() -> None:
    """SC-2 here: with no required answer, tools are offered and no output
    format is set — the model-roster behavior, unchanged."""
    provider, captured = _anthropic(
        _anthropic_reply("tool_use", [
            {"type": "tool_use", "id": "t1", "name": "lookup", "input": {}},
        ])
    )

    response = await provider.invoke(Request(prompt="judge", tools=(_OTHER,)), model="m")

    assert [t["name"] for t in captured["body"]["tools"]] == ["lookup"]
    assert "output_config" not in captured["body"]
    assert response.tool_calls == (ToolCall("lookup", {}),)
    assert response.stop == "complete"


def test_sc3_a_required_answer_that_is_not_offered_is_unconstructible() -> None:
    """SC-3 here: naming a tool the request does not offer is an error when
    the request is built — before any provider can be called."""
    with pytest.raises(RequestError, match="nonesuch"):
        Request(prompt="judge", tools=(_ANSWER,), require_tool="nonesuch")
    with pytest.raises(RequestError, match="answer"):
        Request(prompt="judge", require_tool="answer")  # no tools at all
    with pytest.raises(RequestError, match="max_output_tokens"):
        Request(prompt="judge", max_output_tokens=0)


async def test_sc7_old_shaped_requests_and_responses_still_work() -> None:
    """SC-7 here: a request with only a prompt and tools, and a provider
    that returns only text and tool calls, behave as before; and the
    interface, dispatch, judgment and gate modules name no vendor or model."""

    class _OldFake:
        async def invoke(self, request: Request, *, model: str) -> Response:
            assert request.require_tool is None and request.max_output_tokens is None
            return Response(text="ok", tool_calls=(ToolCall("lookup", {}),))

    registry = ProviderRegistry()
    registry.register("fake", _OldFake())
    roster = Roster.from_dict({"roles": {"validator": {"provider": "fake", "model": "m"}}})

    response = await dispatch(
        roster, "validator", Request(prompt="p", tools=(_OTHER,)), registry=registry
    )

    assert (response.text, response.tool_calls) == ("ok", (ToolCall("lookup", {}),))
    assert (response.stop, response.stop_detail, response.usage) == ("complete", "", None)

    src = Path(__file__).resolve().parents[1] / "src" / "agent_framework"
    for module in ("providers/base.py", "dispatch.py", "validator/judgment.py",
                   "validator/gate.py"):
        text = (src / module).read_text(encoding="utf-8").lower()
        for vendor in ("anthropic", "claude", "google", "gemini"):
            assert vendor not in text, f"{module} names {vendor}"


@pytest.mark.parametrize("which", ["google", "anthropic"])
async def test_a_provider_failure_is_one_typed_error_whatever_the_vendor(which: str) -> None:
    """A rate limit or outage reaches the caller as `ProviderError`, with the
    vendor's own error chained — so nothing above the adapters has to know a
    vendor's exception types."""
    from agent_framework.errors import ProviderError

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"code": 429, "message": "quota exhausted",
                                                   "status": "RESOURCE_EXHAUSTED",
                                                   "type": "rate_limit_error"}})

    provider: GoogleProvider | AnthropicProvider
    if which == "google":
        provider = GoogleProvider(client=genai.Client(
            api_key="k",
            http_options=types.HttpOptions(
                async_client_args={"transport": httpx.MockTransport(handler)},
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        ))
    else:
        provider = AnthropicProvider(client=AsyncAnthropic(
            api_key="k", max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        ))

    with pytest.raises(ProviderError, match="429") as raised:
        await provider.invoke(Request(prompt="judge"), model="judge-model")

    assert raised.value.__cause__ is not None
