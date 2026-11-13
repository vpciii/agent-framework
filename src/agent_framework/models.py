"""Core value types shared across the framework."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, get_args

# How much reasoning a role's model is asked to spend on a request. Intent,
# in one vocabulary across providers: each adapter translates it to its
# provider's own control, and None means the provider's default
# (specs/role-effort).
Effort = Literal["low", "medium", "high"]
EFFORTS: tuple[Effort, ...] = get_args(Effort)


@dataclass(frozen=True)
class ModelRef:
    """A resolved binding of a role to a concrete model.

    `provider` names a registered provider adapter (e.g. "anthropic",
    "google"); `model` is that provider's model id (see the roster in `agent-framework.toml`).
    `effort` is how much reasoning the role asks of it, when the roster says.
    """

    provider: str
    model: str
    effort: Effort | None = None
