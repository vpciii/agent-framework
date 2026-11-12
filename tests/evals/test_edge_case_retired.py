"""The eval set after the edge-case item was retired
(specs/conformance-only-judgment, ADR 0008).

Each test's docstring names the one criterion it verifies. No model is
called.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_framework.errors import EvalCaseError
from agent_framework.evals.case import EvalCase, Provenance, dump_case, load_case, load_set
from agent_framework.evals.scorecard import render, result_from_json
from agent_framework.validator.bundle import CIEvidence, EvidenceBundle, TaskRef

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "evals" / "validator" / "cases"
RESULTS = ROOT / "evals" / "validator" / "results"


def _accepted() -> EvalCase:
    return EvalCase(
        id="pr-7", kind="accepted", expected="pass",
        reason="Merged 2026-11-09; accepted by vpc.",
        provenance=Provenance(repo="acme/widgets", pr=7, head="head111", frozen="2026-11-12"),
        bundle=EvidenceBundle(
            task=TaskRef(task_id="T-2", criteria=("SC-1",)),
            diff="+def collect() -> int:\n+    return 1\n",
            tests={"tests/test_x.py": "def test_a() -> None:\n    assert collect() == 1\n"},
            ci=CIEvidence(green=True, summary="ci: SUCCESS"),
        ),
    )


def test_sc4_a_case_that_names_edge_case_fails_to_load_naming_the_file(
    tmp_path: Path,
) -> None:
    """SC-4: `edge-case` is no longer a checklist item a case can name."""
    data = json.loads(dump_case(_accepted())) | {"expected": "reject", "check": "edge-case"}
    path = tmp_path / "pr-7.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(EvalCaseError, match=r"pr-7\.json.*check"):
        load_case(path)


def test_sc4_every_case_in_the_repositorys_set_loads_and_none_names_edge_case() -> None:
    """SC-4: every case in the repository's set loads, so none names the
    retired item."""
    cases = load_set(CASES)

    assert cases, f"no eval cases in {CASES}"
    assert [case.id for case in cases if case.check == "edge-case"] == []


@pytest.mark.parametrize(
    ("name", "shows_edge_case"),
    [("2026-11-10-gemini-3.8-flash.json", True), ("2026-11-12-gemini-3.8-flash.json", False)],
)
def test_sc5_the_results_recorded_before_the_change_still_load_and_render(
    name: str, shows_edge_case: bool
) -> None:
    """SC-5: both result files in the repository on 2026-11-12 load and
    render; the findings the first one recorded under `edge-case` are shown."""
    result = result_from_json((RESULTS / name).read_text(encoding="utf-8"))

    text = render(result)

    assert len(result.judgments) == 36 and "Accepted work (expected PASS)" in text
    recorded = [f for j in result.judgments for f in j.findings if f.check == "edge-case"]
    assert bool(recorded) is shows_edge_case
    assert ("[edge-case]" in text) is shows_edge_case
