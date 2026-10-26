"""Provider adapters as model catalogs (and Google's routing probe).

Verifies spec success criteria (specs/roster-currency-check):
- SC-6: the production adapters implement the catalog protocol the check
  resolves through the registry — mocked at the transport layer, so the
  real SDKs parse realistic listing responses. No live calls.
- SC-8: Google's probe returns the `modelVersion` Gemini reports.
"""

from __future__ import annotations

from typing import Any

import httpx
from anthropic import AsyncAnthropic
from google import genai
from google.genai import types

from agent_framework.providers.anthropic import AnthropicProvider
from agent_framework.providers.base import ModelCatalog, ModelProbe
from agent_framework.providers.google import GoogleProvider


def _anthropic(handler: Any) -> AnthropicProvider:
    return AnthropicProvider(client=AsyncAnthropic(
        api_key="test-key",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    ))


def _google(handler: Any) -> GoogleProvider:
    return GoogleProvider(client=genai.Client(
        api_key="test-key",
        http_options=types.HttpOptions(
            async_client_args={"transport": httpx.MockTransport(handler)}
        ),
    ))


async def test_sc6_anthropic_adapter_lists_model_ids() -> None:
    """SC-6: AnthropicProvider is a ModelCatalog (no probe) over GET /v1/models."""
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        return httpx.Response(200, json={
            "data": [
                {"type": "model", "id": i, "display_name": i,
                 "created_at": "2026-09-01T00:00:00Z"}
                for i in ("claude-sonnet-5-5", "claude-fable-5-1")
            ],
            "has_more": False, "first_id": "claude-sonnet-5-5", "last_id": "claude-fable-5-1",
        })

    provider = _anthropic(handler)
    assert isinstance(provider, ModelCatalog) and not isinstance(provider, ModelProbe)
    assert await provider.list_models() == ("claude-sonnet-5-5", "claude-fable-5-1")


async def test_sc6_google_adapter_lists_model_ids_without_prefix() -> None:
    """SC-6: GoogleProvider lists served models, `models/` prefix stripped."""
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/models")
        return httpx.Response(200, json={"models": [
            {"name": "models/gemini-3.8-flash"}, {"name": "models/gemini-3.6-flash"},
        ]})

    provider = _google(handler)
    assert isinstance(provider, ModelCatalog)
    assert await provider.list_models() == ("gemini-3.8-flash", "gemini-3.6-flash")


async def test_sc8_google_probe_reports_the_serving_model() -> None:
    """SC-8: a 1-token request; the reported modelVersion comes back."""
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/models/gemini-3.5-flash:generateContent")
        return httpx.Response(200, json={
            "candidates": [{"content": {"role": "model", "parts": [{"text": "o"}]},
                            "finishReason": "MAX_TOKENS", "index": 0}],
            "modelVersion": "gemini-3.6-flash",
        })

    assert await _google(handler).probe_model("gemini-3.5-flash") == "gemini-3.6-flash"
