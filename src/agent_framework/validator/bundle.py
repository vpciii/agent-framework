"""The evidence bundle: everything the gate needs about one task's PR.

An immutable value assembled by the collector edge (or a test) — the
validator core never touches the network or the repo (plan: hermetic core,
thin edges).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TaskRef:
    """The task under validation: its id, claimed criteria, and whether it is a fix."""

    task_id: str
    criteria: tuple[str, ...]
    is_fix: bool = False


@dataclass(frozen=True)
class CIEvidence:
    """The deterministic CI outcome for the PR (ADR 0003 already ran the tests)."""

    green: bool
    summary: str


@dataclass(frozen=True)
class EvidenceBundle:
    """One task's PR evidence: diff, the tests citing its criteria, CI, red evidence."""

    task: TaskRef
    diff: str
    tests: dict[str, str]  # path → source
    ci: CIEvidence
    red_evidence: str | None = None  # a fix's failing-before run
