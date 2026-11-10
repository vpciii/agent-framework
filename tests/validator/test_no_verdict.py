"""A judgment that could not be made (specs/judgment-reliability).

Each test's docstring names the one criterion it verifies.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from agent_framework.errors import JudgmentFormatError, NoVerdictError
from agent_framework.providers.base import Request, Response, ToolCall, Usage
from agent_framework.providers.registry import ProviderRegistry
from agent_framework.roster import Roster
from agent_framework.validator import __main__ as gate_cli
from agent_framework.validator.bundle import CIEvidence, EvidenceBundle, TaskRef
from agent_framework.validator.judgment import VERDICT_TOOL, judge
from agent_framework.validator.verdict import Finding, Pass, Reject, Verdict


class _Fake:
    def __init__(self, response: Response) -> None:
        self.response = response
        self.requests: list[Request] = []

    async def invoke(self, request: Request, *, model: str) -> Response:
        self.requests.append(request)
        return self.response


def _wire(response: Response) -> tuple[_Fake, ProviderRegistry, Roster]:
    fake, registry = _Fake(response), ProviderRegistry()
    registry.register("fake", fake)
    roster = Roster.from_dict({"roles": {"validator": {"provider": "fake", "model": "judge-9"}}})
    return fake, registry, roster


def _bundle() -> EvidenceBundle:
    return EvidenceBundle(
        task=TaskRef(task_id="T-9", criteria=("SC-1",)),
        diff="+ x",
        tests={"tests/test_x.py": 'def test_a() -> None:\n    """SC-1."""\n'},
        ci=CIEvidence(green=True, summary="ci: SUCCESS"),
    )


_CLEAN = Response(
    text="", tool_calls=(ToolCall(VERDICT_TOOL.name, {"defect_found": False, "findings": []}),),
    stop="complete", stop_detail="STOP", usage=Usage(input_tokens=1234, output_tokens=56),
)


async def test_sc4_the_judgment_requires_its_verdict_tool() -> None:
    """SC-4 here: the request names return_verdict as its required answer."""
    fake, registry, roster = _wire(_CLEAN)

    await judge(_bundle(), roster, registry=registry)

    [request] = fake.requests
    assert request.require_tool == VERDICT_TOOL.name == "return_verdict"


@pytest.mark.parametrize(
    ("response", "reason", "stop_word"),
    [
        (Response(text='{"defect_fo', stop="truncated", stop_detail="MAX_TOKENS"),
         "truncated", "MAX_TOKENS"),
        (Response(text="", stop="refused", stop_detail="refusal"), "refused", "refusal"),
        (Response(text="LGTM, ship it", stop="complete", stop_detail="end_turn"),
         "no-answer", "end_turn"),
    ],
)
async def test_sc4_truncated_refused_and_unanswered_are_each_named_never_a_verdict(
    response: Response, reason: str, stop_word: str
) -> None:
    """SC-4 here: each of the three raises the typed error, saying which
    and carrying the provider's own stop word; none becomes a verdict."""
    _, registry, roster = _wire(response)

    with pytest.raises(NoVerdictError) as raised:
        await judge(_bundle(), roster, registry=registry)

    assert raised.value.reason == reason
    assert reason in str(raised.value) and stop_word in str(raised.value)
    assert isinstance(raised.value, JudgmentFormatError)  # existing handlers still catch it


async def test_sc4_a_truncated_response_is_not_trusted_even_with_a_call() -> None:
    """SC-4 here: a verdict call inside a cut-off response is not a verdict."""
    cut_off = Response(
        text="", stop="truncated", stop_detail="max_tokens",
        tool_calls=(ToolCall(VERDICT_TOOL.name, {"defect_found": False, "findings": []}),),
    )
    _, registry, roster = _wire(cut_off)

    with pytest.raises(NoVerdictError, match="truncated"):
        await judge(_bundle(), roster, registry=registry)


def _run_cli(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, outcome: Verdict | Exception
) -> int:
    (tmp_path / "agent-framework.toml").write_text(
        '[roles]\nvalidator = { provider = "fake", model = "judge-9" }\n', encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(gate_cli, "collect_bundle", lambda *a, **k: _bundle())

    async def validate(*args: Any, **kwargs: Any) -> Verdict:
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(gate_cli, "validate", validate)
    return gate_cli.main(["7"])


def test_sc5_could_not_judge_prints_its_reason_and_exits_three(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """SC-5 here: a JSON object naming the reason, exit 3, no traceback."""
    code = _run_cli(
        monkeypatch, tmp_path,
        NoVerdictError("truncated", "the judgment was truncated (provider said MAX_TOKENS)"),
    )

    out, err = capsys.readouterr()
    assert code == 3
    assert json.loads(out) == {
        "verdict": "none", "reason": "truncated",
        "detail": "the judgment was truncated (provider said MAX_TOKENS)",
    }
    assert "Traceback" not in err


def test_sc5_a_malformed_judgment_is_also_no_verdict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """SC-5 here: the older format error is reported the same way."""
    code = _run_cli(monkeypatch, tmp_path, JudgmentFormatError("finding missing field 'check'"))

    assert code == 3
    assert json.loads(capsys.readouterr().out)["reason"] == "malformed"


def test_sc5_a_provider_failure_is_no_verdict_not_a_reject(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """SC-5 here: a rate limit or outage is "could not judge", exit 3."""
    from agent_framework.errors import ProviderError

    code = _run_cli(monkeypatch, tmp_path, ProviderError("RateLimitError: 429 quota exhausted"))

    out, err = capsys.readouterr()
    assert code == 3
    assert json.loads(out)["reason"] == "provider-error"
    assert "429" in json.loads(out)["detail"] and "Traceback" not in err


def test_sc5_pass_and_reject_keep_their_codes_and_their_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """SC-5 here: PASS exits 0 and REJECT 1, with the verdict JSON unchanged."""
    from agent_framework.validator.verdict import Citation

    passed = Pass(task_id="T-9", citations=(Citation("SC-1", "tests/test_x.py::test_a"),),
                  ci="ci: SUCCESS")
    assert _run_cli(monkeypatch, tmp_path, passed) == 0
    assert set(json.loads(capsys.readouterr().out)) == {"verdict", "task_id", "citations", "ci"}

    rejected = Reject(task_id="T-9", findings=(Finding("ci", "red", "ci: FAILURE"),))
    assert _run_cli(monkeypatch, tmp_path, rejected) == 1
    assert set(json.loads(capsys.readouterr().out)) == {"verdict", "task_id", "findings"}


async def test_sc6_each_judgment_logs_model_stop_reason_and_token_counts(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SC-6 here: one line carrying the model, the stop reason and both counts."""
    _, registry, roster = _wire(_CLEAN)

    with caplog.at_level(logging.INFO, logger="agent_framework.validator"):
        await judge(_bundle(), roster, registry=registry)

    [line] = [r.getMessage() for r in caplog.records if "judgment" in r.getMessage()]
    for expected in ("T-9", "judge-9", "complete", "STOP", "1234", "56"):
        assert expected in line


async def test_sc6_a_failed_judgment_is_logged_before_it_raises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SC-6 here: the line is written for a refused judgment too."""
    _, registry, roster = _wire(Response(text="", stop="refused", stop_detail="SAFETY"))

    with caplog.at_level(logging.INFO, logger="agent_framework.validator"), \
            pytest.raises(NoVerdictError):
        await judge(_bundle(), roster, registry=registry)

    assert any("refused" in r.getMessage() and "SAFETY" in r.getMessage() for r in caplog.records)
