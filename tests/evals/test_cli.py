"""The eval's command (specs/validator-eval-set).

Each test's docstring names the one criterion it verifies. No model is
called and no provider key is set anywhere in this file.
"""

from __future__ import annotations

import importlib.metadata
import json
import logging
from pathlib import Path
from typing import Any

import pytest

from agent_framework.errors import ProviderError
from agent_framework.evals import __main__ as eval_cli
from agent_framework.evals.case import EvalCase, Provenance, dump_case, set_fingerprint
from agent_framework.evals.scorecard import instructions_fingerprint, result_from_json
from agent_framework.providers.base import Request, Response, ToolCall, Usage
from agent_framework.providers.registry import register_provider
from agent_framework.validator.bundle import CIEvidence, EvidenceBundle, TaskRef
from agent_framework.validator.judgment import VERDICT_TOOL

TEST_SOURCE = 'def test_a() -> None:\n    """SC-1."""\n    assert collect() == 1\n'
DIFF = "+def test_a() -> None:\n+    assert collect() == 1\n"

_ACCEPTED = EvalCase(
    id="pr-1", kind="accepted", expected="pass", reason="Merged.",
    provenance=Provenance(repo="o/r", pr=1, head="abc", frozen="2026-11-10"),
    bundle=EvidenceBundle(
        task=TaskRef(task_id="T-1", criteria=("SC-1",)), diff=DIFF,
        tests={"tests/test_x.py": TEST_SOURCE}, ci=CIEvidence(green=True, summary="ci: SUCCESS"),
    ),
)
_SEEDED = {
    "id": "pr-1--tautology", "kind": "seeded-defect", "base": "pr-1",
    "expected": "reject", "check": "test-honesty", "reason": "A tautology.",
    "edit": [
        {"in": "diff", "replace": "+    assert collect() == 1", "with": "+    assert 1 == 1 + 0"},
        {"in": "tests/test_x.py", "replace": "    assert collect() == 1",
         "with": "    assert 1 == 1 + 0"},
    ],
}


class _Fake:
    def __init__(self, *answers: Response) -> None:
        self.answers = list(answers)
        self.requests: list[Request] = []

    async def invoke(self, request: Request, *, model: str) -> Response:
        self.requests.append(request)
        return self.answers.pop(0)


def _answer(defect_found: bool, *findings: dict[str, Any]) -> Response:
    arguments = {"defect_found": defect_found, "findings": list(findings)}
    return Response(text="", tool_calls=(ToolCall(VERDICT_TOOL.name, arguments),),
                    stop="complete", stop_detail="STOP",
                    usage=Usage(input_tokens=1000, output_tokens=100))


CAUGHT = _answer(True, {"check": "test-honesty", "finding": "a tautology",
                        "evidence": "see the quote", "quotes": ["assert 1 == 1 + 0"]})


@pytest.fixture
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A case set of two, a roster naming a fake provider, a fixed date —
    and no provider key in the environment."""
    for key in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    cases = tmp_path / "evals" / "cases"
    cases.mkdir(parents=True)
    (cases / "pr-1.json").write_text(dump_case(_ACCEPTED), encoding="utf-8")
    (cases / "pr-1--tautology.json").write_text(json.dumps(_SEEDED), encoding="utf-8")
    (tmp_path / "roster.toml").write_text(
        '[roles]\nvalidator = { provider = "fake-eval", model = "judge-9" }\n', encoding="utf-8"
    )
    monkeypatch.setattr(eval_cli, "_today", lambda: "2026-11-10")
    return tmp_path


def _run(root: Path, *extra: str) -> int:
    return eval_cli.main(["run", "--cases", str(root / "evals" / "cases"),
                          "--roster", str(root / "roster.toml"), *extra])


def test_sc10_a_whole_run_needs_no_provider_key(
    setup: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """SC-10: with every provider key unset, the command judges the set
    through a fake provider, prints the scorecard and writes the result."""
    register_provider("fake-eval", _Fake(_answer(False), CAUGHT))

    code = _run(setup)

    out, err = capsys.readouterr()
    assert code == 0
    assert "passed            1 of 1 judged (100%)" in out
    assert "caught            1 of 1 judged (100%)" in out
    # One line per judgment as it lands, and the gate's own log line, on stderr.
    assert "pr-1 " in err and "pr-1--tautology" in err and "caught" in err
    assert "model=judge-9" in err

    written = setup / "evals" / "results" / "2026-11-10-judge-9.json"
    result = result_from_json(written.read_text(encoding="utf-8"))
    assert (result.model, result.date, result.runs) == ("fake-eval:judge-9", "2026-11-10", 1)
    assert result.instructions == instructions_fingerprint()
    assert result.case_set == set_fingerprint(setup / "evals" / "cases")
    assert [(j.case, j.cls, j.input_tokens) for j in result.judgments] == [
        ("pr-1", "passed", 1000), ("pr-1--tautology", "caught", 1000),
    ]
    assert not logging.getLogger("agent_framework").handlers  # the handler is the CLI's own


def test_sc5_only_and_runs_choose_what_is_judged(
    setup: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """SC-5 here: `--only` names the cases, `--runs` how often, `--out` where."""
    fake = _Fake(CAUGHT, CAUGHT)
    register_provider("fake-eval", fake)
    out_file = setup / "elsewhere.json"

    code = _run(setup, "--only", "pr-1--tautology", "--runs", "2", "--out", str(out_file))

    capsys.readouterr()
    assert code == 0 and len(fake.requests) == 2
    result = result_from_json(out_file.read_text(encoding="utf-8"))
    assert [(j.case, j.run) for j in result.judgments] == [
        ("pr-1--tautology", 1), ("pr-1--tautology", 2),
    ]
    assert result.runs == 2


@pytest.mark.parametrize(
    ("extra", "says"),
    [
        (("--only", "pr-99"), "pr-99"),
        (("--runs", "0"), "--runs"),
    ],
)
def test_sc5_a_run_that_cannot_start_says_why_and_judges_nothing(
    setup: Path, capsys: pytest.CaptureFixture[str], extra: tuple[str, ...], says: str
) -> None:
    """SC-5 here: an unknown case or a senseless count is exit 2 before any
    model call."""
    fake = _Fake()
    register_provider("fake-eval", fake)

    code = _run(setup, *extra)

    assert code == 2 and says in capsys.readouterr().err and not fake.requests


def test_sc5_an_empty_or_malformed_set_is_refused(
    setup: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """SC-5 here: no cases, or a case that does not load, stops the run
    naming the problem — no model call, no result file."""
    register_provider("fake-eval", _Fake())
    cases = setup / "evals" / "cases"
    (cases / "pr-2.json").write_text("{ not json", encoding="utf-8")

    assert _run(setup) == 2
    assert "pr-2.json" in capsys.readouterr().err

    for path in cases.glob("*.json"):
        path.unlink()
    assert _run(setup) == 2
    assert "no eval cases" in capsys.readouterr().err
    assert not (setup / "evals" / "results").exists()


def test_sc5_a_recorded_result_is_never_overwritten(
    setup: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """SC-5 here: a second run on the same day does not replace the first's
    file — and says so before spending a model call."""
    register_provider("fake-eval", _Fake(_answer(False), CAUGHT))
    assert _run(setup) == 0
    fake = _Fake()
    register_provider("fake-eval", fake)

    code = _run(setup)

    assert code == 2 and "--out" in capsys.readouterr().err and not fake.requests


def test_sc6_the_command_shows_why_a_case_could_not_be_judged(
    setup: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """SC-6 here: on stderr, beside the could-not-judge line, the provider's
    own message — and the run still completes and writes its result."""

    class _Refusing:
        async def invoke(self, request: Request, *, model: str) -> Response:
            raise ProviderError("ClientError: 400 API_KEY_INVALID")

    register_provider("fake-eval", _Refusing())

    code = _run(setup)

    err = capsys.readouterr().err
    assert code == 0
    assert "judgment pr-1: provider error — ClientError: 400 API_KEY_INVALID" in err
    assert "could-not-judge (provider-error)" in err


def test_sc9_compare_names_what_changed_and_refuses_different_case_sets(
    setup: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """SC-9 here: from the command line — the changed case on comparable
    results; exit 2 and "not comparable" when the case sets differ."""
    first, second, third = (setup / f"{n}.json" for n in ("first", "second", "third"))
    register_provider("fake-eval", _Fake(_answer(False), CAUGHT))
    assert _run(setup, "--out", str(first)) == 0
    register_provider("fake-eval", _Fake(_answer(False), _answer(False)))
    assert _run(setup, "--out", str(second)) == 0
    capsys.readouterr()

    assert eval_cli.main(["compare", str(first), str(second)]) == 0
    assert "pr-1--tautology: caught → missed" in capsys.readouterr().out

    (setup / "evals" / "cases" / "pr-1--tautology.json").unlink()
    register_provider("fake-eval", _Fake(_answer(False)))
    assert _run(setup, "--out", str(third)) == 0
    capsys.readouterr()

    assert eval_cli.main(["compare", str(first), str(third)]) == 2
    assert "not comparable" in capsys.readouterr().out

    third.write_text("{ not a result", encoding="utf-8")
    assert eval_cli.main(["compare", str(first), str(third)]) == 2
    assert "third.json" in capsys.readouterr().err


def test_sc10_the_command_is_installed_as_agent_framework_eval() -> None:
    """SC-10 here: the console entry point is the same `main`."""
    [entry] = [ep for ep in importlib.metadata.entry_points(group="console_scripts")
               if ep.name == "agent-framework-eval"]

    assert entry.value == "agent_framework.evals.__main__:main"
    assert entry.load() is eval_cli.main
