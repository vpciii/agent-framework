"""Scoring a completed session (specs/worker-eval SC-6). The gate commands
and the reference tests are small shell scripts, not this repository's
gate, and the session is a fake one: no real session is started."""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from agent_framework.errors import SessionResultError, SessionTimeoutError
from agent_framework.evals.worker.case import (
    CaseSet,
    CaseTask,
    Provenance,
    Reference,
    WorkerCase,
    load_settings,
)
from agent_framework.evals.worker.run import run_eval
from agent_framework.evals.worker.scorecard import GateCommand, RunRecord
from agent_framework.models import ModelRef

WORKER = ModelRef(provider="anthropic", model="fake-worker-model")
ENVIRON = {"PATH": "/usr/bin:/bin", "EVAL_ALLOWED": "1", "SECRET_TOKEN": "x"}

_TASKS = "# Tasks\n\n### [ ] T-1 — Do the thing\n- **Satisfies:** SC-1\n- **Brief:** do it\n"
_SPEC = "# Spec\n\n## Success criteria\n\n- **SC-1** — The thing is done. (R-1)\n"
# Each gate command is a script; `env.sh` passes only in the session's env.
_SETTINGS = """[project]
gate_commands = ["sh gate/done.sh", "sh gate/env.sh"{extra}]
session_env = ["EVAL_ALLOWED"]

[eval]
reference_test_command = "sh {{files}}"
"""


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _commit(root: Path, files: Mapping[str, str], message: str) -> str:
    for path, text in files.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text)
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "HEAD")


@pytest.fixture
def case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> WorkerCase:
    """A repository whose start commit has the task, the gate scripts and a
    test that checks nothing; at the reference head, the test checks the
    thing is done."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    start = _commit(root, {
        "specs/demo/tasks.md": _TASKS, "specs/demo/spec.md": _SPEC,
        "impl.txt": "TODO\n", "tests/test_thing.sh": "exit 0\n",
        "gate/done.sh": "grep -q DONE impl.txt\n",
        "gate/env.sh": 'test "$EVAL_ALLOWED" = 1 && test -z "$SECRET_TOKEN"\n',
    }, "start")
    head = _commit(root, {
        "impl.txt": "DONE\n", "tests/test_thing.sh": "grep -q DONE impl.txt\n",
    }, "the reference pull request")
    _git(root, "checkout", "-q", start)  # the head is reached only through git
    monkeypatch.chdir(root)
    return WorkerCase(
        id="pr-1", task=CaseTask(spec="demo", task="T-1"),
        reference=Reference(repo="o/r", pr=1, start=start, head=head),
        reference_tests=("tests/test_thing.sh",),
        provenance=Provenance(frozen="2026-11-18", by="test"),
    )


def _case_set(tmp_path: Path, case: WorkerCase, extra_gate: str) -> CaseSet:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "settings.toml"
    path.write_text(_SETTINGS.format(extra=extra_gate))
    return CaseSet(cases=(case,), settings=load_settings(path))


class Session:
    """Ends as told; a completed one commits `files` first, then leaves
    `uncommitted` in its working tree."""

    def __init__(
        self, ending: str = "completed", files: Mapping[str, str] | None = None,
        uncommitted: Mapping[str, str] | None = None,
    ) -> None:
        self.ending, self.files, self.uncommitted = ending, files or {}, uncommitted or {}

    def __call__(
        self, argv: Sequence[str], cwd: Path, timeout_s: float,
        env: Mapping[str, str], record: Path,
    ) -> None:
        subtype = "error_max_budget_usd" if self.ending == "spend-limit" else "success"
        record.write_text(json.dumps(
            {"type": "result", "subtype": subtype, "total_cost_usd": 0.75, "num_turns": 12}
        ) + "\n")
        if self.ending == "timed-out":
            raise SessionTimeoutError("session exceeded its budget")
        if self.ending in ("spend-limit", "error"):
            raise SessionResultError("session exited 1")
        if self.files:
            _commit(cwd, self.files, "the session's change")
        for path, text in self.uncommitted.items():
            (cwd / path).write_text(text)
        status = "escalated" if self.ending == "escalated" else "completed"
        (cwd / ".worker-result.json").write_text(json.dumps({"status": status, "detail": "x"}))


def _run(
    tmp_path: Path, case: WorkerCase, session: Session, run_id: str = "r1",
    extra_gate: str = "", timeout_s: float = 60,
) -> RunRecord:
    records, _ = run_eval(
        _case_set(tmp_path, case, extra_gate), WORKER, run_id, runs=1, timeout_s=timeout_s,
        spend_limit_usd=1.0, environ=ENVIRON, session_run=session,
    )
    (record,) = records
    return record


# The session does the thing, with its own test that checks nothing.
DONE = {"impl.txt": "DONE\n", "tests/test_thing.sh": "exit 0\n"}


def test_sc6_a_completed_session_is_scored_at_its_last_commit(
    case: WorkerCase, tmp_path: Path,
) -> None:
    """SC-6: each gate command's outcome at the last commit (run with the
    session's env), the handoff findings, the reference tests passing on the
    session's code, the diff size, and the cost, turns and elapsed time."""
    r = _run(tmp_path, case, Session(files=DONE), extra_gate=', "sh -c \'exit 3\'"')

    assert r.gate == (
        GateCommand("sh gate/done.sh", True), GateCommand("sh gate/env.sh", True),
        GateCommand("sh -c 'exit 3'", False),
    )
    assert r.cls == "gate-failed"
    assert r.handoff == ()
    assert r.reference_tests == "passed"
    assert r.diff_lines == 2  # one line out and one in, in impl.txt
    assert (r.cost_usd, r.turns) == (0.75, 12)
    assert r.elapsed_s is not None and r.elapsed_s >= 0
    kept = r.kept
    assert kept.record and kept.diff and kept.gate
    eval_dir = Path(".worktrees/eval/r1").resolve()
    for path in (kept.record, kept.diff, kept.gate):
        assert Path(path).resolve().parent == eval_dir and Path(path).is_file()
    assert "+DONE" in Path(kept.diff).read_text()
    gate_log = Path(kept.gate).read_text()
    assert "$ sh -c 'exit 3'" in gate_log and "[failed]" in gate_log
    assert (eval_dir / "pr-1-1-reference.log").is_file()
    assert not (eval_dir / "pr-1-1-reference").exists()  # the copy is dropped


def test_sc6_reference_tests_fail_when_the_sessions_code_does_not_satisfy_them(
    case: WorkerCase, tmp_path: Path,
) -> None:
    """SC-6: the reference versions are laid over the session's own test
    files, so a session whose own test passes still fails them."""
    r = _run(tmp_path, case, Session(files={**DONE, "impl.txt": "HALF\n"}))

    assert r.reference_tests == "failed"
    assert r.gate[0] == GateCommand("sh gate/done.sh", False)  # at its last commit
    assert r.cls == "gate-failed"


def test_sc6_ready_and_refused_follow_the_gate_and_the_handoff_check(
    case: WorkerCase, tmp_path: Path,
) -> None:
    """SC-6: every command passing and no finding is ready; a finding since
    the start commit is refused, and the finding is recorded."""
    ready = _run(tmp_path, case, Session(files=DONE))
    assert ready.cls == "ready" and ready.handoff == ()

    refused = _run(tmp_path, case, Session(files={
        **DONE, ".github/workflows/x.yml": "on: push\n"}), run_id="r2")
    assert refused.cls == "refused"
    assert len(refused.handoff) == 1 and ".github/workflows/x.yml" in refused.handoff[0]
    assert refused.reference_tests == "passed"


@pytest.mark.parametrize("ending", ["escalated", "timed-out", "spend-limit", "error"])
def test_sc6_every_other_outcome_records_cost_turns_and_time_and_no_score(
    case: WorkerCase, tmp_path: Path, ending: str,
) -> None:
    """SC-6: for every other outcome, the outcome, cost, turns and elapsed
    time, with the reference tests not-run."""
    r = _run(tmp_path, case, Session(ending, files=DONE))

    assert r.cls == ending
    assert (r.cost_usd, r.turns) == (0.75, 12)
    assert r.elapsed_s is not None
    assert r.reference_tests == "not-run"
    assert r.gate == () and r.diff_lines is None


def test_sc6_what_the_session_left_uncommitted_is_not_scored(
    case: WorkerCase, tmp_path: Path,
) -> None:
    """SC-6 (regression): the gate and the reference tests run against the
    last commit. A session that did the thing in its working tree but
    committed something else has not done it."""
    r = _run(tmp_path, case, Session(
        files={"notes.txt": "started\n"},
        uncommitted={"impl.txt": "DONE\n", "scratch.txt": "left behind\n"},
    ))

    assert r.gate[0] == GateCommand("sh gate/done.sh", False)
    assert r.cls == "gate-failed"
    assert r.reference_tests == "failed"
    gate_log = Path(r.kept.gate or "").read_text()
    assert "impl.txt" in gate_log and "scratch.txt" in gate_log  # named, then set aside


def test_sc6_a_command_that_hangs_fails_at_the_time_budget(
    case: WorkerCase, tmp_path: Path,
) -> None:
    """SC-6 (regression): a gate command that never returns is stopped at the
    session's time budget and recorded as failed; the run goes on."""
    started = time.monotonic()
    r = _run(tmp_path, case, Session(files=DONE), extra_gate=', "sleep 60 & wait"', timeout_s=1)

    assert time.monotonic() - started < 30
    assert r.gate[-1] == GateCommand("sleep 60 & wait", False)
    assert r.gate[:2] == (GateCommand("sh gate/done.sh", True), GateCommand("sh gate/env.sh", True))
    assert r.cls == "gate-failed"
    assert r.reference_tests == "passed"  # scoring went on after the stopped command
    assert "timed out after 1" in Path(r.kept.gate or "").read_text()


def test_sc6_a_scoring_that_cannot_be_set_up_could_not_run(
    case: WorkerCase, tmp_path: Path,
) -> None:
    """SC-6, R-7: a reference test file absent at the head is the eval's
    failure, not the worker's."""
    broken = WorkerCase(
        id=case.id, task=case.task, reference=case.reference,
        reference_tests=("tests/missing.sh",), provenance=case.provenance,
    )
    r = _run(tmp_path, broken, Session(files=DONE))

    assert r.cls == "could-not-run"
    assert "cannot score the session" in r.detail
    assert (r.cost_usd, r.turns) == (0.75, 12)
