"""Core value types shared across the framework."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelRef:
    """A resolved binding of a role to a concrete model.

    `provider` names a registered provider adapter (e.g. "anthropic",
    "google"); `model` is that provider's model id (e.g. "claude-fable-5").
    """

    provider: str
    model: str
