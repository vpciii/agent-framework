"""Verdicts: the gate's durable, cited output (ADR 0005 — cite, never assert).

`Pass` names, per claimed criterion, the passing test; `Reject` names specific
findings with evidence. JSON round-trip so a verdict is actionable without the
validator's session context (spec R-7).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from ..errors import ValidationError
from .bundle import TaskRef


@dataclass(frozen=True)
class Citation:
    """One criterion's evidence: `SC-n` → the passing test that cites it."""

    criterion: str
    test: str  # full path::test_name (ADR 0003 — no shorthand)

    def __post_init__(self) -> None:
        if not self.criterion or not self.test:
            raise ValidationError(f"citation must name a criterion and a test: {self!r}")


@dataclass(frozen=True)
class Finding:
    """One specific defect: which check failed, what was found, the evidence."""

    check: str
    finding: str
    evidence: str


@dataclass(frozen=True)
class Pass:
    """Every claimed criterion cited to its passing test, with green CI."""

    task_id: str
    citations: tuple[Citation, ...]
    ci: str

    def __post_init__(self) -> None:
        if not self.citations:
            raise ValidationError("a PASS with no citations is not a PASS")

    @classmethod
    def from_evidence(
        cls, task: TaskRef, citations: tuple[Citation, ...], ci: str
    ) -> Pass:
        """The gate's constructor: rejects any claimed criterion left uncited (R-2)."""
        cited = {c.criterion for c in citations}
        uncited = [sc for sc in task.criteria if sc not in cited]
        if uncited:
            raise ValidationError(
                f"cannot construct PASS for {task.task_id}: uncited {', '.join(uncited)}"
            )
        return cls(task_id=task.task_id, citations=citations, ci=ci)


@dataclass(frozen=True)
class Reject:
    """At least one specific, evidenced finding — never a bare 'looks wrong'."""

    task_id: str
    findings: tuple[Finding, ...]

    def __post_init__(self) -> None:
        if not self.findings:
            raise ValidationError("a REJECT with no findings is not a verdict")


Verdict = Pass | Reject


def verdict_to_json(verdict: Verdict) -> str:
    """Serialize a verdict to its durable JSON form."""
    kind = "pass" if isinstance(verdict, Pass) else "reject"
    return json.dumps({"verdict": kind, **asdict(verdict)}, indent=2)


def verdict_from_json(text: str) -> Verdict:
    """Parse a verdict back from JSON; loud on any unknown or malformed shape."""
    data: dict[str, Any] = json.loads(text)
    kind = data.get("verdict")
    if kind == "pass":
        return Pass(
            task_id=data["task_id"],
            citations=tuple(Citation(**c) for c in data["citations"]),
            ci=data["ci"],
        )
    if kind == "reject":
        return Reject(
            task_id=data["task_id"],
            findings=tuple(Finding(**f) for f in data["findings"]),
        )
    raise ValidationError(f"unknown verdict kind: {kind!r}")
