"""The effort a judgment ran at is on record (specs/role-effort).

Each test's docstring names the one criterion it verifies. No model is
called and no provider key is set.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from agent_framework.evals import __main__ as eval_cli
from agent_framework.evals.case import EvalCase, Provenance, dump_case
from agent_framework.evals.scorecard import render, result_from_json
from agent_framework.providers.base import Request, Response, ToolCall, Usage
from agent_framework.providers.registry import ProviderRegistry, register_provider
from agent_framework.roster import Roster
from agent_framework.validator.bundle import CIEvidence, EvidenceBundle, TaskRef
from agent_framework.validator.judgment import VERDICT_TOOL, judge

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "evals" / "validator" / "results" / (
    "2026-11-12-gemini-3.8-flash-conformance-only.json"
)

_BUNDLE = EvidenceBundle(
    task=TaskRef(task_id="T-1", criteria=("SC-1",)),
    diff="+def test_a() -> None:\n+    assert collect() == 1\n",
    tests={"tests/test_x.py": 'def test_a() -> None:\n    """SC-1."""\n    assert collect() == 1\n'},
    ci=CIEvidence(green=True, summary="ci: SUCCESS"),
)
_PASS = Response(
    text="", tool_calls=(ToolCall(VERDICT_TOOL.name, {"defect_found": False, "findings": []}),),
    stop="complete", stop_detail="STOP", usage=Usage(input_tokens=1000, output_tokens=100),
)


class _Fake:
    def __init__(self) -> None:
        self.requests: list[Request] = []

    async def invoke(self, request: Request, *, model: str) -> Response:
        self.requests.append(request)
        return _PASS


def _binding(**extra: str) -> dict[str, Any]:
    return {"roles": {"validator": {"provider": "fake-effort", "model": "judge-9"} | extra}}


@pytest.mark.parametrize(("extra", "logged"), [({"effort": "high"}, "effort=high"),
                                               ({}, "effort=default")])
async def test_sc7_a_judgment_logs_the_effort_it_ran_at(
    extra: dict[str, str], logged: str, caplog: pytest.LogCaptureFixture
) -> None:
    """SC-7: the judgment's log line names the effort, or says it is the
    provider's default."""
    registry = ProviderRegistry()
    registry.register("fake-effort", _Fake())

    with caplog.at_level(logging.INFO, logger="agent_framework.validator"):
        await judge(_BUNDLE, Roster.from_dict(_binding(**extra)), registry=registry)

    [line] = [r.getMessage() for r in caplog.records if r.getMessage().startswith("judgment ")]
    assert "model=judge-9" in line and logged in line


def test_sc7_an_eval_result_records_the_effort_and_the_scorecard_shows_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SC-7: a run through a validator bound with effort `high` sends that
    effort, writes a result that records it and prints a scorecard that
    shows it."""
    cases = tmp_path / "evals" / "cases"
    cases.mkdir(parents=True)
    case = EvalCase(
        id="pr-1", kind="accepted", expected="pass", reason="Merged.",
        provenance=Provenance(repo="o/r", pr=1, head="abc", frozen="2026-11-12"),
        bundle=_BUNDLE,
    )
    (cases / "pr-1.json").write_text(dump_case(case), encoding="utf-8")
    roster = tmp_path / "roster.toml"
    roster.write_text(
        '[roles]\nvalidator = { provider = "fake-effort", model = "judge-9", effort = "high" }\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(eval_cli, "_today", lambda: "2026-11-12")
    fake = _Fake()
    register_provider("fake-effort", fake)
    out_file = tmp_path / "result.json"

    code = eval_cli.main(["run", "--cases", str(cases), "--roster", str(roster),
                          "--out", str(out_file)])

    out = capsys.readouterr().out
    assert code == 0
    assert [r.effort for r in fake.requests] == ["high"]
    assert json.loads(out_file.read_text(encoding="utf-8"))["effort"] == "high"
    assert "effort high" in out.splitlines()[1]
    stored = result_from_json(out_file.read_text(encoding="utf-8"))
    assert "effort high" in render(stored).splitlines()[1]


def test_sc7_a_result_written_before_the_change_shows_the_providers_default() -> None:
    """SC-7: a result with no record of an effort loads, and its scorecard
    says the judgment ran at the provider's default."""
    text = BASELINE.read_text(encoding="utf-8")
    assert '"effort"' not in text[:400]

    result = result_from_json(text)

    assert len(result.judgments) == 36
    assert "effort provider default" in render(result).splitlines()[1]
