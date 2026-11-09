"""Refusing the handoff (specs/worker-confinement, ADR 0007 decision 4).

Drives the real orchestrator over real git repositories; only the session,
`gh` and the alert channels are faked.

Verifies:
- SC-6: a refused handoff pushes nothing, opens no PR, keeps the worktree,
  carries every finding, and raises one `refused` alert the resume card lists.
- SC-7: a successful handoff's push does not run a hook planted in the repository.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest

from agent_framework.proc import run_command
from agent_framework.status.card import GitHubSnapshot, github_snapshot, read_repo, render
from agent_framework.worker.orchestrator import work
from agent_framework.worker.types import HandoffRefused, PrOpened

from .test_brief import _SPEC_MD, _TASKS_MD
from .test_orchestrator import _roster
from .test_timeout_and_escalation_alerts import FakePush, FakeTracker


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


@pytest.fixture
def project_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A real repository with a bare remote, holding the fixture spec, a CI
    workflow and a test file; the orchestrator runs from its root."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    root = tmp_path / "proj"
    _git(tmp_path, "clone", "-q", str(origin), str(root))
    files = {
        "specs/fixture/spec.md": _SPEC_MD,
        "specs/fixture/tasks.md": _TASKS_MD,
        ".github/workflows/ci.yml": "name: CI\n",
        "tests/test_old.py": "def test_old() -> None:\n    assert True\n",
        ".gitignore": ".worktrees/\n",
    }
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "feat: seed")
    _git(root, "push", "-q", "origin", "HEAD:main")
    monkeypatch.chdir(root)
    return root


class _RealGitFakeGh:
    """Real `git`; `gh` recorded and answered."""

    def __init__(self) -> None:
        self.gh: list[list[str]] = []

    def __call__(self, args: Sequence[str]) -> str:
        if args[0] == "gh":
            self.gh.append(list(args))
            return "https://github.com/x/y/pull/99\n" if args[1:3] == ["pr", "create"] else ""
        return run_command(args)


def _session(
    changes: Mapping[str, str | None],
) -> Callable[[Sequence[str], Path, float, Mapping[str, str]], None]:
    """A session that commits `changes` (path → new text, or None to delete)
    and reports completion — what a real one leaves behind, minus the model."""

    def run(args: Sequence[str], cwd: Path, timeout_s: float, env: Mapping[str, str]) -> None:
        for rel, text in changes.items():
            if text is None:
                _git(cwd, "rm", "-q", rel)
            else:
                (cwd / rel).parent.mkdir(parents=True, exist_ok=True)
                (cwd / rel).write_text(text, encoding="utf-8")
                _git(cwd, "add", rel)
        _git(cwd, "commit", "-q", "-m", "feat: the session's work")
        (cwd / ".worker-result.json").write_text(
            json.dumps({"status": "completed", "detail": "done"}), encoding="utf-8"
        )

    return run


_FORBIDDEN: dict[str, str | None] = {
    "src/widget.py": "def spin() -> bool:\n    return True\n",
    "specs/fixture/spec.md": _SPEC_MD.replace("CRITERION-ONE-TEXT", "an easier criterion"),
    ".github/workflows/ci.yml": "name: CI\non: []\n",
    "tests/test_old.py": None,
}


def test_sc6_a_refused_handoff_pushes_nothing_keeps_the_tree_and_alerts(
    project_repo: Path,
) -> None:
    """SC-6: no push, no PR, the worktree kept, every finding in the outcome,
    one `refused` alert — and the resume card lists it."""
    run, tracker, push = _RealGitFakeGh(), FakeTracker(), FakePush()

    outcome = work("fixture", "T-1", _roster(), run=run, session_run=_session(_FORBIDDEN),
                   tracker=tracker, push_factory=lambda: push)

    assert isinstance(outcome, HandoffRefused)
    assert {(f.rule, f.path) for f in outcome.findings} == {
        ("contract", "specs/fixture/spec.md"),
        ("protected-path", ".github/workflows/ci.yml"),
        ("deleted-test", "tests/test_old.py"),
    }
    # Nothing left the machine.
    assert _git(project_repo, "ls-remote", "--heads", "origin", "feat/fixture-t-1") == ""
    assert not [c for c in run.gh if c[1:3] == ["pr", "create"]]
    # The worktree is kept for inspection, with the session's commit in it.
    tree = Path(outcome.worktree_path)
    assert tree.is_dir() and (tree / "src/widget.py").is_file()
    # One alert, labelled refused, naming the task; the phone is told once.
    assert tracker.created == [
        ("[refused:fixture/T-1] T-1 of fixture: handoff refused", "refused")
    ]
    assert len(push.sent) == 1
    assert outcome.alerts == ("github issue: opened #40", "phone push: sent")

    # The resume card counts a refused issue among its alerts.
    def gh(args: Sequence[str]) -> str:
        if "--label" in args and args[args.index("--label") + 1] == "refused":
            return json.dumps([{"number": 40, "title": tracker.created[0][0], "url": "u"}])
        return "[]"

    snapshot = github_snapshot(gh)
    assert [i.number for i in snapshot.open_alerts] == [40]
    card = render(read_repo(project_repo), snapshot)
    assert "Issue #40 — [refused:fixture/T-1]" in card
    assert "**Next action:** Answer #40" in card


def test_sc6_the_refusal_names_every_finding_to_the_human(project_repo: Path) -> None:
    """SC-6: the alert's body lists each finding with its path."""
    bodies: list[str] = []

    class _Tracker(FakeTracker):
        def create(self, title: str, body: str, label: str) -> str:
            bodies.append(body)
            return super().create(title, body, label)

    work("fixture", "T-1", _roster(), run=_RealGitFakeGh(), session_run=_session(_FORBIDDEN),
         tracker=_Tracker(), push_factory=lambda: None)

    [body] = bodies
    for path in ("specs/fixture/spec.md", ".github/workflows/ci.yml", "tests/test_old.py"):
        assert path in body
    assert ".worktrees/fixture-t-1" in body


def test_sc7_a_planted_hook_does_not_run_when_the_orchestrator_pushes(
    project_repo: Path,
) -> None:
    """SC-7: a pre-push hook in the repository is not executed by a
    successful handoff — and the handoff still succeeds."""
    marker = project_repo.parent / "hook-ran"
    hook = project_repo / ".git" / "hooks" / "pre-push"
    hook.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
    hook.chmod(0o755)
    run = _RealGitFakeGh()

    outcome = work(
        "fixture", "T-1", _roster(), run=run,
        session_run=_session({"src/widget.py": "def spin() -> bool:\n    return True\n"}),
        tracker=FakeTracker(), push_factory=lambda: None,
    )

    assert isinstance(outcome, PrOpened)
    assert _git(project_repo, "ls-remote", "--heads", "origin", "feat/fixture-t-1")  # pushed
    assert not marker.exists()  # …without running the hook
    assert not Path(".worktrees/fixture-t-1").exists()  # and cleaned up


def test_refused_outcome_prints_and_exits_four(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """The CLI: outcome JSON with the findings; exit 4, distinct from 0/2/3."""
    from agent_framework.worker.__main__ import main
    from agent_framework.worker.types import HandoffFinding

    roster = tmp_path / "roster.toml"
    roster.write_text('[roles]\nworker = { provider = "anthropic", model = "m" }\n')
    refused = HandoffRefused(
        worktree_path=".worktrees/x",
        findings=(HandoffFinding("protected-path", ".github/ci.yml", "matches"),),
    )

    code = main(["fixture", "T-1", "--roster", str(roster)], work_fn=lambda *a, **k: refused)

    out = json.loads(capsys.readouterr().out)
    assert code == 4
    assert out["outcome"] == "handoff_refused"
    assert out["findings"] == [
        {"rule": "protected-path", "path": ".github/ci.yml", "detail": "matches"}
    ]


def test_an_empty_card_names_all_three_alert_kinds() -> None:
    card = render(read_repo(Path(".")), GitHubSnapshot((), ()))
    assert "no open escalation, timeout or refused issues" in card
