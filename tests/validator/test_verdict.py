"""Verdict types and their durable JSON form.

Verifies SC-6: a verdict written as the structured artifact and re-parsed is
equal to the in-memory verdict — PASS and REJECT. Plus the construction
guards T-3's gate relies on (an uncited PASS is rejected at construction).
"""

from __future__ import annotations

import pytest

from agent_framework.errors import ValidationError
from agent_framework.validator.bundle import TaskRef
from agent_framework.validator.verdict import (
    Citation,
    Finding,
    Pass,
    Reject,
    verdict_from_json,
    verdict_to_json,
)


def test_sc6_pass_round_trips_through_json() -> None:
    """SC-6 (PASS half): to JSON and back → equal value."""
    verdict = Pass(
        task_id="T-9",
        citations=(
            Citation("SC-1", "tests/test_x.py::test_a"),
            Citation("SC-2", "tests/test_x.py::test_b"),
        ),
        ci="ci run 123: green",
    )
    assert verdict_from_json(verdict_to_json(verdict)) == verdict


def test_sc6_reject_round_trips_through_json() -> None:
    """SC-6 (REJECT half): to JSON and back → equal value."""
    verdict = Reject(
        task_id="T-9",
        findings=(
            Finding(
                check="test-honesty",
                finding="test_b asserts nothing about the new behavior",
                evidence="tests/test_x.py::test_b body has no assert on result",
            ),
        ),
    )
    assert verdict_from_json(verdict_to_json(verdict)) == verdict


def test_unknown_verdict_kind_fails_loudly() -> None:
    with pytest.raises(ValidationError, match="unknown verdict kind"):
        verdict_from_json('{"verdict": "maybe", "task_id": "T-9"}')


def test_pass_from_evidence_rejects_uncited_criterion() -> None:
    """The gate's constructor path: a claimed criterion with no citation → error."""
    task = TaskRef(task_id="T-9", criteria=("SC-1", "SC-2"))
    with pytest.raises(ValidationError, match="uncited SC-2"):
        Pass.from_evidence(
            task, (Citation("SC-1", "tests/test_x.py::test_a"),), ci="green"
        )


def test_pass_with_no_citations_is_unconstructible() -> None:
    with pytest.raises(ValidationError, match="no citations"):
        Pass(task_id="T-9", citations=(), ci="green")


def test_reject_with_no_findings_is_unconstructible() -> None:
    with pytest.raises(ValidationError, match="no findings"):
        Reject(task_id="T-9", findings=())
