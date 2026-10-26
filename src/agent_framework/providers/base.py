"""The provider interface and its normalized request/response shapes.

One shape across every vendor (ADR 0001): a `Provider` takes a `Request`
(prompt + tool definitions) and returns a `Response` (assistant text + any
tool calls). Adapters are the only place a vendor SDK is imported; they
normalize into these types. Kept deliberately thin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ToolDef:
    """A tool offered to the model: name + description + JSON-schema params."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class Request:
    """A model invocation: a prompt and the tools the model may call."""

    prompt: str
    tools: tuple[ToolDef, ...] = ()


@dataclass(frozen=True)
class ToolCall:
    """A tool the model chose to call, with its arguments."""

    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Response:
    """A normalized model response: assistant text plus any tool calls."""

    text: str
    tool_calls: tuple[ToolCall, ...] = ()


@runtime_checkable
class Provider(Protocol):
    """A vendor adapter. Serves any model of its provider; `model` selects one."""

    async def invoke(self, request: Request, *, model: str) -> Response: ...


@runtime_checkable
class ModelCatalog(Protocol):
    """An adapter that can list the model IDs its provider currently serves.

    Separate from `Provider` so existing adapters and fakes stay valid; the
    roster currency check treats a provider without it as unchecked.
    """

    async def list_models(self) -> tuple[str, ...]: ...


@runtime_checkable
class ModelProbe(Protocol):
    """An adapter that can report which model actually served a request.

    Returns the provider-reported serving model for a minimal request, or
    None when the provider does not say.
    """

    async def probe_model(self, model: str) -> str | None: ...
