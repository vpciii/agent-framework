"""Config-driven citation scanning.

Verifies SC-3: with a custom test-citation pattern the deterministic check
finds and cites tests per that pattern (a non-Python fixture); with no
config the default Python behavior is unchanged (the existing gate and
collector tests pin that half).
"""

from __future__ import annotations

import re

from agent_framework.project import ProjectConfig
from agent_framework.providers.base import Request, Response, ToolCall
from agent_framework.providers.registry import ProviderRegistry
from agent_framework.roster import Roster
from agent_framework.validator.bundle import CIEvidence, EvidenceBundle, TaskRef
from agent_framework.validator.checks import find_citations
from agent_framework.validator.gate import validate
from agent_framework.validator.judgment import VERDICT_TOOL
from agent_framework.validator.verdict import Citation, Pass

_JS_TESTS = {
    "tests/render.test.js": (
        '// Jest suite\n'
        'it("test renders the widget", () => {\n'
        '  // SC-1: the widget renders\n'
        '  expect(render()).toBeTruthy();\n'
        '});\n'
        'it("test stops the widget", () => {\n'
        '  // SC-2\n'
        '  expect(stop()).toBe(true);\n'
        '});\n'
    )
}

_JS_PROJECT = ProjectConfig(test_pattern=r'it\("(test[^"]+)"')


def _bundle() -> EvidenceBundle:
    return EvidenceBundle(
        task=TaskRef(task_id="T-1", criteria=("SC-1", "SC-2")),
        diff="+ change",
        tests=_JS_TESTS,
        ci=CIEvidence(green=True, summary="test: SUCCESS"),
    )


def test_sc3_custom_pattern_finds_and_cites_non_python_tests() -> None:
    """SC-3: a Jest-shaped pattern locates the citing tests and names them."""
    pattern = re.compile(_JS_PROJECT.test_pattern, re.M)
    citations = find_citations(_bundle(), pattern)
    assert citations == {
        "SC-1": "tests/render.test.js::test renders the widget",
        "SC-2": "tests/render.test.js::test stops the widget",
    }


async def test_sc3_gate_threads_the_project_pattern_end_to_end() -> None:
    """SC-3: validate(..., project=...) passes deterministically on a JS
    bundle the default (Python) pattern would REJECT."""
    reg = ProviderRegistry()

    class _CleanProvider:
        async def invoke(self, request: Request, *, model: str) -> Response:
            return Response(
                text="",
                tool_calls=(
                    ToolCall(VERDICT_TOOL.name, {"defect_found": False, "findings": []}),
                ),
            )

    reg.register("fake", _CleanProvider())
    roster = Roster.from_dict(
        {"roles": {"validator": {"provider": "fake", "model": "m"}}}
    )

    # Default pattern: no `def test_` in a JS file → deterministic REJECT.
    default_verdict = await validate(_bundle(), roster, registry=reg)
    assert not isinstance(default_verdict, Pass)

    # Project pattern: citations found → judgment → cited PASS.
    verdict = await validate(_bundle(), roster, registry=reg, project=_JS_PROJECT)
    assert isinstance(verdict, Pass)
    assert (
        Citation("SC-1", "tests/render.test.js::test renders the widget")
        in verdict.citations
    )
