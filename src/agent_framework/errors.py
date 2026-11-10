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


class NoVerdictError(JudgmentFormatError):
    """The judgment could not be made: nothing was shown to be wrong with the
    pull request — the model's answer was cut off, declined or absent, or it
    reported a defect without one finding whose quoted evidence is in the
    data it was sent.

    `reason` is one of "truncated", "refused", "no-answer"
    (specs/judgment-reliability) or "unsupported-finding"
    (specs/finding-evidence). Never a verdict, and never a REJECT.
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class ProviderError(AgentFrameworkError):
    """A provider could not serve a request (rate limit, outage, rejected
    call). Raised by the adapters with the vendor's own error chained, so
    nothing above them needs to know a vendor's exception types."""


class RequestError(AgentFrameworkError):
    """A provider request is inconsistent (e.g. it requires a tool it does not offer)."""


class ProjectConfigError(AgentFrameworkError):
    """agent-framework.toml's [project] table is malformed."""


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


class EvalCaseError(AgentFrameworkError):
    """An eval case file is malformed, or its seeded edit does not apply
    exactly once. The message names the file (specs/validator-eval-set)."""
