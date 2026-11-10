"""Eval cases: the file format, the loader, seeded edits (specs/validator-eval-set).

Each test's docstring names the one criterion it verifies.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agent_framework.errors import EvalCaseError
from agent_framework.evals.case import (
    EvalCase,
    Provenance,
    dump_case,
    load_case,
    load_set,
    set_fingerprint,
)
from agent_framework.validator.bundle import CIEvidence, Contract, EvidenceBundle, TaskRef

TEST_A = 'def test_a() -> None:\n    """SC-1."""\n    assert collect() == expected\n'
TEST_B = 'def test_b() -> None:\n    """SC-2."""\n    assert render() == "ok"\n'
DIFF = (
    "diff --git a/tests/test_a.py b/tests/test_a.py\n"
    "@@ -0,0 +1,3 @@\n"
    "+def test_a() -> None:\n"
    '+    """SC-1."""\n'
    "+    assert collect() == expected\n"
)


def _bundle(contract: Contract | None = None) -> EvidenceBundle:
    return EvidenceBundle(
        task=TaskRef(task_id="T-4", criteria=("SC-1", "SC-2"), is_fix=True),
        diff=DIFF,
        tests={"tests/test_a.py": TEST_A, "tests/test_b.py": TEST_B},
        ci=CIEvidence(green=True, summary="ci: SUCCESS"),
        red_evidence="FAILED tests/test_a.py::test_a",
        contract=contract,
    )


CONTRACT = Contract(
    spec_slug="some-feature",
    criterion_texts={"SC-1": "- **SC-1** — It collects.", "SC-2": "- **SC-2** — It renders."},
    task_block="### [ ] T-4 — Collect and render",
    cited_tests={"SC-1": ("tests/test_a.py::test_a",),
                 "SC-2": ("tests/test_b.py::test_b", "tests/test_a.py::test_a")},
    read_from="head",
    ref="84a707e",
)
PROVENANCE = Provenance(repo="vpciii/agent-framework", pr=77, head="6b1f2c3", frozen="2026-11-10")


def _accepted(case_id: str = "pr-77", contract: Contract | None = CONTRACT) -> EvalCase:
    return EvalCase(
        id=case_id, kind="accepted", expected="pass",
        reason="Merged 2026-11-09; accepted by vpc.",
        provenance=PROVENANCE, bundle=_bundle(contract),
    )


def _write(directory: Path, case: EvalCase) -> Path:
    path = directory / f"{case.id}.json"
    path.write_text(dump_case(case), encoding="utf-8")
    return path


def _write_raw(directory: Path, name: str, data: Any) -> Path:
    path = directory / f"{name}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _raw_accepted() -> dict[str, Any]:
    data = json.loads(dump_case(_accepted()))
    assert isinstance(data, dict)
    return data


# ---- SC-1: a case file round-trips, and a malformed one names itself --------


@pytest.mark.parametrize("contract", [CONTRACT, None], ids=["with a contract", "without one"])
def test_sc1_an_accepted_case_round_trips_to_an_equal_bundle(
    tmp_path: Path, contract: Contract | None
) -> None:
    """SC-1: frozen, written, read back — the same bundle, expected outcome,
    reason and provenance."""
    case = _accepted(contract=contract)

    loaded = load_case(_write(tmp_path, case))

    assert loaded == case
    assert loaded.bundle == _bundle(contract)  # tuples and nested values, not look-alikes
    assert loaded.expected == "pass" and loaded.check is None
    assert loaded.provenance == PROVENANCE


def test_sc1_an_accepted_case_can_carry_a_corrected_answer(tmp_path: Path) -> None:
    """SC-1 here: an accepted pull request found to hold a real defect is
    re-labelled `reject` with its checklist item, and still round-trips."""
    data = _raw_accepted() | {"expected": "reject", "check": "test-honesty"}

    loaded = load_case(_write_raw(tmp_path, "pr-77", data))

    assert (loaded.kind, loaded.expected, loaded.check) == ("accepted", "reject", "test-honesty")
    assert load_case(_write(tmp_path, loaded)) == loaded


def _without(key: str) -> dict[str, Any]:
    data = _raw_accepted()
    del data[key]
    return data


def _with(**changes: Any) -> dict[str, Any]:
    return _raw_accepted() | changes


def _nested(outer: str, drop: str) -> dict[str, Any]:
    data = _raw_accepted()
    del data[outer][drop]
    return data


@pytest.mark.parametrize(
    ("data", "names"),
    [
        (_without("id"), "id"),
        (_without("kind"), "kind"),
        (_without("expected"), "expected"),
        (_without("reason"), "reason"),
        (_without("provenance"), "provenance"),
        (_without("bundle"), "bundle"),
        (_nested("provenance", "head"), "head"),
        (_nested("bundle", "diff"), "diff"),
        (_nested("bundle", "ci"), "ci"),
        (_with(kind="golden"), "kind"),
        (_with(expected="maybe"), "expected"),
        (_with(expected="reject"), "check"),
        (_with(expected="reject", check="looks-wrong"), "check"),
        (_with(check="test-honesty"), "check"),
        (_with(id="pr-78"), "id"),
        (_with(reason="  "), "reason"),
        (["not", "an", "object"], "object"),
    ],
    ids=[
        "no id", "no kind", "no expected", "no reason", "no provenance", "no bundle",
        "provenance without head", "bundle without diff", "bundle without ci",
        "unknown kind", "unknown expected", "reject with no checklist item",
        "reject under an unknown item", "pass with a checklist item",
        "id is not the file's name", "blank reason", "not an object",
    ],
)
def test_sc1_a_malformed_case_fails_to_load_naming_the_file(
    tmp_path: Path, data: Any, names: str
) -> None:
    """SC-1: a file missing any part, or a `reject` with no checklist item,
    fails to load — and the error says which file and what."""
    path = _write_raw(tmp_path, "pr-77", data)

    with pytest.raises(EvalCaseError) as raised:
        load_case(path)

    assert "pr-77.json" in str(raised.value) and names in str(raised.value)


def test_sc1_a_file_that_is_not_json_fails_naming_the_file(tmp_path: Path) -> None:
    """SC-1 here: unparseable text is the same typed error, not a traceback
    from the JSON library."""
    path = tmp_path / "pr-77.json"
    path.write_text("{ not json", encoding="utf-8")

    with pytest.raises(EvalCaseError, match=r"pr-77\.json"):
        load_case(path)


# ---- SC-2: a seeded-defect case is its accepted case plus exactly its edit --

TAUTOLOGY = [
    {"in": "diff", "replace": "+    assert collect() == expected",
     "with": "+    assert expected == expected"},
    {"in": "tests/test_a.py", "replace": "    assert collect() == expected",
     "with": "    assert expected == expected"},
]


def _seeded(**changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "pr-77--tautology", "kind": "seeded-defect", "base": "pr-77",
        "expected": "reject", "check": "test-honesty",
        "reason": "SC-1's test asserts a value against itself.", "edit": TAUTOLOGY,
    }
    return base | changes


def _set(tmp_path: Path, seeded: dict[str, Any]) -> Path:
    _write(tmp_path, _accepted())
    return _write_raw(tmp_path, "pr-77--tautology", seeded)


def test_sc2_a_seeded_case_is_its_base_with_exactly_the_edit_applied(tmp_path: Path) -> None:
    """SC-2: the bundle differs from the accepted case's by the named edit
    — in the diff and in the test file — and by nothing else."""
    case = load_case(_set(tmp_path, _seeded()))
    base = _bundle(CONTRACT)

    assert (case.kind, case.expected, case.check, case.base) == (
        "seeded-defect", "reject", "test-honesty", "pr-77",
    )
    assert case.bundle.diff == base.diff.replace(
        "+    assert collect() == expected", "+    assert expected == expected"
    )
    assert case.bundle.tests["tests/test_a.py"] == TEST_A.replace(
        "assert collect() == expected", "assert expected == expected"
    )
    assert case.bundle.tests["tests/test_b.py"] == TEST_B
    assert (case.bundle.task, case.bundle.ci, case.bundle.red_evidence, case.bundle.contract) == (
        base.task, base.ci, base.red_evidence, base.contract,
    )
    assert case.provenance == PROVENANCE  # where its accepted case came from


@pytest.mark.parametrize(
    ("edit", "says"),
    [
        ([{"in": "diff", "replace": "+    assert never_written()", "with": "+    pass"}],
         "0 times"),
        ([{"in": "diff", "replace": "test_a", "with": "test_z"}], "3 times"),
        ([{"in": "tests/test_missing.py", "replace": "assert", "with": "pass"}],
         "tests/test_missing.py"),
        ([{"in": "diff", "replace": "", "with": "+    pass"}], "replace"),
        ([{"in": "diff", "replace": "+def test_a() -> None:", "with": "+def test_a() -> None:"}],
         "changes nothing"),
        ([], "edit"),
        ([{"in": "diff", "replace": "+def test_a() -> None:"}], "with"),
    ],
    ids=["text absent", "text present three times", "a file the bundle does not hold",
         "empty text to find", "an edit that changes nothing", "no replacements",
         "a replacement without its new text"],
)
def test_sc2_an_edit_that_does_not_apply_exactly_once_fails_to_load(
    tmp_path: Path, edit: list[dict[str, str]], says: str
) -> None:
    """SC-2: an edit whose text is absent, or present more than once, is an
    error naming the case's file."""
    path = _set(tmp_path, _seeded(edit=edit))

    with pytest.raises(EvalCaseError) as raised:
        load_case(path)

    assert "pr-77--tautology.json" in str(raised.value) and says in str(raised.value)


@pytest.mark.parametrize(
    ("changes", "says"),
    [
        ({"base": "pr-99"}, "pr-99"),
        ({"base": "pr-77--tautology"}, "accepted"),
        ({"expected": "pass", "check": None}, "reject"),
        ({"check": None}, "check"),
    ],
    ids=["a base that is not in the set", "a base that is itself seeded",
         "a seeded case expected to pass", "no checklist item"],
)
def test_sc2_a_seeded_case_needs_an_accepted_base_and_a_reject(
    tmp_path: Path, changes: dict[str, Any], says: str
) -> None:
    """SC-2 here: the base must be an accepted case in the same set, and a
    seeded defect is always expected to be rejected."""
    path = _set(tmp_path, _seeded(**changes))

    with pytest.raises(EvalCaseError) as raised:
        load_case(path)

    assert "pr-77--tautology.json" in str(raised.value) and says in str(raised.value)


def test_sc2_the_set_loads_every_case_of_both_kinds(tmp_path: Path) -> None:
    """SC-2 here: a directory loads as the set — accepted and seeded cases
    together, in a stable order."""
    _set(tmp_path, _seeded())
    _write(tmp_path, _accepted("pr-81"))
    (tmp_path / "README.md").write_text("not a case", encoding="utf-8")

    cases = load_set(tmp_path)

    assert [c.id for c in cases] == ["pr-77", "pr-77--tautology", "pr-81"]
    assert [c.kind for c in cases] == ["accepted", "seeded-defect", "accepted"]


def test_the_case_sets_fingerprint_moves_only_when_a_case_does(tmp_path: Path) -> None:
    """Groundwork for SC-9 (delivered with the scorecard): the fingerprint
    changes when a case is added, edited or removed, and not otherwise."""
    _set(tmp_path, _seeded())
    first = set_fingerprint(tmp_path)

    assert set_fingerprint(tmp_path) == first and len(first) == 12
    (tmp_path / "notes.txt").write_text("not a case", encoding="utf-8")
    assert set_fingerprint(tmp_path) == first

    added = _write(tmp_path, _accepted("pr-81"))
    with_added = set_fingerprint(tmp_path)
    assert with_added != first

    _write_raw(tmp_path, "pr-77--tautology", _seeded(reason="Reworded."))
    edited = set_fingerprint(tmp_path)
    assert edited not in (first, with_added)

    added.unlink()
    assert set_fingerprint(tmp_path) not in (with_added, edited)
