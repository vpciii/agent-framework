"""The cite-the-test gate.

Verifies:
- SC-1: clean bundle + no-defect judgment → PASS citing every claimed
  criterion's test and the CI evidence.
- SC-2: a claimed criterion no test cites → deterministic REJECT naming it,
  and the fake provider proves zero model invocations.
- SC-3: red CI → deterministic REJECT citing the CI evidence, zero
  invocations.
- SC-7: a fix-task bundle without red→green evidence → REJECT naming the
  missing evidence.
"""

from __future__ import annotations

from agent_framework.providers.base import Request, Response, ToolCall
from agent_framework.providers.registry import ProviderRegistry
from agent_framework.roster import Roster
from agent_framework.validator.bundle import CIEvidence, EvidenceBundle, TaskRef
from agent_framework.validator.gate import validate
from agent_framework.validator.judgment import VERDICT_TOOL
from agent_framework.validator.verdict import Citation, Pass, Reject

_TESTS = {
    "tests/test_feature.py": (
        '"""Feature tests."""\n'
        "def test_alpha() -> None:\n"
        '    """SC-1: alpha behavior."""\n'
        "    assert True\n"
        "def test_beta() -> None:\n"
        '    """SC-2: beta behavior."""\n'
        "    assert True\n"
    )
}


class _FakeProvider:
    """Records calls; answers return_verdict with no defect."""

    def __init__(self) -> None:
        self.calls: list[tuple[Request, str]] = []

    async def invoke(self, request: Request, *, model: str) -> Response:
        self.calls.append((request, model))
        return Response(
            text="",
            tool_calls=(ToolCall(VERDICT_TOOL.name, {"defect_found": False, "findings": []}),),
        )


def _roster() -> Roster:
    return Roster.from_dict(
        {"roles": {"validator": {"provider": "fake", "model": "judge-1"}}}
    )


def _wire() -> tuple[_FakeProvider, ProviderRegistry]:
    reg = ProviderRegistry()
    fake = _FakeProvider()
    reg.register("fake", fake)
    return fake, reg


def _bundle(
    criteria: tuple[str, ...] = ("SC-1", "SC-2"),
    *,
    green: bool = True,
    is_fix: bool = False,
    red_evidence: str | None = None,
) -> EvidenceBundle:
    return EvidenceBundle(
        task=TaskRef(task_id="T-9", criteria=criteria, is_fix=is_fix),
        diff="+ the change",
        tests=_TESTS,
        ci=CIEvidence(green=green, summary="ci run 42: green" if green else "ci run 42: RED"),
        red_evidence=red_evidence,
    )


async def test_sc1_clean_bundle_and_clean_judgment_pass_with_citations() -> None:
    """SC-1: PASS lists every claimed criterion with its citing test + CI evidence."""
    fake, reg = _wire()

    verdict = await validate(_bundle(), _roster(), registry=reg)

    assert isinstance(verdict, Pass)
    assert verdict.citations == (
        Citation("SC-1", "tests/test_feature.py::test_alpha"),
        Citation("SC-2", "tests/test_feature.py::test_beta"),
    )
    assert verdict.ci == "ci run 42: green"
    assert len(fake.calls) == 1  # exactly one judgment dispatch


async def test_sc2_uncited_criterion_rejects_without_model_call() -> None:
    """SC-2: a criterion no test cites → deterministic REJECT naming it; zero invocations."""
    fake, reg = _wire()

    verdict = await validate(_bundle(criteria=("SC-1", "SC-99")), _roster(), registry=reg)

    assert isinstance(verdict, Reject)
    assert any("SC-99 has no test citing it" in f.finding for f in verdict.findings)
    assert fake.calls == []  # the model was never invoked


async def test_sc3_red_ci_rejects_without_model_call() -> None:
    """SC-3: red CI → deterministic REJECT citing the CI evidence; zero invocations."""
    fake, reg = _wire()

    verdict = await validate(_bundle(green=False), _roster(), registry=reg)

    assert isinstance(verdict, Reject)
    ci_findings = [f for f in verdict.findings if f.check == "ci"]
    assert ci_findings and ci_findings[0].evidence == "ci run 42: RED"
    assert fake.calls == []


async def test_sc7_fix_without_red_evidence_rejects_naming_it() -> None:
    """SC-7: a fix task with no failing-before run → REJECT naming the missing evidence."""
    fake, reg = _wire()

    verdict = await validate(_bundle(is_fix=True, red_evidence=None), _roster(), registry=reg)

    assert isinstance(verdict, Reject)
    assert any(
        f.check == "red-evidence" and "without red→green evidence" in f.finding
        for f in verdict.findings
    )
    assert fake.calls == []


async def test_zero_claim_bundle_rejects_deterministically_instead_of_crashing() -> None:
    """Regression (#21 advisory run): a bundle claiming NO criteria sailed
    through the deterministic stage vacuously, burned a judgment call, then
    crashed in Pass.from_evidence ("a PASS with no citations is not a PASS").
    It must instead REJECT deterministically — free, before any model call."""
    fake, reg = _wire()

    verdict = await validate(_bundle(criteria=()), _roster(), registry=reg)

    assert isinstance(verdict, Reject)
    assert any(
        f.check == "satisfies-declaration" and "claims no success criteria" in f.finding
        for f in verdict.findings
    )
    assert fake.calls == []  # no model call for a claimless PR
