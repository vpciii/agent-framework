"""The repository's own eval set (specs/validator-eval-set).

Each test's docstring names the one criterion it verifies. No model is
called: the cases are read from `evals/validator/cases/` and put through
the gate's deterministic stage, as code.
"""

from __future__ import annotations

import re
from pathlib import Path

from agent_framework.evals.case import EvalCase, Provenance, dump_case, load_set
from agent_framework.project import load_project_config
from agent_framework.validator.bundle import CIEvidence, EvidenceBundle, TaskRef
from agent_framework.validator.checks import run_checks

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "evals" / "validator" / "cases"
TEST_PATTERN = re.compile(load_project_config(ROOT).test_pattern, re.MULTILINE)


def _rejected(cases: tuple[EvalCase, ...]) -> list[str]:
    """Every case the deterministic stage would reject: `case: check — finding`."""
    return [
        f"{case.id}: {finding.check} — {finding.finding}"
        for case in cases
        for finding in run_checks(case.bundle, TEST_PATTERN)
    ]


def test_sc3_every_case_in_the_set_loads_and_passes_the_deterministic_stage() -> None:
    """SC-3: every case in the repository's set loads (a file that does not
    is an error naming it) and is one the judgment would really be asked
    about — the deterministic stage finds nothing in it."""
    cases = load_set(CASES)

    assert cases, f"no eval cases in {CASES}"
    assert _rejected(cases) == []


def test_sc3_a_case_the_stage_would_reject_is_named_with_its_check(tmp_path: Path) -> None:
    """SC-3: a case that would be rejected there fails the check above,
    naming the case and the check — shown on a set with one such case."""
    source = 'def test_a() -> None:\n    """SC-1."""\n    assert collect() == 1\n'

    def case(case_id: str, *, green: bool) -> EvalCase:
        return EvalCase(
            id=case_id, kind="accepted", expected="pass", reason="Merged.",
            provenance=Provenance(repo="o/r", pr=1, head="abc", frozen="2026-11-10"),
            bundle=EvidenceBundle(
                task=TaskRef(task_id="T-1", criteria=("SC-1",)), diff="+x = 1\n",
                tests={"tests/test_x.py": source},
                ci=CIEvidence(green=green, summary="ci: SUCCESS" if green else "ci: FAILURE"),
            ),
        )

    for item in (case("pr-1", green=True), case("pr-2", green=False)):
        (tmp_path / f"{item.id}.json").write_text(dump_case(item), encoding="utf-8")

    assert _rejected(load_set(tmp_path)) == ["pr-2: ci — deterministic CI is not green"]


def test_sc11_the_set_has_enough_cases_of_each_kind() -> None:
    """SC-11: at least 12 accepted cases, #77 among them, and at least 9
    seeded-defect cases — at least 3 for each of test honesty, spec
    conformance and criteria integrity."""
    cases = load_set(CASES)
    accepted = [c.id for c in cases if c.kind == "accepted"]
    seeded = [c for c in cases if c.kind == "seeded-defect"]

    assert len(accepted) >= 12 and "pr-77" in accepted
    assert len(seeded) >= 9
    for check in ("test-honesty", "spec-conformance", "criteria-integrity"):
        assert len([c for c in seeded if c.check == check]) >= 3, check
