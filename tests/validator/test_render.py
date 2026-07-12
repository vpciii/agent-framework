"""Rendering a verdict to markdown.

Verifies SC-1: a rendered PASS contains the task id, every citation's
criterion and `path::test`, and the CI evidence; a rendered REJECT contains
the task id and every finding's check, finding, and evidence.
"""

from __future__ import annotations

from agent_framework.validator.render import render_verdict
from agent_framework.validator.verdict import Citation, Finding, Pass, Reject


def test_sc1_pass_renders_task_id_citations_and_ci() -> None:
    """SC-1 (PASS half): task id, every citation, and the CI evidence appear."""
    verdict = Pass(
        task_id="T-9",
        citations=(
            Citation("SC-1", "tests/test_x.py::test_a"),
            Citation("SC-2", "tests/test_x.py::test_b"),
        ),
        ci="ci run 123: green",
    )

    rendered = render_verdict(verdict)

    assert "PASS" in rendered
    assert "T-9" in rendered
    assert "SC-1" in rendered
    assert "tests/test_x.py::test_a" in rendered
    assert "SC-2" in rendered
    assert "tests/test_x.py::test_b" in rendered
    assert "ci run 123: green" in rendered


def test_sc1_reject_renders_task_id_and_every_finding_field() -> None:
    """SC-1 (REJECT half): task id and each finding's check/finding/evidence appear."""
    verdict = Reject(
        task_id="T-9",
        findings=(
            Finding(
                check="test-honesty",
                finding="test_b asserts nothing about the new behavior",
                evidence="tests/test_x.py::test_b body has no assert on result",
            ),
            Finding(
                check="style",
                finding="mypy --strict fails",
                evidence="render.py:12: error: Missing return statement",
            ),
        ),
    )

    rendered = render_verdict(verdict)

    assert "REJECT" in rendered
    assert "T-9" in rendered
    for finding in verdict.findings:
        assert finding.check in rendered
        assert finding.finding in rendered
        assert finding.evidence in rendered
