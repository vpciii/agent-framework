"""Scoring: the classes, the scorecard, a comparable result (specs/validator-eval-set).

Each test's docstring names the one criterion it verifies.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from agent_framework.errors import EvalResultError
from agent_framework.evals.case import EvalCase, Provenance
from agent_framework.evals.scorecard import (
    JudgmentRecord,
    NotJudged,
    Outcome,
    Passed,
    Rejected,
    Result,
    classify,
    compare,
    instructions_fingerprint,
    record,
    render,
    render_comparison,
    result_from_json,
    result_to_json,
    scorecard,
)
from agent_framework.validator import judgment
from agent_framework.validator.bundle import CIEvidence, EvidenceBundle, TaskRef
from agent_framework.validator.verdict import Finding

_BUNDLE = EvidenceBundle(
    task=TaskRef(task_id="T-1", criteria=("SC-1",)),
    diff="+ x",
    tests={"tests/test_x.py": "def test_a(): ..."},
    ci=CIEvidence(green=True, summary="ci: SUCCESS"),
)
_FROM = Provenance(repo="o/r", pr=77, head="abc", frozen="2026-11-10")


def _accepted(case_id: str = "pr-77") -> EvalCase:
    return EvalCase(id=case_id, kind="accepted", expected="pass", reason="Merged.",
                    provenance=_FROM, bundle=_BUNDLE)


def _seeded(case_id: str = "pr-77--tautology", check: str = "test-honesty") -> EvalCase:
    return EvalCase(id=case_id, kind="seeded-defect", expected="reject", check=check,
                    reason="An assertion made a tautology.", provenance=_FROM, bundle=_BUNDLE,
                    base="pr-77")


THEATRE = Finding("test-honesty", "test_a asserts a value against itself", "assert x == x")
CREEP = Finding("spec-conformance", "an unrelated module is rewritten", "see the diff")


def _rec(case: EvalCase, outcome: Outcome, run: int = 1, reported: int | None = None,
         tokens: tuple[int | None, int | None] = (100, 10)) -> JudgmentRecord:
    if reported is None:
        reported = len(outcome.findings) if isinstance(outcome, Rejected) else 0
    return record(case, run, outcome, reported=reported,
                  input_tokens=tokens[0], output_tokens=tokens[1])


def _one_of_each() -> tuple[JudgmentRecord, ...]:
    return (
        _rec(_accepted("pr-1"), Passed()),
        _rec(_accepted("pr-2"), Rejected((CREEP,))),
        _rec(_accepted("pr-3"), NotJudged("provider-error")),
        _rec(_seeded("pr-1--a"), Rejected((CREEP, THEATRE))),
        _rec(_seeded("pr-1--b"), Rejected((CREEP,))),
        _rec(_seeded("pr-1--c"), Passed()),
        _rec(_seeded("pr-1--d"), NotJudged("unsupported-finding"), reported=2),
    )


def _result(judgments: tuple[JudgmentRecord, ...] | None = None, case_set: str = "aaaaaaaaaaaa",
            instructions: str = "bbbbbbbbbbbb", runs: int = 1) -> Result:
    return Result(model="google:judge-9", date="2026-11-10", runs=runs,
                  instructions=instructions, case_set=case_set,
                  judgments=_one_of_each() if judgments is None else judgments)


# ---- SC-7: the classes and the counts --------------------------------------


@pytest.mark.parametrize(
    ("case", "outcome", "expected"),
    [
        (_accepted(), Passed(), "passed"),
        (_accepted(), Rejected((CREEP,)), "wrongly-rejected"),
        (_accepted(), NotJudged("truncated"), "could-not-judge"),
        (_seeded(), Rejected((THEATRE,)), "caught"),
        (_seeded(), Rejected((CREEP, THEATRE)), "caught"),
        (_seeded(), Rejected((CREEP,)), "other-reason"),
        (_seeded(), Passed(), "missed"),
        (_seeded(), NotJudged("provider-error"), "could-not-judge"),
    ],
)
def test_sc7_each_outcome_of_each_kind_of_case_has_its_class(
    case: EvalCase, outcome: Outcome, expected: str
) -> None:
    """SC-7: a seeded defect rejected under a different checklist item is
    "another reason", not caught."""
    assert classify(case, outcome) == expected


def test_sc7_an_accepted_case_with_a_corrected_answer_is_scored_as_a_defect() -> None:
    """SC-7 here: scoring follows the expected outcome, so an accepted case
    re-labelled `reject` is caught or missed, never wrongly rejected."""
    relabelled = dataclasses.replace(_accepted(), expected="reject", check="spec-conformance")

    assert classify(relabelled, Rejected((CREEP,))) == "caught"
    assert classify(relabelled, Passed()) == "missed"


def test_sc7_the_scorecard_counts_one_of_each() -> None:
    """SC-7: the counts are right for a run holding one of each outcome for
    each kind of case; could-not-judge is in neither the right nor the
    wrong count."""
    card = scorecard(_one_of_each())

    assert card.accepted == {"passed": 1, "wrongly-rejected": 1, "could-not-judge": 1}
    assert card.seeded == {"caught": 1, "other-reason": 1, "missed": 1, "could-not-judge": 1}
    # Right and wrong are counted over what was judged, never over the holes.
    assert card.accepted["passed"] + card.accepted["wrongly-rejected"] == 2
    assert card.seeded["caught"] + card.seeded["other-reason"] + card.seeded["missed"] == 3


def test_sc7_dropped_findings_and_tokens_are_summed() -> None:
    """SC-7: the number of unsupported findings dropped, and the tokens used."""
    judgments = (
        _rec(_accepted("pr-1"), Rejected((CREEP,)), reported=3, tokens=(1000, 200)),
        _rec(_seeded("pr-1--a"), NotJudged("unsupported-finding"), reported=2, tokens=(500, 50)),
        _rec(_seeded("pr-1--b"), NotJudged("provider-error"), tokens=(None, None)),
        _rec(_accepted("pr-2"), Passed(), tokens=(40, 4)),
    )

    card = scorecard(judgments)

    assert [j.dropped for j in judgments] == [2, 2, 0, 0]
    assert (card.dropped, card.input_tokens, card.output_tokens) == (4, 1540, 254)


def test_sc7_a_case_whose_runs_disagree_is_marked_unstable() -> None:
    """SC-7 here: with several runs the counts are of judgments, and a case
    whose runs disagree is named."""
    judgments = (
        _rec(_accepted("pr-1"), Passed(), run=1),
        _rec(_accepted("pr-1"), Rejected((CREEP,)), run=2),
        _rec(_accepted("pr-2"), Passed(), run=1),
        _rec(_accepted("pr-2"), Passed(), run=2),
    )

    card = scorecard(judgments)

    assert card.accepted == {"passed": 3, "wrongly-rejected": 1, "could-not-judge": 0}
    assert card.unstable == ("pr-1",)


# ---- SC-8: every wrong case is listed with the model's findings ------------


def test_sc8_the_rendering_lists_each_wrong_case_with_its_findings() -> None:
    """SC-8: wrongly rejected, missed and other-reason cases, each with the
    findings the model gave, so a human can decide who was wrong."""
    text = render(_result())

    wrongly, missed, other = (
        text.index("Wrongly rejected"), text.index("Missed"),
        text.index("Rejected for another reason"),
    )
    assert wrongly < text.index("pr-2", wrongly) < missed
    assert "[spec-conformance] an unrelated module is rewritten" in text[wrongly:missed]
    assert "see the diff" in text[wrongly:missed]
    assert "pr-1--c" in text[missed:other] and "test-honesty" in text[missed:other]
    assert "pr-1--b" in text[other:] and "an unrelated module is rewritten" in text[other:]
    # A case the judgment got right is not in the lists.
    assert "pr-1--a" not in text[wrongly:]


def test_sc8_the_rendering_puts_the_case_count_beside_every_rate() -> None:
    """SC-8 here: a rate is never shown without what it is a rate of, and
    could-not-judge is shown apart with its reason."""
    text = render(_result())

    assert "passed            1 of 2 judged (50%)" in text
    assert "caught            1 of 3 judged (33%)" in text
    assert "could not judge   1" in text
    assert "pr-3: provider-error" in text and "pr-1--d: unsupported-finding" in text
    assert "google:judge-9" in text and "2026-11-10" in text
    assert "aaaaaaaaaaaa" in text and "bbbbbbbbbbbb" in text


def test_sc8_a_run_with_nothing_judged_shows_no_rate() -> None:
    """SC-8 here: no division by zero and no invented percentage."""
    text = render(_result((_rec(_accepted("pr-1"), NotJudged("provider-error")),)))

    assert "passed            0 of 0 judged" in text and "%" not in text


# ---- SC-9: a result says what was measured, and when two can be compared ---


def test_sc9_a_result_round_trips_with_what_was_measured() -> None:
    """SC-9: the model, the date and both fingerprints, every judgment and
    the scorecard — written and read back equal."""
    result = _result()

    text = result_to_json(result)
    back = result_from_json(text)

    assert back == result
    data = json.loads(text)
    assert (data["model"], data["date"], data["runs"]) == ("google:judge-9", "2026-11-10", 1)
    assert (data["instructions"], data["case_set"]) == ("bbbbbbbbbbbb", "aaaaaaaaaaaa")
    assert data["scorecard"]["accepted"] == {
        "passed": 1, "wrongly-rejected": 1, "could-not-judge": 1,
    }
    assert data["judgments"][1]["class"] == "wrongly-rejected"
    assert data["judgments"][1]["findings"] == [
        {"check": "spec-conformance", "finding": "an unrelated module is rewritten",
         "evidence": "see the diff"},
    ]


@pytest.mark.parametrize("text", ["{ not json", "[]", '{"model": "m"}'])
def test_sc9_a_malformed_result_file_is_a_typed_error(text: str) -> None:
    """SC-9 here: a result that cannot be read fails loudly, not as a KeyError."""
    with pytest.raises(EvalResultError):
        result_from_json(text)


def test_sc9_the_instructions_fingerprint_moves_with_the_instructions_and_the_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SC-9: it changes when the wording or the tool's schema changes, and
    is the same from one call to the next."""
    before = instructions_fingerprint()
    assert instructions_fingerprint() == before and len(before) == 12

    monkeypatch.setattr(judgment, "REFUTATION_CHECKLIST", judgment.REFUTATION_CHECKLIST + "\n5. …")
    reworded = instructions_fingerprint()
    assert reworded != before
    monkeypatch.undo()

    schema = json.loads(json.dumps(judgment.VERDICT_TOOL.parameters))
    schema["properties"]["findings"]["items"]["properties"]["quotes"]["minItems"] = 2
    monkeypatch.setattr(
        judgment, "VERDICT_TOOL", dataclasses.replace(judgment.VERDICT_TOOL, parameters=schema)
    )
    assert instructions_fingerprint() not in (before, reworded)
    monkeypatch.undo()

    assert instructions_fingerprint() == before


def test_sc9_the_instructions_fingerprint_does_not_move_with_the_data() -> None:
    """SC-9: it is taken from a fixed placeholder, so no case — and no
    change to the case set — can move it."""
    before = instructions_fingerprint()

    request = judgment.build_request(dataclasses.replace(_BUNDLE, diff="+ something else"))

    assert request.prompt  # judging real data in between changes nothing
    assert instructions_fingerprint() == before


def test_sc9_results_on_different_case_sets_are_not_comparable() -> None:
    """SC-9: comparing two results whose case sets differ says so, and
    offers no differences to misread."""
    comparison = compare(_result(case_set="aaaaaaaaaaaa"), _result(case_set="cccccccccccc"))

    assert comparison.comparable is False and comparison.changed == ()
    text = render_comparison(_result(case_set="aaaaaaaaaaaa"), _result(case_set="cccccccccccc"))
    assert "not comparable" in text and "aaaaaaaaaaaa" in text and "cccccccccccc" in text


def test_sc9_comparable_results_show_the_cases_whose_class_changed() -> None:
    """SC-9 here: same case set — the comparison names what moved, and only that."""
    before = _result()
    fixed = tuple(
        _rec(_accepted("pr-2"), Passed()) if j.case == "pr-2" else j for j in _one_of_each()
    )
    after = _result(fixed, instructions="dddddddddddd")

    comparison = compare(before, after)

    assert comparison.comparable is True
    assert [(c.case, c.before, c.after) for c in comparison.changed] == [
        ("pr-2", ("wrongly-rejected",), ("passed",)),
    ]
    text = render_comparison(before, after)
    assert "pr-2: wrongly-rejected → passed" in text
    assert "bbbbbbbbbbbb" in text and "dddddddddddd" in text  # what changed between the runs
