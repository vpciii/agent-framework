"""Typed errors. The framework fails loudly — never a silent default or fallback."""

from __future__ import annotations


class AgentFrameworkError(Exception):
    """Base class for all framework errors."""


class RosterError(AgentFrameworkError):
    """The roster configuration is invalid (bad shape, or a secret in config)."""


class UnknownRoleError(AgentFrameworkError):
    """A role was requested that has no binding in the roster."""


class UnknownProviderError(AgentFrameworkError):
    """A role's provider has no registered adapter."""
