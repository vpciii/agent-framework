"""Citations come from the spec's Traceability table (specs/citation-from-traceability).

Through the real collector against a faked `gh` runner, then the real gate.
Each test's docstring names the one criterion it verifies.
"""

from __future__ import annotations

import json

import pytest

from agent_framework.validator.bundle import CIEvidence, Contract, EvidenceBundle, TaskRef
from agent_framework.validator.collector import collect_bundle
from agent_framework.validator.gate import validate
from agent_framework.validator.verdict import Pass, Reject, verdict_from_json, verdict_to_json

from .test_evidence import _runner, _view, _wire

_HEAD, _BASE = "head222", "base111"
_BODY = "Implements **T-3** from `specs/widget/tasks.md`.\n\nSatisfies: SC-1\n"


def _spec(row: str) -> str:
    return f"""# Spec: Widget

## Success criteria

- **SC-1** — The widget spins when asked. (R-1)

## Traceability

| Criterion | Requirement(s) | Verified by (test) |
|---|---|---|
{row}
"""


_REAL = "tests/test_widget.py"
_REAL_TEST = 'def test_spins() -> None:\n    """SC-1."""\n    assert True\n'
_ROW = f"| SC-1 | R-1 | `{_REAL}::test_spins` |"
# An older test, for another spec, that merely mentions the id in a string —
# in a file that sorts ahead of the real one.
_OLDER = "tests/test_a_orchestrator.py"
_OLDER_TEST = (
    "def test_pr_body_declares_the_criteria() -> None:\n"
    '    assert "Satisfies: SC-1, SC-2" in "Satisfies: SC-1, SC-2"\n'
)


def _files(row: str, **extra: str) -> dict[tuple[str, str], str]:
    files = {
        ("specs/widget/spec.md", _BASE): _spec("| SC-1 | R-1 | *(pending)* |"),
        ("specs/widget/spec.md", _HEAD): _spec(row),
        (_REAL, _HEAD): _REAL_TEST,
    }
    files.update({(path, _HEAD): text for path, text in extra.items()})
    return files


def test_sc1_bundle_carries_the_tables_tests_and_fetches_an_unchanged_file() -> None:
    """SC-1 here: the table is read at the PR's head; the test file it names
    is fetched although the PR did not change it."""
    run = _runner(_view(_BODY, ["src/widget.py", "specs/widget/spec.md"]), _files(_ROW))

    bundle = collect_bundle(7, run=run)

    assert bundle.contract is not None
    assert bundle.contract.cited_tests == {"SC-1": (f"{_REAL}::test_spins",)}
    assert bundle.tests == {_REAL: _REAL_TEST}  # not among the changed files, fetched anyway


async def test_sc2_pass_cites_the_tables_test_not_an_older_one_that_mentions_the_id() -> None:
    """SC-2 here: the 2026-11-09 case. A changed file holds an older test
    with the id in an assertion string; the table names the real test."""
    judge, reg, roster = _wire()
    run = _runner(
        _view(_BODY, [_OLDER, _REAL, "specs/widget/spec.md"]),
        _files(_ROW, **{_OLDER: _OLDER_TEST}),
    )

    verdict = await validate(collect_bundle(7, run=run), roster, registry=reg)

    assert isinstance(verdict, Pass)
    assert [(c.criterion, c.test) for c in verdict.citations] == [
        ("SC-1", f"{_REAL}::test_spins")
    ]
    assert len(judge.calls) == 1


@pytest.mark.parametrize(
    ("row", "real_test", "names"),
    [
        # (a) no row at all for the claimed criterion.
        ("| SC-9 | R-9 | `tests/test_widget.py::test_spins` |", _REAL_TEST, "SC-1"),
        # (a) a pending cell.
        ("| SC-1 | R-1 | *(pending)* |", _REAL_TEST, "SC-1"),
        # (b) the named file does not exist at the head.
        ("| SC-1 | R-1 | `tests/test_gone.py::test_spins` |", _REAL_TEST, "tests/test_gone.py"),
        # (c) no test of that name in the file.
        (f"| SC-1 | R-1 | `{_REAL}::test_whirls` |", _REAL_TEST, "test_whirls"),
        # (d) the named test's own text does not contain the id.
        (_ROW, "def test_spins() -> None:\n    assert True\n", "test_spins"),
    ],
)
async def test_sc3_a_missing_or_unconfirmed_table_entry_rejects_without_a_model_call(
    row: str, real_test: str, names: str
) -> None:
    """SC-3 here: no row, pending, missing file, missing test, or a test
    that does not cite the criterion — each a free REJECT naming it."""
    judge, reg, roster = _wire()
    # An older test that mentions the id is present throughout: it must not rescue the claim.
    files = _files(row, **{_OLDER: _OLDER_TEST})
    files[(_REAL, _HEAD)] = real_test
    run = _runner(_view(_BODY, [_OLDER, _REAL, "specs/widget/spec.md"]), files)

    verdict = await validate(collect_bundle(7, run=run), roster, registry=reg)

    assert isinstance(verdict, Reject)
    [finding] = [f for f in verdict.findings if f.check == "criterion-citation"]
    assert "SC-1" in finding.finding
    assert names in finding.finding or names in finding.evidence
    assert judge.calls == []


async def test_sc4_judgment_request_lists_each_criterions_cited_tests() -> None:
    """SC-4 here: the judge is told which tests are the cited ones."""
    judge, reg, roster = _wire()
    run = _runner(
        _view(_BODY, [_OLDER, _REAL, "specs/widget/spec.md"]),
        _files(_ROW, **{_OLDER: _OLDER_TEST}),
    )

    await validate(collect_bundle(7, run=run), roster, registry=reg)

    [request] = judge.calls
    data = request.prompt.split("===== BEGIN DATA =====")[1].split("===== END DATA =====")[0]
    cited = data[data.index("[CITED TESTS") : data.index("[TASK")]
    assert f"SC-1: {_REAL}::test_spins" in cited
    assert _OLDER not in cited


async def test_sc5_two_tests_in_a_row_are_both_cited_and_the_json_form_is_unchanged() -> None:
    """SC-5 here: every test the row names; the same verdict JSON; a
    hand-built bundle with no contract passes exactly as before."""
    _, reg, roster = _wire()
    second = "tests/test_widget_edge.py"
    row = f"| SC-1 | R-1 | `{_REAL}::test_spins`, `{second}::test_spins_backwards` |"
    files = _files(row, **{second: 'def test_spins_backwards() -> None:\n    """SC-1."""\n'})
    run = _runner(_view(_BODY, [_REAL, second, "specs/widget/spec.md"]), files)

    verdict = await validate(collect_bundle(7, run=run), roster, registry=reg)

    assert isinstance(verdict, Pass)
    assert [(c.criterion, c.test) for c in verdict.citations] == [
        ("SC-1", f"{_REAL}::test_spins"),
        ("SC-1", f"{second}::test_spins_backwards"),
    ]
    text = verdict_to_json(verdict)
    assert verdict_from_json(text) == verdict
    assert set(json.loads(text)) == {"verdict", "task_id", "citations", "ci"}
    assert set(json.loads(text)["citations"][0]) == {"criterion", "test"}

    # No contract (hand-built, not from the collector): the id scan, as before.
    legacy = EvidenceBundle(
        task=TaskRef(task_id="T-3", criteria=("SC-1",)),
        diff="+ x",
        tests={_REAL: _REAL_TEST},
        ci=CIEvidence(green=True, summary="ci: SUCCESS"),
    )
    legacy_verdict = await validate(legacy, roster, registry=reg)
    assert isinstance(legacy_verdict, Pass)
    assert [(c.criterion, c.test) for c in legacy_verdict.citations] == [
        ("SC-1", f"{_REAL}::test_spins")
    ]


async def test_a_contract_without_table_entries_is_not_rescued_by_the_scan() -> None:
    """A bundle that carries a resolved contract is held to the table, even
    when built by hand."""
    _, reg, roster = _wire()
    bundle = EvidenceBundle(
        task=TaskRef(task_id="T-3", criteria=("SC-1",)),
        diff="+ x",
        tests={_REAL: _REAL_TEST},
        ci=CIEvidence(green=True, summary="ci: SUCCESS"),
        contract=Contract(spec_slug="widget", criterion_texts={"SC-1": "**SC-1** — spins"}),
    )

    assert isinstance(await validate(bundle, roster, registry=reg), Reject)
