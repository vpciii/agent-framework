"""The worker scorecard, the result file, show and compare
(specs/worker-eval SC-8, SC-9, SC-10). Pure: hand-built runs, no session."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from agent_framework.evals.__main__ import main
from agent_framework.evals.worker.scorecard import (
    GateCommand,
    Kept,
    Result,
    RunRecord,
    classify,
    render,
    result_from_json,
    result_to_json,
)


def _kept(case: str, run: int) -> Kept:
    base = f".worktrees/eval/2026-11-20-1/{case}-{run}"
    return Kept(record=f"{base}/record.jsonl", diff=f"{base}/diff.patch", gate=f"{base}/gate.log")


def _run(case: str, run: int, cls: str, tests: str = "not-run", cost: float | None = None,
         elapsed: float | None = None) -> RunRecord:
    return RunRecord(case=case, run=run, cls=cls, reference_tests=tests,  # type: ignore[arg-type]
                     cost_usd=cost, elapsed_s=elapsed, kept=_kept(case, run))


RUNS = (
    _run("pr-31", 1, "ready", "passed", 1.0, 100),
    _run("pr-31", 2, "ready", "failed", 3.0, 300),
    _run("pr-38", 1, "gate-failed", "passed", 2.0, 200),
    _run("pr-38", 2, "timed-out", "not-run", 10.0, 1800),
    _run("pr-73", 1, "could-not-run"),
    _run("pr-88", 1, "spend-limit", "not-run", None, 50),
)


def _result(runs: tuple[RunRecord, ...] = RUNS, case_set: str = "abcdef012345") -> Result:
    return Result(
        model="anthropic:claude-opus-5-5", claude_code="2.1.325", date="2026-11-20", runs=2,
        time_budget_s=1800, spend_limit_usd=10.0, case_set=case_set,
        briefs={"pr-31": "111111111111", "pr-38": "222222222222"}, results=runs,
    )


def test_sc8_the_class_follows_the_plans_table() -> None:
    """SC-8: ready is completed, every gate command passing, no finding."""
    ok, bad = GateCommand("a", True), GateCommand("b", False)
    assert classify("completed", (ok, ok), ()) == "ready"
    assert classify("completed", (ok, bad), ("finding",)) == "gate-failed"
    assert classify("completed", (ok,), ("finding",)) == "refused"
    for ending in ("escalated", "timed-out", "spend-limit", "error"):
        assert classify(ending, (), ()) == ending


def test_sc8_counts_medians_and_unstable_are_what_the_runs_say() -> None:
    """SC-8: counts per class and per case, reference tests beside ready,
    could-not-run on its own, total and median cost and time."""
    card = _result().scorecard
    assert card.total.classes == {
        "ready": 2, "gate-failed": 1, "refused": 0, "escalated": 0,
        "timed-out": 1, "spend-limit": 1, "error": 0, "could-not-run": 1,
    }
    # A ready run that failed its reference tests is still ready.
    assert card.total.reference_tests == {"passed": 2, "failed": 1, "not-run": 3}
    assert card.cases["pr-31"].classes["ready"] == 2
    assert card.cases["pr-31"].reference_tests == {"passed": 1, "failed": 1, "not-run": 0}
    assert card.cases["pr-73"].classes["could-not-run"] == 1
    assert (card.cost_usd.total, card.cost_usd.median, card.cost_usd.reported) == (16.0, 2.5, 4)
    assert (card.elapsed_s.total, card.elapsed_s.median, card.elapsed_s.reported) == (
        2450, 200, 5,
    )
    assert card.unstable == ("pr-38",)


def test_sc9_a_result_round_trips_with_every_field(tmp_path: Path) -> None:
    """SC-9: model, Claude Code version, date, limits, fingerprints, runs."""
    full = replace(RUNS[0], gate=(GateCommand("uv run pytest", True),), handoff=("x",),
                   diff_lines=94, turns=37, detail="why")
    result = _result((full, *RUNS[1:]))
    text = result_to_json(result)
    back = result_from_json(text)
    assert back == result
    data = json.loads(text)
    for field in ("model", "claude_code", "date", "runs", "time_budget_s", "spend_limit_usd",
                  "case_set", "briefs", "results", "scorecard"):
        assert field in data
    assert data["scorecard"]["total"]["classes"]["ready"] == 2
    assert data["results"][0]["class"] == "ready"


def test_sc9_comparing_different_case_sets_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """SC-9: the command says the results are not comparable and exits 2."""
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(result_to_json(_result()), encoding="utf-8")
    b.write_text(result_to_json(_result(case_set="999999999999")), encoding="utf-8")
    assert main(["worker", "compare", str(a), str(b)]) == 2
    assert "not comparable" in capsys.readouterr().out


def test_sc9_compare_names_the_cases_whose_class_or_reference_tests_changed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """SC-9: on one case set, compare lists what changed and exits 0."""
    after = (replace(RUNS[0], reference_tests="failed"), *RUNS[1:4],
             replace(RUNS[4], cls="ready"), RUNS[5])
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(result_to_json(_result()), encoding="utf-8")
    b.write_text(result_to_json(_result(after)), encoding="utf-8")
    assert main(["worker", "compare", str(a), str(b)]) == 0
    changed = [line.split(":")[0] for line in capsys.readouterr().out.splitlines()
               if "→" in line]
    assert changed == ["pr-31", "pr-73"]


def test_sc10_every_run_not_ready_and_every_reference_failure_is_listed_with_its_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """SC-10: the listing names each with its session record, diff and gate output."""
    text = render(_result())
    not_ready, failures = text.split("Not ready for review (4):")[1].split(
        "Reference-test failures (1):"
    )
    for r in RUNS:
        paths = (r.kept.record, r.kept.diff, r.kept.gate)
        if r.cls != "ready":
            assert f"{r.case} run {r.run}: {r.cls}" in not_ready
            assert all(f": {p}" in not_ready for p in paths)
        if r.reference_tests == "failed":
            assert f"{r.case} run {r.run}: {r.cls}" in failures
            assert all(f": {p}" in failures for p in paths)
    assert "pr-31 run 1" not in text.split("Not ready for review")[1]

    path = tmp_path / "r.json"
    path.write_text(result_to_json(_result()), encoding="utf-8")
    assert main(["worker", "show", str(path)]) == 0
    assert capsys.readouterr().out == text
