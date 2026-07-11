"""Provider registry: maps a provider name to its adapter.

An instance-based registry (so tests stay isolated), plus module-level
`register_provider` / `get_provider` over a shared default registry for the
common case. Looking up an unregistered provider fails loudly.
"""

from __future__ import annotations

from ..errors import UnknownProviderError
from .base import Provider


class ProviderRegistry:
    """A name → `Provider` mapping."""

    def __init__(self) -> None:
        self._providers: dict[str, Provider] = {}

    def register(self, name: str, provider: Provider) -> None:
        self._providers[name] = provider

    def get(self, name: str) -> Provider:
        try:
            return self._providers[name]
        except KeyError:
            known = ", ".join(sorted(self._providers)) or "(none)"
            raise UnknownProviderError(
                f"no adapter registered for provider {name!r}; registered: {known}"
            ) from None


_default = ProviderRegistry()


def default_registry() -> ProviderRegistry:
    """The shared registry used when a caller does not pass its own."""
    return _default


def register_provider(name: str, provider: Provider) -> None:
    """Register `provider` under `name` in the shared default registry."""
    _default.register(name, provider)


def get_provider(name: str) -> Provider:
    """Look up a provider in the shared default registry (loud on miss)."""
    return _default.get(name)
