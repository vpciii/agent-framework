"""A stored eval result is read against today's answers (specs/eval-rescore).

Each test's docstring names the one criterion it verifies. No model is
called and no provider key is set anywhere in this file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agent_framework.evals import __main__ as eval_cli
from agent_framework.evals import case as case_module
from agent_framework.evals.case import EvalCase, Provenance, dump_case, load_set
from agent_framework.evals.scorecard import result_from_json
from agent_framework.providers.base import Request, Response, ToolCall, Usage
from agent_framework.providers.registry import register_provider
from agent_framework.validator.bundle import CIEvidence, EvidenceBundle, TaskRef
from agent_framework.validator.judgment import VERDICT_TOOL, build_request

ROOT = Path(__file__).resolve().parents[2]
REPO_RESULTS = ROOT / "evals" / "validator" / "results"
# What the repository's cases sent the judgment at each of the three runs
# recorded by 2026-11-12, as the case files stood at each run's commit.
RECORDED_INPUTS = "1f427ab0b735"

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
_SEEDED: dict[str, Any] = {
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


def _answer(*quotes: str) -> Response:
    """A PASS, or with quotes a REJECT resting on them under test-honesty."""
    findings = [{"check": "test-honesty", "finding": "the test checks too little",
                 "evidence": "see the quote", "quotes": list(quotes)}] if quotes else []
    arguments = {"defect_found": bool(quotes), "findings": findings}
    return Response(text="", tool_calls=(ToolCall(VERDICT_TOOL.name, arguments),),
                    stop="complete", stop_detail="STOP",
                    usage=Usage(input_tokens=1000, output_tokens=100))


PASS = _answer()
REJECT_ACCEPTED = _answer("assert collect() == 1")
REJECT_SEEDED = _answer("assert 1 == 1 + 0")


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A case set of two, a roster naming a fake provider, a fixed date."""
    for key in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    cases = tmp_path / "evals" / "cases"
    cases.mkdir(parents=True)
    (cases / "pr-1.json").write_text(dump_case(_ACCEPTED), encoding="utf-8")
    (cases / "pr-1--tautology.json").write_text(json.dumps(_SEEDED), encoding="utf-8")
    (tmp_path / "roster.toml").write_text(
        '[roles]\nvalidator = { provider = "fake-rescore", model = "judge-9" }\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(eval_cli, "_today", lambda: "2026-11-12")
    return tmp_path


def _cases(root: Path) -> Path:
    return root / "evals" / "cases"


def _run(root: Path, out: str, *answers: Response) -> Path:
    fake = _Fake(*answers)
    register_provider("fake-rescore", fake)
    path = root / out
    code = eval_cli.main(["run", "--cases", str(_cases(root)),
                          "--roster", str(root / "roster.toml"), "--out", str(path)])
    assert code == 0
    return path


def _edit(path: Path, **changes: Any) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    for key, value in changes.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    path.write_text(json.dumps(data), encoding="utf-8")


def _correct_the_answer(root: Path) -> None:
    """A human rules that the accepted case holds a real defect."""
    _edit(_cases(root) / "pr-1.json", expected="reject", check="test-honesty",
          reason="Merged. Answer corrected: the test checks too little.")


def _inputs(directory: Path) -> str:
    fingerprint: str = case_module.inputs_fingerprint(directory)
    return fingerprint


# ---- SC-1: the inputs fingerprint ------------------------------------------


def test_sc1_the_inputs_fingerprint_moves_with_what_is_sent_and_not_with_the_answers(
    root: Path,
) -> None:
    """SC-1: unchanged when an answer, a checklist item or a reason changes;
    changed when a bundle or a seeded edit changes, or a case is added or
    removed."""
    cases = _cases(root)
    before = _inputs(cases)

    _correct_the_answer(root)
    _edit(cases / "pr-1--tautology.json", check="spec-conformance", reason="Reworded.")
    assert _inputs(cases) == before

    accepted = json.loads((cases / "pr-1.json").read_text(encoding="utf-8"))
    accepted["bundle"]["ci"]["summary"] = "ci: SUCCESS (rerun)"
    (cases / "pr-1.json").write_text(json.dumps(accepted), encoding="utf-8")
    bundle_changed = _inputs(cases)
    assert bundle_changed != before

    _edit(cases / "pr-1--tautology.json", edit=[
        {"in": "diff", "replace": "+    assert collect() == 1", "with": "+    assert True"},
    ])
    edit_changed = _inputs(cases)
    assert edit_changed not in (before, bundle_changed)

    another = json.loads((cases / "pr-1.json").read_text(encoding="utf-8")) | {"id": "pr-2"}
    (cases / "pr-2.json").write_text(json.dumps(another), encoding="utf-8")
    added = _inputs(cases)
    assert added not in (before, bundle_changed, edit_changed)

    (cases / "pr-2.json").unlink()
    assert _inputs(cases) == edit_changed


def test_sc1_a_new_result_carries_the_inputs_fingerprint(root: Path) -> None:
    """SC-1: a run records what its cases sent."""
    written = _run(root, "first.json", PASS, REJECT_SEEDED)

    assert json.loads(written.read_text(encoding="utf-8"))["inputs"] == _inputs(_cases(root))


# ---- SC-2, SC-3: show ------------------------------------------------------


def test_sc2_show_classes_a_stored_result_against_the_answers_on_disk(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """SC-2: a case rejected when it was expected to pass, whose answer has
    since been corrected to `reject`, is shown as caught, counted so, and
    named as re-scored."""
    stored = _run(root, "first.json", REJECT_ACCEPTED, REJECT_SEEDED)
    assert result_from_json(stored.read_text(encoding="utf-8")).judgments[0].cls == (
        "wrongly-rejected"
    )
    capsys.readouterr()

    assert eval_cli.main(["show", str(stored), "--cases", str(_cases(root))]) == 0
    as_recorded = capsys.readouterr().out
    assert "wrongly rejected  1 of 1 judged (100%)" in as_recorded
    assert "re-scored" not in as_recorded.lower()

    _correct_the_answer(root)
    assert eval_cli.main(["show", str(stored), "--cases", str(_cases(root))]) == 0
    out = capsys.readouterr().out

    assert "Accepted work (expected PASS): 0 judgments" in out
    assert "Defects (expected REJECT): 2 judgments" in out
    assert "caught            2 of 2 judged (100%)" in out
    assert "Wrongly rejected" not in out
    [note] = [line for line in out.splitlines() if "re-scored" in line.lower()]
    assert "pr-1" in note and "pr-1--tautology" not in note


def test_sc3_show_refuses_a_result_whose_cases_have_changed(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """SC-3: when what the cases send is not what the result judged, `show`
    exits 2 and says the cases have changed since the run."""
    stored = _run(root, "first.json", PASS, REJECT_SEEDED)
    accepted = json.loads((_cases(root) / "pr-1.json").read_text(encoding="utf-8"))
    accepted["bundle"]["diff"] = DIFF + "+# a later commit\n"
    (_cases(root) / "pr-1.json").write_text(json.dumps(accepted), encoding="utf-8")
    capsys.readouterr()

    assert eval_cli.main(["show", str(stored), "--cases", str(_cases(root))]) == 2

    out, err = capsys.readouterr()
    assert out == "" and "cases have changed since the run" in err


# ---- SC-4: compare ---------------------------------------------------------


def test_sc4_compare_classes_both_results_against_the_answers_on_disk(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """SC-4: two results on the same inputs and different case-set
    fingerprints are compared, each classed against today's answers; two on
    different inputs are refused with exit 2."""
    first = _run(root, "first.json", REJECT_ACCEPTED, REJECT_SEEDED)
    _correct_the_answer(root)
    second = _run(root, "second.json", PASS, REJECT_SEEDED)
    was, now = (result_from_json(p.read_text(encoding="utf-8")) for p in (first, second))
    assert was.case_set != now.case_set and was.inputs == now.inputs
    capsys.readouterr()

    code = eval_cli.main(["compare", str(first), str(second), "--cases", str(_cases(root))])

    out = capsys.readouterr().out
    assert code == 0 and "not comparable" not in out
    # Recorded as wrongly-rejected then missed; under today's answer the
    # first run caught the defect and the second missed it.
    assert "pr-1: caught → missed" in out
    assert "wrongly-rejected" not in out

    (_cases(root) / "pr-1--tautology.json").unlink()
    third = _run(root, "third.json", PASS)
    capsys.readouterr()
    assert eval_cli.main(
        ["compare", str(first), str(third), "--cases", str(_cases(root))]
    ) == 2
    assert "not comparable" in capsys.readouterr().out


# ---- SC-5: reading changes nothing -----------------------------------------


def test_sc5_show_and_compare_leave_the_result_files_as_they_were(root: Path) -> None:
    """SC-5: after `show` and `compare`, the files are byte-for-byte what
    they were, and no other file has appeared."""
    first = _run(root, "first.json", REJECT_ACCEPTED, REJECT_SEEDED)
    _correct_the_answer(root)
    second = _run(root, "second.json", PASS, REJECT_SEEDED)
    before = {p: p.read_bytes() for p in (first, second)}
    files = sorted(root.rglob("*"))

    assert eval_cli.main(["show", str(first), "--cases", str(_cases(root))]) == 0
    assert eval_cli.main(
        ["compare", str(first), str(second), "--cases", str(_cases(root))]
    ) == 0

    assert {p: p.read_bytes() for p in (first, second)} == before
    assert sorted(root.rglob("*")) == files


# ---- SC-6: the results already in the repository ---------------------------


@pytest.mark.parametrize("name", [
    "2026-11-10-gemini-3.8-flash.json",
    "2026-11-12-gemini-3.8-flash.json",
    "2026-11-12-gemini-3.8-flash-conformance-only.json",
])
def test_sc6_a_result_recorded_before_the_change_carries_its_inputs_fingerprint(
    name: str,
) -> None:
    """SC-6: each of the three results in the repository on 2026-11-12
    loads and carries one and the same inputs fingerprint — what the case
    files sent at the commit of each run."""
    result = result_from_json((REPO_RESULTS / name).read_text(encoding="utf-8"))

    assert result.inputs == RECORDED_INPUTS
    assert len(result.judgments) == 36


def test_the_repositorys_cases_still_send_what_the_recorded_results_judged() -> None:
    """Regression (found 2026-11-13): giving the evidence bundle a new
    optional field changed the inputs fingerprint of every stored case, so
    `show` and `compare` would have refused every result on record — and no
    test noticed, because the tests above only read what the results say.

    A field a stored bundle does not carry must not move the fingerprint.
    This fails on the day the cases are deliberately rebuilt; that is the
    day a new baseline is recorded and this value changes with it."""
    cases = ROOT / "evals" / "validator" / "cases"
    assert case_module.inputs_fingerprint(cases) == RECORDED_INPUTS


def test_sc6_a_result_with_no_inputs_fingerprint_is_refused_saying_so(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """SC-6: a result made before results recorded their inputs is refused
    by `show` and by `compare`, with a message that says why."""
    stored = _run(root, "first.json", PASS, REJECT_SEEDED)
    other = _run(root, "second.json", PASS, REJECT_SEEDED)
    data = json.loads(stored.read_text(encoding="utf-8"))
    del data["inputs"]
    stored.write_text(json.dumps(data), encoding="utf-8")
    capsys.readouterr()

    assert eval_cli.main(["show", str(stored), "--cases", str(_cases(root))]) == 2
    assert "no inputs fingerprint" in capsys.readouterr().err

    assert eval_cli.main(
        ["compare", str(stored), str(other), "--cases", str(_cases(root))]
    ) == 2
    assert "no inputs fingerprint" in capsys.readouterr().err


# ---- SC-7: a run is what it was --------------------------------------------


def test_sc7_a_run_records_what_it_recorded_before_plus_the_inputs_fingerprint(
    root: Path,
) -> None:
    """SC-7: the same requests are sent and the same judgments and classes
    recorded; the result differs only in carrying the inputs fingerprint."""
    fake = _Fake(PASS, REJECT_SEEDED)
    register_provider("fake-rescore", fake)
    written = root / "first.json"

    assert eval_cli.main(["run", "--cases", str(_cases(root)),
                          "--roster", str(root / "roster.toml"), "--out", str(written)]) == 0

    cases = load_set(_cases(root))
    assert fake.requests == [build_request(case.bundle) for case in cases]
    data = json.loads(written.read_text(encoding="utf-8"))
    assert list(data) == [
        "model", "date", "runs", "instructions", "case_set", "inputs", "scorecard", "judgments",
    ]
    assert [(j["case"], j["expected"], j["check"], j["outcome"], j["class"])
            for j in data["judgments"]] == [
        ("pr-1", "pass", None, "pass", "passed"),
        ("pr-1--tautology", "reject", "test-honesty", "reject", "caught"),
    ]
