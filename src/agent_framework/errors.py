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


class ValidationError(AgentFrameworkError):
    """The validator was given inconsistent inputs or built an invalid verdict."""


class JudgmentFormatError(ValidationError):
    """The judgment model did not answer with the required verdict tool call."""


class WorkerError(AgentFrameworkError):
    """Base class for worker-orchestration errors."""


class UnknownTaskError(WorkerError):
    """The requested spec slug or task id does not exist in the artifacts."""


class SessionResultError(WorkerError):
    """The session did not honor the `.worker-result.json` contract."""


class SessionTimeoutError(WorkerError):
    """The session exceeded its time budget and was killed."""


class WorktreeError(WorkerError):
    """The worktree or branch could not be created (collision or git failure)."""
