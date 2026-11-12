"""A role's effort is set in the roster (specs/role-effort).

Each test's docstring names the one criterion it verifies. Both SDKs are
mocked at the transport layer; no live calls and no provider key.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest
from anthropic import AsyncAnthropic
from google import genai
from google.genai import types

from agent_framework.dispatch import dispatch
from agent_framework.errors import RosterError
from agent_framework.models import Effort
from agent_framework.providers.anthropic import AnthropicProvider
from agent_framework.providers.base import Request, Response, ToolDef
from agent_framework.providers.google import GoogleProvider
from agent_framework.providers.registry import ProviderRegistry
from agent_framework.roster import Roster

ANSWER = ToolDef(
    "return_verdict", "the answer",
    {"type": "object", "properties": {"ok": {"type": "boolean"}},
     "required": ["ok"], "additionalProperties": False},
)


def _roster(**validator: str) -> Roster:
    binding = {"provider": "fake", "model": "judge-9"} | validator
    return Roster.from_dict({"roles": {"validator": binding}})


# ---- SC-1: the roster ------------------------------------------------------


@pytest.mark.parametrize("effort", ["low", "medium", "high"])
def test_sc1_a_binding_may_carry_an_effort(effort: str) -> None:
    """SC-1: a binding with one of the three efforts resolves to it."""
    ref = _roster(effort=effort).resolve("validator")

    assert (ref.provider, ref.model) == ("fake", "judge-9")
    assert ref.effort == effort


def test_sc1_a_binding_without_an_effort_has_none() -> None:
    """SC-1: a binding without it is what it is today."""
    assert _roster().resolve("validator").effort is None


@pytest.mark.parametrize("effort", ["maximum", "", "HIGH", 3])
def test_sc1_any_other_effort_is_a_roster_error_naming_the_role(effort: Any) -> None:
    """SC-1: a value outside the three fails to load, naming the role and
    the allowed values."""
    with pytest.raises(RosterError) as refused:
        Roster.from_dict(
            {"roles": {"validator": {"provider": "fake", "model": "judge-9", "effort": effort}}}
        )

    message = str(refused.value)
    assert "validator" in message
    assert all(allowed in message for allowed in ("low", "medium", "high"))


# ---- SC-2: dispatch carries it ---------------------------------------------


class _Fake:
    def __init__(self) -> None:
        self.requests: list[Request] = []

    async def invoke(self, request: Request, *, model: str) -> Response:
        self.requests.append(request)
        return Response(text="ok")


async def test_sc2_dispatch_hands_the_roles_effort_to_the_adapter() -> None:
    """SC-2: through a role bound with an effort, the adapter receives the
    request with that effort and otherwise equal to the one given; through
    a role without one, it receives the very request it was given."""
    given = Request(prompt="judge this", tools=(ANSWER,), require_tool="return_verdict")
    fake, registry = _Fake(), ProviderRegistry()
    registry.register("fake", fake)

    await dispatch(_roster(effort="high"), "validator", given, registry=registry)
    await dispatch(_roster(), "validator", given, registry=registry)

    with_effort, without = fake.requests
    assert with_effort.effort == "high"
    assert (with_effort.prompt, with_effort.tools, with_effort.require_tool) == (
        given.prompt, given.tools, given.require_tool,
    )
    assert without is given


# ---- SC-3: the Google adapter ----------------------------------------------

_GEMINI_RESPONSE: dict[str, Any] = {
    "candidates": [{"content": {"role": "model", "parts": [{"text": "ok"}]},
                    "finishReason": "STOP", "index": 0}],
    "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 3, "totalTokenCount": 8},
}


async def _google_body(request: Request) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def handler(sent: httpx.Request) -> httpx.Response:
        captured.update(json.loads(sent.content))
        return httpx.Response(200, json=_GEMINI_RESPONSE)

    client = genai.Client(
        api_key="test-key",
        http_options=types.HttpOptions(
            async_client_args={"transport": httpx.MockTransport(handler)}
        ),
    )
    await GoogleProvider(client=client).invoke(request, model="gemini-test")
    return captured


async def test_sc3_the_google_adapter_asks_for_the_effort_as_the_thinking_level() -> None:
    """SC-3: effort `high` reaches the SDK call as the thinking level `high`;
    with no effort the call carries no thinking option."""
    asked = await _google_body(_with_effort(Request(prompt="hi"), "high"))
    plain = await _google_body(Request(prompt="hi"))

    # The SDK writes this one option's name in snake case on the wire.
    thinking = asked["generationConfig"]["thinkingConfig"]
    level = thinking.get("thinkingLevel", thinking.get("thinking_level"))
    assert str(level).lower() == "high" and len(thinking) == 1
    assert "thinkingConfig" not in json.dumps(plain)


# ---- SC-4: the Anthropic adapter -------------------------------------------

_CLAUDE_RESPONSE: dict[str, Any] = {
    "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-test",
    "content": [{"type": "text", "text": '{"ok": true}'}],
    "stop_reason": "end_turn", "stop_sequence": None,
    "usage": {"input_tokens": 5, "output_tokens": 3},
}


async def _anthropic_body(request: Request) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def handler(sent: httpx.Request) -> httpx.Response:
        captured.update(json.loads(sent.content))
        return httpx.Response(200, json=_CLAUDE_RESPONSE)

    client = AsyncAnthropic(
        api_key="test-key",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    await AnthropicProvider(client=client).invoke(request, model="claude-test")
    return captured


async def test_sc4_the_anthropic_adapter_asks_for_the_effort_as_the_output_effort() -> None:
    """SC-4: effort `high` reaches the call as the output effort `high` —
    together with the answer format when the request names a required
    answer; with no effort the call carries none."""
    plain = Request(prompt="hi")
    required = Request(prompt="hi", tools=(ANSWER,), require_tool="return_verdict")

    asked = await _anthropic_body(_with_effort(plain, "high"))
    both = await _anthropic_body(_with_effort(required, "high"))
    neither = await _anthropic_body(plain)
    format_only = await _anthropic_body(required)

    assert asked["output_config"] == {"effort": "high"}
    assert both["output_config"]["effort"] == "high"
    assert both["output_config"]["format"] == format_only["output_config"]["format"]
    assert "output_config" not in neither
    assert "effort" not in format_only["output_config"]


def _with_effort(request: Request, effort: Effort) -> Request:
    return replace(request, effort=effort)


# ---- SC-5: intent only outside the adapters --------------------------------


def test_sc5_no_providers_option_name_outside_the_adapters() -> None:
    """SC-5: the provider interface, dispatch, the judgment and the gate
    carry the effort as intent; no provider's name for the option is in them."""
    src = Path(__file__).resolve().parents[1] / "src" / "agent_framework"
    for module in ("providers/base.py", "dispatch.py", "validator/judgment.py",
                   "validator/gate.py"):
        text = (src / module).read_text(encoding="utf-8").lower()
        for option in ("thinking_level", "thinkinglevel", "thinking_config", "output_config"):
            assert option not in text, f"{module} names {option}"
    # And the intent is there to be carried.
    assert "effort" in (src / "providers" / "base.py").read_text(encoding="utf-8")
    assert "effort" in (src / "dispatch.py").read_text(encoding="utf-8")
