"""Role-based dispatch.

Verifies spec success criteria:
- SC-2: dispatch invokes the bound provider and returns a normalized Response.
- SC-4: an unknown role, or a provider with no adapter, fails loudly and
  invokes nothing.
"""

from __future__ import annotations

import pytest

from agent_framework.dispatch import dispatch
from agent_framework.errors import UnknownProviderError, UnknownRoleError
from agent_framework.providers.base import Request, Response, ToolDef
from agent_framework.providers.registry import ProviderRegistry
from agent_framework.roster import Roster


class _FakeProvider:
    """Records its calls and returns a deterministic Response."""

    def __init__(self) -> None:
        self.calls: list[tuple[Request, str]] = []

    async def invoke(self, request: Request, *, model: str) -> Response:
        self.calls.append((request, model))
        return Response(text=f"ok:{model}")


def _roster() -> Roster:
    return Roster.from_dict(
        {
            "roles": {
                "chief": {"provider": "anthropic", "model": "claude-fable-5"},
                "worker": {"provider": "mystery", "model": "m"},
            }
        }
    )


async def test_sc2_dispatch_invokes_bound_provider_and_returns_response() -> None:
    """SC-2: resolve the role, send prompt+tools to the bound provider, return a Response."""
    reg = ProviderRegistry()
    fake = _FakeProvider()
    reg.register("anthropic", fake)

    request = Request(prompt="hello", tools=(ToolDef("noop", "does nothing", {}),))
    response = await dispatch(_roster(), "chief", request, registry=reg)

    assert isinstance(response, Response)
    assert response.text == "ok:claude-fable-5"
    assert fake.calls == [(request, "claude-fable-5")]


async def test_sc4_unknown_role_fails_loudly_and_does_not_invoke() -> None:
    """SC-4: an unbound role raises UnknownRoleError; no provider is invoked."""
    reg = ProviderRegistry()
    fake = _FakeProvider()
    reg.register("anthropic", fake)

    with pytest.raises(UnknownRoleError):
        await dispatch(_roster(), "nobody", Request(prompt="x"), registry=reg)
    assert fake.calls == []


async def test_sc4_provider_without_adapter_fails_loudly_and_does_not_invoke() -> None:
    """SC-4: a role bound to a provider with no adapter raises UnknownProviderError."""
    reg = ProviderRegistry()  # empty — no "mystery" adapter
    with pytest.raises(UnknownProviderError):
        await dispatch(_roster(), "worker", Request(prompt="x"), registry=reg)
