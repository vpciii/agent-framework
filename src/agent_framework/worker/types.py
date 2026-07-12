"""The worker's data model: the task in, the outcome out.

Immutable values; the orchestrator's state machine passes these between
seams (plan: pure core, injectable edges).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class TaskSpec:
    """One dispatchable task: its identity, claimed criteria, and source text."""

    spec_slug: str
    task_id: str
    criteria: tuple[str, ...]
    section: str  # the task's verbatim block from tasks.md
    criterion_texts: dict[str, str]  # SC-id → criterion text from spec.md
    requirements: str  # the spec's Requirements section, verbatim


@dataclass(frozen=True)
class SessionResult:
    """What the session reports via `.worker-result.json` — never inferred."""

    status: Literal["completed", "escalated"]
    detail: str
    spec_location: str | None = None


@dataclass(frozen=True)
class PrOpened:
    """Success: the branch is pushed and the PR (with its declaration) is open."""

    url: str
    branch: str
    task_id: str


@dataclass(frozen=True)
class Escalated:
    """The worker challenged the contract: no PR, a durable escalation artifact."""

    artifact_path: str
    detail: str


@dataclass(frozen=True)
class TimedOut:
    """The session exceeded its budget: no PR, worktree preserved for inspection."""

    worktree_path: str


WorkerOutcome = PrOpened | Escalated | TimedOut
