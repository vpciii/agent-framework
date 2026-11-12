"""The judgment checks conformance only (specs/conformance-only-judgment, ADR 0008).

Each test's docstring names the one criterion it verifies.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from agent_framework.errors import JudgmentFormatError, NoVerdictError
from agent_framework.providers.base import Request, Response, ToolCall
from agent_framework.providers.registry import ProviderRegistry
from agent_framework.roster import Roster
from agent_framework.validator import judgment
from agent_framework.validator.bundle import CIEvidence, Contract, EvidenceBundle, TaskRef
from agent_framework.validator.judgment import (
    CHECK_NAMES,
    REFUTATION_CHECKLIST,
    VERDICT_TOOL,
    build_request,
    judge,
)

DIFF = "+def collect() -> int:\n+    return 1\n"
TEST_SOURCE = 'def test_a() -> None:\n    """SC-1."""\n    assert collect() == 1\n'


def _bundle() -> EvidenceBundle:
    return EvidenceBundle(
        task=TaskRef(task_id="T-2", criteria=("SC-1",)),
        diff=DIFF,
        tests={"tests/test_x.py": TEST_SOURCE},
        ci=CIEvidence(green=True, summary="ci: SUCCESS"),
        contract=Contract(
            spec_slug="demo",
            criterion_texts={"SC-1": "- **SC-1** — The collector returns one."},
            task_block="### [ ] T-2 — Collect",
            cited_tests={"SC-1": ("tests/test_x.py::test_a",)},
            ref="84a707e",
        ),
    )


def _instructions(request: Request) -> str:
    """The request without its data: what the model is told, not what it is shown."""
    before, _, rest = request.prompt.partition("===== BEGIN DATA =====")
    _, _, after = rest.rpartition("===== END DATA =====")
    return before + after


class _Fake:
    def __init__(self, response: Response) -> None:
        self.response = response

    async def invoke(self, request: Request, *, model: str) -> Response:
        return self.response


def _wire(*findings: dict[str, Any]) -> tuple[ProviderRegistry, Roster]:
    arguments = {"defect_found": True, "findings": list(findings)}
    registry = ProviderRegistry()
    registry.register(
        "fake", _Fake(Response(text="", tool_calls=(ToolCall(VERDICT_TOOL.name, arguments),)))
    )
    roster = Roster.from_dict({"roles": {"validator": {"provider": "fake", "model": "judge-9"}}})
    return registry, roster


def test_sc1_the_request_carries_three_checklist_items_and_asks_for_no_edge_case() -> None:
    """SC-1: the request carries the three-item checklist — test honesty,
    spec conformance, criteria integrity — and nowhere asks for an edge case."""
    request = build_request(_bundle())
    told = _instructions(request)

    assert REFUTATION_CHECKLIST in told
    assert re.findall(r"^(\d+)\. (\w+ \w+)", REFUTATION_CHECKLIST, re.MULTILINE) == [
        ("1", "Test honesty"), ("2", "Spec conformance"), ("3", "Criteria integrity"),
    ]
    assert "edge case" not in told.lower() and "edge-case" not in told.lower()
    assert "edge" not in VERDICT_TOOL.description.lower()


def test_sc2_the_request_says_only_a_departure_from_the_contract_is_a_defect() -> None:
    """SC-2: the instructions state the scope — judge against the task and
    the claimed criteria; a possible bug they do not speak to is not a defect."""
    told = _instructions(build_request(_bundle()))
    scope: str = judgment.CONFORMANCE_SCOPE

    assert scope in told
    said = " ".join(scope.split())
    assert "only against the task and criteria" in said
    assert "not a defect for this verdict" in said


def test_sc3_the_schema_allows_only_the_three_check_names() -> None:
    """SC-3: the verdict tool's schema restricts `check` to the three names."""
    item = VERDICT_TOOL.parameters["properties"]["findings"]["items"]

    assert item["properties"]["check"]["enum"] == list(CHECK_NAMES) == [
        "test-honesty", "spec-conformance", "criteria-integrity",
    ]


async def test_sc3_a_finding_filed_as_an_edge_case_is_malformed_not_a_verdict() -> None:
    """SC-3: a response whose finding names `edge-case` is reported as
    malformed — for a provider that does not enforce the schema — and is
    neither a REJECT nor "could not judge for want of evidence"."""
    registry, roster = _wire({
        "check": "edge-case", "finding": "an empty input is not handled",
        "evidence": "see the quote", "quotes": ["def collect() -> int:"],
    })

    with pytest.raises(JudgmentFormatError, match="check") as raised:
        await judge(_bundle(), roster, registry=registry)

    assert not isinstance(raised.value, NoVerdictError)
