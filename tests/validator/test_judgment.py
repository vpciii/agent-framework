"""The judgment stage.

Verifies:
- SC-4: a defect reported through return_verdict is carried into the
  judgment verbatim (finding + evidence).
- SC-5: the request goes through the roster's `validator` role in an
  isolated registry, and the prompt carries the refutation checklist.
Plus the fail-loud paths: no tool call, malformed findings, and an
unevidenced defect all raise JudgmentFormatError.
"""

from __future__ import annotations

from typing import Any

import pytest

from agent_framework.errors import JudgmentFormatError
from agent_framework.providers.base import Request, Response, ToolCall
from agent_framework.providers.registry import ProviderRegistry
from agent_framework.roster import Roster
from agent_framework.validator.bundle import CIEvidence, EvidenceBundle, TaskRef
from agent_framework.validator.judgment import REFUTATION_CHECKLIST, VERDICT_TOOL, judge
from agent_framework.validator.verdict import Finding


class _FakeProvider:
    """Records its calls and returns a canned Response."""

    def __init__(self, response: Response) -> None:
        self.response = response
        self.calls: list[tuple[Request, str]] = []

    async def invoke(self, request: Request, *, model: str) -> Response:
        self.calls.append((request, model))
        return self.response


def _roster() -> Roster:
    return Roster.from_dict(
        {"roles": {"validator": {"provider": "fake", "model": "judge-1"}}}
    )


def _bundle() -> EvidenceBundle:
    return EvidenceBundle(
        task=TaskRef(task_id="T-9", criteria=("SC-1", "SC-2")),
        diff="--- a/x.py\n+++ b/x.py\n+def f(): return 1",
        tests={"tests/test_x.py": '"""Cites SC-1, SC-2."""\ndef test_a(): ...'},
        ci=CIEvidence(green=True, summary="ci run 42: all green"),
    )


def _wire(response: Response) -> tuple[_FakeProvider, ProviderRegistry]:
    reg = ProviderRegistry()
    fake = _FakeProvider(response)
    reg.register("fake", fake)
    return fake, reg


def _verdict_response(arguments: dict[str, Any]) -> Response:
    return Response(text="", tool_calls=(ToolCall(VERDICT_TOOL.name, arguments),))


async def test_sc4_defect_from_return_verdict_is_carried_verbatim() -> None:
    """SC-4: the model's finding + evidence arrive in the Judgment untouched."""
    reported = {
        "defect_found": True,
        "findings": [
            {
                "check": "test-honesty",
                "finding": "test_a asserts nothing about f()",
                "evidence": "tests/test_x.py::test_a has no assert",
            }
        ],
    }
    _, reg = _wire(_verdict_response(reported))

    judgment = await judge(_bundle(), _roster(), registry=reg)

    assert judgment.defect_found is True
    assert judgment.findings == (
        Finding(
            check="test-honesty",
            finding="test_a asserts nothing about f()",
            evidence="tests/test_x.py::test_a has no assert",
        ),
    )


async def test_sc5_judgment_dispatches_through_validator_role_with_checklist() -> None:
    """SC-5: roster's validator role is used; the prompt carries the refutation checklist."""
    fake, reg = _wire(_verdict_response({"defect_found": False, "findings": []}))

    judgment = await judge(_bundle(), _roster(), registry=reg)

    assert judgment.defect_found is False
    [(request, model)] = fake.calls
    assert model == "judge-1"  # resolved via the roster's validator binding
    assert REFUTATION_CHECKLIST in request.prompt
    assert request.tools == (VERDICT_TOOL,)  # exactly one tool: return_verdict


async def test_no_tool_call_raises_typed_error() -> None:
    _, reg = _wire(Response(text="LGTM, ship it"))
    with pytest.raises(JudgmentFormatError, match="did not call return_verdict"):
        await judge(_bundle(), _roster(), registry=reg)


async def test_defect_without_findings_raises_typed_error() -> None:
    _, reg = _wire(_verdict_response({"defect_found": True, "findings": []}))
    with pytest.raises(JudgmentFormatError, match="cite, don't assert"):
        await judge(_bundle(), _roster(), registry=reg)


async def test_malformed_finding_raises_typed_error() -> None:
    _, reg = _wire(
        _verdict_response({"defect_found": True, "findings": [{"check": "x"}]})
    )
    with pytest.raises(JudgmentFormatError, match="missing field"):
        await judge(_bundle(), _roster(), registry=reg)
