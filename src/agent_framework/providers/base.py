"""The provider interface and its normalized request/response shapes.

One shape across every vendor (ADR 0001): a `Provider` takes a `Request`
(prompt + tool definitions) and returns a `Response` (assistant text + any
tool calls). Adapters are the only place a vendor SDK is imported; they
normalize into these types. Kept deliberately thin.

The interface carries *intent*, never a provider's option name: a request
may say "this tool is the answer" (`require_tool`), and each adapter asks
its provider to enforce that in whatever way that provider can. A response
says why it stopped in one vocabulary, and what it cost in tokens
(specs/judgment-reliability).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable

from ..errors import RequestError
from ..models import EFFORTS, Effort


@dataclass(frozen=True)
class ToolDef:
    """A tool offered to the model: name + description + JSON-schema params."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class Request:
    """A model invocation: a prompt and the tools the model may call.

    `require_tool` names one of `tools` as the required answer: the provider
    is asked to enforce that the response is a call to it. `max_output_tokens`
    bounds the response; None means the adapter's own documented default.
    `effort` is how much reasoning the model is asked to spend, as intent:
    each adapter asks its provider in that provider's own way, and None
    means the provider's default. Dispatch sets it from the role's roster
    binding; a caller does not.
    """

    prompt: str
    tools: tuple[ToolDef, ...] = ()
    require_tool: str | None = None
    max_output_tokens: int | None = None
    effort: Effort | None = None

    def __post_init__(self) -> None:
        if self.effort is not None and self.effort not in EFFORTS:
            raise RequestError(
                f"effort must be one of {', '.join(EFFORTS)}, got {self.effort!r}"
            )
        if self.require_tool is not None and self.require_tool not in {
            t.name for t in self.tools
        }:
            offered = ", ".join(t.name for t in self.tools) or "(none)"
            raise RequestError(
                f"require_tool {self.require_tool!r} is not among the request's tools: {offered}"
            )
        if self.max_output_tokens is not None and self.max_output_tokens <= 0:
            raise RequestError(
                f"max_output_tokens must be positive, got {self.max_output_tokens}"
            )

    def required(self) -> ToolDef | None:
        """The tool that is the required answer, if one is named."""
        return next((t for t in self.tools if t.name == self.require_tool), None)


@dataclass(frozen=True)
class ToolCall:
    """A tool the model chose to call, with its arguments."""

    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Usage:
    """The tokens the provider counted for one response."""

    input_tokens: int
    output_tokens: int


# Why generation stopped, in one vocabulary across providers:
#   complete  — the model finished its answer
#   truncated — the output limit was reached
#   refused   — the provider declined to answer
#   other     — anything else the provider reports
StopReason = Literal["complete", "truncated", "refused", "other"]


@dataclass(frozen=True)
class Response:
    """A normalized model response: assistant text plus any tool calls.

    `stop` is the normalized reason generation ended and `stop_detail` the
    provider's own word for it; `usage` is None when the provider reports
    none. All three default, so a provider that says nothing about them is
    read as a complete answer of unknown cost.
    """

    text: str
    tool_calls: tuple[ToolCall, ...] = ()
    stop: StopReason = "complete"
    stop_detail: str = ""
    usage: Usage | None = None


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
