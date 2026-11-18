"""Running worker eval cases through a fake session in a real repository
(specs/worker-eval SC-4, SC-5, SC-7). No real session is started."""

from __future__ import annotations

import hashlib
import json
import subprocess
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
from agent_framework.evals.worker.run import run_and_write, run_eval
from agent_framework.evals.worker.scorecard import result_from_json
from agent_framework.models import ModelRef
from agent_framework.proc import run_command
from agent_framework.worker.confinement import profile_args, session_env

REPO = Path(__file__).resolve().parents[3]
WORKER = ModelRef(provider="anthropic", model="fake-worker-model")

_TASKS = """# Tasks

### [ ] T-{n} — Do thing {n}
- **Satisfies:** SC-1
- **Brief:** {marker}
"""

_SPEC = """# Spec

## Requirements

- **R-1 (MUST)** The thing is done.

## Success criteria

- **SC-1** — The thing is done. (R-1)
"""

_SETTINGS = """[project]
gate_commands = ["true"]
session_network = ["pypi.org"]
session_env = ["EVAL_ALLOWED"]

[eval]
reference_test_command = "true {files}"
"""


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, list[str]]:
    """A repository, the current directory, whose task text changes in each
    of three commits; returns it and those commits."""
    root = tmp_path / "repo"
    (root / "specs" / "demo").mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    commits = []
    for k in (1, 2, 3):
        tasks = "".join(_TASKS.format(n=n, marker=f"T-{n} AT COMMIT {k}") for n in (1, 2))
        (root / "specs/demo/tasks.md").write_text(tasks)
        (root / "specs/demo/spec.md").write_text(_SPEC)
        _git(root, "add", ".")
        _git(root, "commit", "-q", "-m", f"commit {k}")
        commits.append(_git(root, "rev-parse", "HEAD"))
    monkeypatch.chdir(root)
    return root, commits


def _case(case_id: str, start: str, task: str = "T-1") -> WorkerCase:
    return WorkerCase(
        id=case_id, task=CaseTask(spec="demo", task=task),
        reference=Reference(repo="o/r", pr=1, start=start, head=start),
        reference_tests=("tests/test_x.py",),
        provenance=Provenance(frozen="2026-11-17", by="test"),
    )


def _case_set(tmp_path: Path, *cases: WorkerCase) -> CaseSet:
    path = tmp_path / "settings.toml"
    path.write_text(_SETTINGS)
    return CaseSet(cases=cases, settings=load_settings(path))


class FakeSession:
    """The session seam: records each launch and ends as its case says."""

    def __init__(self, endings: Mapping[str, str] | None = None) -> None:
        self.endings = endings or {}
        self.calls: list[dict[str, object]] = []

    def __call__(
        self, argv: Sequence[str], cwd: Path, timeout_s: float,
        env: Mapping[str, str], record: Path,
    ) -> None:
        head = _git(cwd, "rev-parse", "HEAD")
        self.calls.append({"argv": list(argv), "cwd": cwd, "timeout": timeout_s,
                           "env": dict(env), "record": record, "head": head})
        case = cwd.name.rsplit("-", 1)[0]
        ending = self.endings.get(case, "completed")
        subtype = "error_max_budget_usd" if ending == "spend-limit" else "success"
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(json.dumps(
            {"type": "result", "subtype": subtype, "total_cost_usd": 0.5, "num_turns": 7}
        ) + "\n")
        if ending == "timed-out":
            raise SessionTimeoutError("session exceeded its budget")
        if ending in ("spend-limit", "error"):
            raise SessionResultError("session exited 1")
        if ending == "refused":  # a change the handoff check would refuse
            (cwd / ".github/workflows").mkdir(parents=True)
            (cwd / ".github/workflows/x.yml").write_text("on: push\n")
            _git(cwd, "add", ".")
            _git(cwd, "commit", "-q", "-m", "touch a protected path")
        status = "escalated" if ending == "escalated" else "completed"
        (cwd / ".worker-result.json").write_text(
            json.dumps({"status": status, "detail": f"{case} {status}"})
        )


def _brief(call: dict[str, object]) -> str:
    argv = call["argv"]
    assert isinstance(argv, list)
    return str(argv[argv.index("-p") + 1])


def test_sc4_each_session_gets_its_start_commits_brief_profile_limits_and_model(
    repo: tuple[Path, list[str]], tmp_path: Path,
) -> None:
    """SC-4: launched as a dispatch launches the worker, in a worktree at the
    case's start commit, with the brief built there."""
    root, commits = repo
    case_set = _case_set(tmp_path, _case("a", commits[0]), _case("b", commits[1], "T-2"))
    session = FakeSession()
    environ = {"PATH": "/bin", "EVAL_ALLOWED": "1", "SECRET_TOKEN": "x"}
    records, briefs = run_eval(
        case_set, WORKER, "r1", runs=1, timeout_s=600, spend_limit_usd=2.5,
        environ=environ, session_run=session,
    )

    assert [r.cls for r in records] == ["ready", "ready"]
    profile = profile_args(case_set.settings.project, (str(root.resolve()),))
    for call, start, marker in zip(
        session.calls, commits[:2], ["T-1 AT COMMIT 1", "T-2 AT COMMIT 2"], strict=True
    ):
        argv = call["argv"]
        assert isinstance(argv, list)
        assert call["head"] == start
        assert marker in _brief(call) and "AT COMMIT 3" not in _brief(call)
        assert argv[argv.index("--model") + 1] == "fake-worker-model"
        assert argv[argv.index("--max-budget-usd") + 1] == "2.50"
        assert call["timeout"] == 600
        assert all(a in argv for a in profile)
        assert call["env"] == session_env(case_set.settings.project, environ)
        assert "SECRET_TOKEN" not in str(call["env"])
    assert set(briefs) == {"a", "b"}
    assert all(r.cost_usd == 0.5 and r.turns == 7 for r in records)
    assert all(r.kept.record and Path(r.kept.record).is_file() for r in records)
    assert not (root / ".worktrees/eval/r1/a-1").exists()  # removed without --keep


def test_sc4_three_runs_of_a_case_start_three_sessions_in_three_worktrees(
    repo: tuple[Path, list[str]], tmp_path: Path,
) -> None:
    """SC-4: a case run three times is three sessions, three trees."""
    _, commits = repo
    session = FakeSession()
    records, _ = run_eval(
        _case_set(tmp_path, _case("a", commits[0])), WORKER, "r1", runs=3,
        timeout_s=60, spend_limit_usd=1.0, keep=True, session_run=session,
    )
    trees = {Path(str(c["cwd"])) for c in session.calls}
    assert len(session.calls) == 3 and len(trees) == 3
    assert {c["head"] for c in session.calls} == {commits[0]}
    assert all(t.is_dir() for t in trees)  # kept
    assert [(r.case, r.run) for r in records] == [("a", 1), ("a", 2), ("a", 3)]


def _snapshot(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file() and not p.relative_to(root).parts[0] in (".git", ".worktrees")
    }


def test_sc5_no_push_pull_request_or_alert_and_nothing_written_elsewhere(
    repo: tuple[Path, list[str]], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SC-5: across every kind of session ending, the eval issues no push,
    pull request or alert command, and writes only its own files."""
    root, commits = repo

    def never(*args: object, **kwargs: object) -> None:
        raise AssertionError("the eval reached the worker's handoff or an alert")

    monkeypatch.setattr("agent_framework.worker.orchestrator.work", never)
    monkeypatch.setattr("agent_framework.alerts.notify", never)
    monkeypatch.setattr("agent_framework.worker.handoff.open_pr", never)
    commands: list[list[str]] = []

    def run(args: Sequence[str]) -> str:
        commands.append(list(args))
        return run_command(args)

    endings = ["completed", "escalated", "timed-out", "spend-limit", "refused"]
    case_set = _case_set(tmp_path, *(_case(e, commits[0]) for e in endings))
    before, refs = _snapshot(root), _git(root, "for-each-ref")
    out = root / "results/out.json"
    result = run_and_write(
        case_set, WORKER, out, date="2026-11-17", claude_code="9.9.9", runs=1,
        timeout_s=60, spend_limit_usd=1.0, run=run, session_run=FakeSession(
            {e: e for e in endings}
        ),
    )

    assert {r.case: r.cls for r in result.results} == {
        "completed": "ready", "escalated": "escalated", "timed-out": "timed-out",
        "spend-limit": "spend-limit", "refused": "ready",  # scored by T-6
    }
    for c in commands:
        assert c[0] != "gh" and "push" not in c, c
    after = _snapshot(root)
    assert {k: v for k, v in after.items() if k != "results/out.json"} == before
    assert _git(root, "for-each-ref") == refs  # no branch, no tag
    assert sorted(p.name for p in (root / ".worktrees").iterdir()) == ["eval", "records"]
    assert result_from_json(out.read_text()) == result


def test_sc5_no_workflow_names_the_eval_command() -> None:
    """SC-5: the eval never runs in CI."""
    workflows = sorted((REPO / ".github/workflows").glob("*.y*ml"))
    assert workflows
    for path in workflows:
        text = path.read_text(encoding="utf-8")
        for name in ("agent-framework-eval", "agent_framework.evals", "evals.worker"):
            assert name not in text, f"{path} names {name}"


def test_sc7_an_unknown_start_commit_could_not_run_and_the_next_case_runs(
    repo: tuple[Path, list[str]], tmp_path: Path,
) -> None:
    """SC-7: the eval's own failure on a case is could-not-run, never the
    worker's success or failure, and the run goes on."""
    root, commits = repo
    session = FakeSession()
    out = root / "results/out.json"
    result = run_and_write(
        _case_set(tmp_path, _case("a-missing", "0" * 40), _case("b-next", commits[0])),
        WORKER, out, date="2026-11-17", claude_code="9.9.9", runs=1,
        timeout_s=60, spend_limit_usd=1.0, session_run=session,
    )

    missing, nxt = result.results
    assert missing.cls == "could-not-run" and "0" * 40 in missing.detail
    assert missing.cost_usd is None and missing.elapsed_s is None
    assert nxt.cls == "ready" and len(session.calls) == 1
    assert "a-missing" not in result.briefs
    total = result.scorecard.total
    assert total.classes["could-not-run"] == 1
    assert total.classes["ready"] == 1
    assert sum(total.classes.values()) - total.classes["could-not-run"] == 1
    assert result.scorecard.elapsed_s.reported == 1


def test_worker_run_refuses_before_any_session(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from agent_framework.evals.__main__ import main
    from agent_framework.evals.worker.case import write_case

    cases = tmp_path / "cases"
    cases.mkdir()
    _case_set(tmp_path, _case("pr-1", "0" * 40))
    write_case(_case("pr-1", "0" * 40), cases)
    roster = REPO / "agent-framework.toml"
    taken = tmp_path / "taken.json"
    taken.write_text("{}")
    base = ["worker", "run", "--cases", str(cases), "--roster", str(roster)]
    assert main([*base, "--runs", "0"]) == 2
    assert main([*base, "--spend-limit", "0"]) == 2
    assert main([*base, "--only", "pr-nope"]) == 2
    assert main([*base, "--out", str(taken)]) == 2
    assert taken.read_text() == "{}"
    assert "already holds a result" in capsys.readouterr().err
