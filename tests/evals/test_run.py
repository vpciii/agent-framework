"""The eval run (specs/validator-eval-set).

Each test's docstring names the one criterion it verifies. No model is
called: the validator's adapter is a fake.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from agent_framework.errors import ProviderError
from agent_framework.evals.case import EvalCase, Provenance
from agent_framework.evals.run import run_eval
from agent_framework.providers.base import Request, Response, ToolCall, Usage
from agent_framework.providers.registry import ProviderRegistry
from agent_framework.roster import Roster
from agent_framework.validator.bundle import CIEvidence, EvidenceBundle, TaskRef
from agent_framework.validator.judgment import VERDICT_TOOL, build_request
from agent_framework.validator.verdict import Finding

_FROM = Provenance(repo="o/r", pr=77, head="abc", frozen="2026-11-10")


def _bundle(task_id: str) -> EvidenceBundle:
    return EvidenceBundle(
        task=TaskRef(task_id=task_id, criteria=("SC-1",)),
        diff=f"+def collect_{task_id.lower().replace('-', '_')}() -> int:\n+    return 1\n",
        tests={"tests/test_x.py": 'def test_a() -> None:\n    """SC-1."""\n    assert collect() == 1\n'},
        ci=CIEvidence(green=True, summary="ci: SUCCESS"),
    )


def _accepted(case_id: str) -> EvalCase:
    return EvalCase(id=case_id, kind="accepted", expected="pass", reason="Merged.",
                    provenance=_FROM, bundle=_bundle(case_id.upper()))


def _seeded(case_id: str, check: str = "test-honesty") -> EvalCase:
    return EvalCase(id=case_id, kind="seeded-defect", expected="reject", check=check,
                    reason="Planted.", provenance=_FROM, bundle=_bundle(case_id.upper()),
                    base="pr-1")


def _answer(defect_found: bool, *findings: dict[str, Any], usage: Usage | None = None) -> Response:
    arguments = {"defect_found": defect_found, "findings": list(findings)}
    return Response(text="", tool_calls=(ToolCall(VERDICT_TOOL.name, arguments),),
                    stop="complete", stop_detail="STOP", usage=usage)


def _finding(quote: str, check: str = "test-honesty") -> dict[str, Any]:
    return {"check": check, "finding": "the test checks nothing", "evidence": "see the quote",
            "quotes": [quote]}


REAL_QUOTE = "assert collect() == 1"
INVENTED_QUOTE = "assert never_written() == 2"


class _Fake:
    """Answers in order: each item is a Response, or an exception to raise."""

    def __init__(self, *answers: Response | Exception) -> None:
        self.answers = list(answers)
        self.calls: list[tuple[Request, str]] = []

    async def invoke(self, request: Request, *, model: str) -> Response:
        self.calls.append((request, model))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def _wire(*answers: Response | Exception) -> tuple[_Fake, ProviderRegistry, Roster]:
    fake, registry = _Fake(*answers), ProviderRegistry()
    registry.register("fake", fake)
    roster = Roster.from_dict({
        "roles": {"validator": {"provider": "fake", "model": "judge-9"},
                  "worker": {"provider": "fake", "model": "builder-1"}},
    })
    return fake, registry, roster


# ---- SC-5: the judgment is made as the gate makes it, and recorded ---------


async def test_sc5_each_case_is_sent_the_gates_own_request_through_the_validator_role() -> None:
    """SC-5: the request for a case is the request the gate would send for
    that bundle, and it goes to the roster's validator model."""
    cases = (_accepted("pr-1"), _seeded("pr-1--a"))
    fake, registry, roster = _wire(_answer(False), _answer(False))

    await run_eval(cases, roster, registry=registry)

    assert [request for request, _ in fake.calls] == [build_request(c.bundle) for c in cases]
    assert [model for _, model in fake.calls] == ["judge-9", "judge-9"]


async def test_sc5_a_pass_and_a_reject_are_recorded_as_such() -> None:
    """SC-5: pass, and reject with its findings — scored against each
    case's expected outcome."""
    usage = Usage(input_tokens=1200, output_tokens=340)
    _, registry, roster = _wire(
        _answer(False, usage=usage),
        _answer(True, _finding(REAL_QUOTE), _finding(INVENTED_QUOTE), usage=usage),
    )

    passed, rejected = await run_eval(
        (_accepted("pr-1"), _seeded("pr-1--a")), roster, registry=registry
    )

    assert (passed.case, passed.run, passed.outcome, passed.cls) == ("pr-1", 1, "pass", "passed")
    assert (passed.reported, passed.dropped, passed.findings) == (0, 0, ())
    assert (rejected.outcome, rejected.cls) == ("reject", "caught")
    assert rejected.findings == (
        Finding("test-honesty", "the test checks nothing", "see the quote"),
    )
    # The model reported two findings; the quote check dropped the invented one.
    assert (rejected.reported, rejected.dropped) == (2, 1)
    assert (rejected.input_tokens, rejected.output_tokens) == (1200, 340)


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        (Response(text='{"defect', stop="truncated", stop_detail="MAX_TOKENS"), "truncated"),
        (Response(text="", stop="refused", stop_detail="SAFETY"), "refused"),
        (Response(text="LGTM", stop="complete", stop_detail="STOP"), "no-answer"),
        (_answer(True, _finding(INVENTED_QUOTE)), "unsupported-finding"),
        (_answer(True, {"check": "test-honesty"}), "malformed"),
    ],
)
async def test_sc5_could_not_judge_is_recorded_with_its_reason(
    answer: Response, reason: str
) -> None:
    """SC-5: each way the gate cannot judge is that case's could-not-judge,
    named as the gate's CLI names it — never a pass and never a reject."""
    _, registry, roster = _wire(answer)

    [judged] = await run_eval((_seeded("pr-1--a"),), roster, registry=registry)

    assert (judged.outcome, judged.reason, judged.cls) == ("none", reason, "could-not-judge")
    assert judged.findings == ()


async def test_sc5_findings_dropped_before_no_verdict_are_counted() -> None:
    """SC-5 here: when every reported finding was unsupported, all of them
    are counted as dropped."""
    _, registry, roster = _wire(
        _answer(True, _finding(INVENTED_QUOTE), _finding("assert also_invented() is None"))
    )

    [judged] = await run_eval((_accepted("pr-1"),), roster, registry=registry)

    assert (judged.reason, judged.reported, judged.dropped) == ("unsupported-finding", 2, 2)


async def test_sc5_a_case_may_be_run_more_than_once() -> None:
    """SC-5: with two runs every case is judged twice, each run numbered."""
    fake, registry, roster = _wire(_answer(False), _answer(False), _answer(False),
                                   _answer(True, _finding(REAL_QUOTE)))
    cases = (_accepted("pr-1"), _accepted("pr-2"))

    judged = await run_eval(cases, roster, registry=registry, runs=2)

    assert [(j.case, j.run, j.cls) for j in judged] == [
        ("pr-1", 1, "passed"), ("pr-2", 1, "passed"),
        ("pr-1", 2, "passed"), ("pr-2", 2, "wrongly-rejected"),
    ]
    assert len(fake.calls) == 4


async def test_sc5_each_judgment_is_reported_as_it_is_made() -> None:
    """SC-5 here: the caller sees each record as it lands — a long run is
    visibly alive."""
    _, registry, roster = _wire(_answer(False), _answer(False))
    seen: list[str] = []

    await run_eval((_accepted("pr-1"), _accepted("pr-2")), roster, registry=registry,
                   on_judgment=lambda j: seen.append(j.case))

    assert seen == ["pr-1", "pr-2"]


# ---- SC-6: one failure does not end the run --------------------------------


async def test_sc6_a_provider_error_on_one_case_leaves_the_others_judged() -> None:
    """SC-6: the second of three cases hits a provider error — it is
    could-not-judge, and the first and third are still judged."""
    usage = Usage(input_tokens=900, output_tokens=90)
    fake, registry, roster = _wire(
        _answer(False, usage=usage),
        ProviderError("RateLimitError: 429 quota exhausted"),
        _answer(False, usage=usage),
    )

    first, second, third = await run_eval(
        (_accepted("pr-1"), _accepted("pr-2"), _accepted("pr-3")), roster, registry=registry
    )

    assert (first.cls, third.cls) == ("passed", "passed")
    assert (second.outcome, second.reason, second.cls) == (
        "none", "provider-error", "could-not-judge",
    )
    # Nothing of the judgment before it leaks into the failed one.
    assert (second.input_tokens, second.output_tokens, second.reported) == (None, None, 0)
    assert len(fake.calls) == 3


async def test_sc6_the_pause_falls_between_judgments_and_not_after_the_last() -> None:
    """SC-6 here: spacing the calls is how a rate limit is avoided; the
    sleep is injected, so no test waits."""
    _, registry, roster = _wire(_answer(False), _answer(False), _answer(False))
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    await run_eval((_accepted("pr-1"), _accepted("pr-2"), _accepted("pr-3")), roster,
                   registry=registry, pause=7.5, sleep=sleep)

    assert slept == [7.5, 7.5]


async def test_sc6_a_case_that_could_not_be_judged_says_why(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SC-6 here: the provider's own message is logged, naming the case —
    so a human watching a run can tell a bad key from a rate limit. (A
    baseline run on 2026-11-10 showed "provider-error" 36 times and no cause.)"""
    _, registry, roster = _wire(
        ProviderError("ClientError: 429 RESOURCE_EXHAUSTED: quota exceeded"),
        _answer(True, {"check": "test-honesty"}),
    )

    with caplog.at_level(logging.WARNING, logger="agent_framework"):
        first, second = await run_eval(
            (_accepted("pr-1"), _accepted("pr-2")), roster, registry=registry
        )

    assert (first.reason, second.reason) == ("provider-error", "malformed")
    said = [r.getMessage() for r in caplog.records if r.name == "agent_framework.evals.run"]
    assert len(said) == 2
    assert "pr-1" in said[0] and "429 RESOURCE_EXHAUSTED: quota exceeded" in said[0]
    assert "pr-2" in said[1] and "finding" in said[1]
