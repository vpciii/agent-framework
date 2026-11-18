"""The repository's own worker eval case set (specs/worker-eval).

No session is run: the committed cases are loaded from
`evals/worker/cases/` as code.
"""

from __future__ import annotations

from pathlib import Path

from agent_framework.evals.worker.case import load_case_set

REPO = Path(__file__).resolve().parents[3]


def test_sc11_the_committed_set_holds_six_cases_among_them_the_four_named() -> None:
    """SC-11: at least 6 cases, among them #31, #38, #73 and #88, each
    from this repository's own merged task pull requests."""
    cases = load_case_set(REPO / "evals/worker/cases").cases

    assert len(cases) >= 6
    assert {31, 38, 73, 88} <= {c.reference.pr for c in cases}
    assert {c.id for c in cases} == {f"pr-{c.reference.pr}" for c in cases}
    assert all(c.reference.repo == "vpciii/agent-framework" for c in cases)
