"""The evidence bundle: everything the gate needs about one task's PR.

An immutable value assembled by the collector edge (or a test) — the
validator core never touches the network or the repo (plan: hermetic core,
thin edges).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


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
class Contract:
    """What the PR's claims are judged against, read from the artifacts.

    `spec_slug` is None when the claims could not be tied to a spec
    (`problem` says why) — the deterministic stage rejects that for free.
    The texts are the spec as it stood at the PR's base commit, or at its
    head when the PR itself introduces the spec (`read_from` says which).
    """

    spec_slug: str | None
    criterion_texts: dict[str, str] = field(default_factory=dict)  # SC-id → text
    task_block: str | None = None  # the task's verbatim block from tasks.md
    # SC-id → the `path::test_name` references the spec's Traceability table
    # names for it, read at the PR's head (the PR is what fills the table in).
    cited_tests: dict[str, tuple[str, ...]] = field(default_factory=dict)
    read_from: Literal["base", "head"] = "base"
    ref: str = ""  # the commit the spec was read at
    problem: str = ""


@dataclass(frozen=True)
class EvidenceBundle:
    """One task's PR evidence: diff, the tests citing its criteria, CI, red evidence,
    and the contract the claims are judged against."""

    task: TaskRef
    diff: str
    tests: dict[str, str]  # path → source
    ci: CIEvidence
    red_evidence: str | None = None  # a fix's failing-before run
    # None only for a hand-built bundle; the collector always supplies one.
    contract: Contract | None = None
