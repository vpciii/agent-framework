"""Starting again: resume, afresh, and a branch already pushed
(specs/dispatch-from-issue T-3).

Drives the real orchestrator over a real repository with a bare remote;
only the session, `gh` and the alert channels are faked.

Verifies:
- SC-11: after a run stopped at its time budget, and after one stopped at
  its spend limit, `existing="continue"` runs a session in the same worktree
  on the same branch, its brief holds the handoff note, and the note and the
  old result file are gone before it starts.
- SC-13: a pushed branch with no pull request gets one pull request and no
  session; with one open, `PrAlreadyOpen` names it and no session runs.
- SC-14: after an escalation, and after a refused handoff, a session runs in
  a fresh worktree cut from `origin/main`, and the earlier commits are
  reachable from an `attempt/` branch.
- SC-18: the default still refuses an existing worktree and an existing
  branch with today's messages.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Literal

import pytest

from agent_framework.errors import SessionResultError, SessionTimeoutError, WorktreeError
from agent_framework.proc import run_command
from agent_framework.worker.orchestrator import work
from agent_framework.worker.types import (
    Escalated,
    HandoffRefused,
    PrAlreadyOpen,
    PrOpened,
    SpendLimitReached,
    TimedOut,
    WorkerOutcome,
)

from .test_brief import _SPEC_MD, _TASKS_MD
from .test_orchestrator import _roster
from .test_timeout_and_escalation_alerts import FakeTracker

_TREE = Path(".worktrees/fixture-t-1")
_BRANCH = "feat/fixture-t-1"
_PR = "https://github.com/x/y/pull/99"

Session = Callable[..., None]


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A real repository with a bare remote; the orchestrator runs from its root."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    root = tmp_path / "proj"
    _git(tmp_path, "clone", "-q", str(origin), str(root))
    for rel, text in {
        "specs/fixture/spec.md": _SPEC_MD,
        "specs/fixture/tasks.md": _TASKS_MD,
        ".github/workflows/ci.yml": "name: CI\n",
        ".gitignore": ".worktrees/\n",
    }.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "feat: seed")
    _git(root, "push", "-q", "origin", "HEAD:main")
    monkeypatch.chdir(root)
    return root


class _Gh:
    """Real `git`; `gh` recorded and answered (an open PR, if one is set)."""

    def __init__(self, open_pr: str = "", create_fails: bool = False) -> None:
        self.open_pr = open_pr
        self.create_fails = create_fails
        self.created: list[list[str]] = []

    def __call__(self, args: Sequence[str]) -> str:
        if args[0] != "gh":
            return run_command(args)
        if list(args[1:3]) == ["pr", "list"]:
            return self.open_pr + "\n"
        if list(args[1:3]) == ["pr", "create"]:
            if self.create_fails:
                raise RuntimeError("gh: network down")
            self.created.append(list(args))
            return _PR + "\n"
        return ""


def _session(
    *, change: tuple[str, str] = ("src/widget.py", "x = 1\n"),
    status: str = "completed", stop: Literal["timeout", "spend"] | None = None,
    seen: list[dict[str, object]] | None = None,
) -> Session:
    """A session that records what it found, commits `change`, writes its
    result file, and then either exits or stops as `stop` says."""

    def run(args: Sequence[str], cwd: Path, timeout_s: float, env: object,
            record: Path) -> None:
        if seen is not None:
            seen.append({
                "brief": args[list(args).index("-p") + 1],
                "cwd": cwd.resolve(),
                "branch": _git(cwd, "branch", "--show-current"),
                "head": _git(cwd, "rev-parse", "HEAD"),
                "note": (cwd / "HANDOFF.md").exists(),
                "result": (cwd / ".worker-result.json").exists(),
            })
        rel, text = change
        (cwd / rel).parent.mkdir(parents=True, exist_ok=True)
        (cwd / rel).write_text(text, encoding="utf-8")
        _git(cwd, "add", rel)
        _git(cwd, "commit", "-q", "-m", f"feat: {status} work")
        (cwd / ".worker-result.json").write_text(
            json.dumps({"status": status, "detail": f"{status} detail"}), encoding="utf-8")
        if stop == "timeout":
            raise SessionTimeoutError("budget")
        if stop == "spend":
            record.parent.mkdir(parents=True, exist_ok=True)
            record.write_text(json.dumps({"type": "result", "subtype": "error_max_budget_usd",
                                          "total_cost_usd": 10.5}) + "\n", encoding="utf-8")
            raise SessionResultError("session exited 1: ")

    return run


def _work(session: Session, gh: _Gh | None = None, **kw: object) -> WorkerOutcome:
    return work("fixture", "T-1", _roster(), run=gh or _Gh(), session_run=session,
                tracker=FakeTracker(), push_factory=lambda: None, **kw)  # type: ignore[arg-type]


@pytest.mark.parametrize("stop", ["timeout", "spend"])
def test_sc11_a_stopped_run_resumes_in_its_worktree_with_the_note(
    repo: Path, stop: Literal["timeout", "spend"],
) -> None:
    """SC-11: stopped at its time budget or spend limit → the next run resumes
    in the same worktree on the same branch, the note in its brief and gone
    from the tree, with no old result file."""
    first = _work(_session(change=("src/a.py", "a = 1\n"), stop=stop))
    assert isinstance(first, TimedOut if stop == "timeout" else SpendLimitReached)
    note = (_TREE / "HANDOFF.md").read_text(encoding="utf-8")
    stopped_at = _git(_TREE, "rev-parse", "HEAD")

    seen: list[dict[str, object]] = []
    gh = _Gh()
    outcome = _work(_session(change=("src/b.py", "b = 1\n"), seen=seen), gh,
                    existing="continue")

    [s] = seen
    assert s["cwd"] == (repo / _TREE).resolve()
    assert s["branch"] == _BRANCH and s["head"] == stopped_at
    assert s["note"] is False and s["result"] is False
    brief = str(s["brief"])
    assert "== HANDOFF NOTE" in brief and note.strip() in brief
    # Both sessions' commits leave on the one branch.
    assert _git(repo, "rev-list", "--count", f"origin/main..origin/{_BRANCH}") == "2"
    assert isinstance(outcome, PrOpened) and len(gh.created) == 1


def test_sc13_a_pushed_branch_without_a_pr_gets_one_and_no_session(repo: Path) -> None:
    """SC-13: pushed, then the PR failed to open → one PR from the surviving
    result file, no session, the worktree removed."""
    with pytest.raises(RuntimeError, match="network down"):
        _work(_session(), _Gh(create_fails=True))
    assert _git(repo, "ls-remote", "--heads", "origin", _BRANCH)

    seen: list[dict[str, object]] = []
    gh = _Gh()
    outcome = _work(_session(seen=seen), gh, existing="continue")

    assert outcome == PrOpened(url=_PR, branch=_BRANCH, task_id="T-1")
    assert seen == []
    [create] = gh.created
    assert "--head" in create and _BRANCH in create
    assert "completed detail" in create[create.index("--body") + 1]
    assert not _TREE.exists()


def test_sc13_with_no_worktree_left_the_pr_says_the_run_was_interrupted(
    repo: Path,
) -> None:
    """SC-13: the branch is on the remote, nothing local → one PR whose body
    says it was opened after an interrupted run; no session."""
    _git(repo, "push", "-q", "origin", f"HEAD:refs/heads/{_BRANCH}")
    seen: list[dict[str, object]] = []
    gh = _Gh()
    outcome = _work(_session(seen=seen), gh, existing="continue")

    assert isinstance(outcome, PrOpened) and seen == []
    [create] = gh.created
    assert "interrupted run" in create[create.index("--body") + 1]


def test_sc13_an_open_pr_is_named_and_no_session_starts(repo: Path) -> None:
    """SC-13: an open PR for the branch → `PrAlreadyOpen` with its address."""
    _git(repo, "push", "-q", "origin", f"HEAD:refs/heads/{_BRANCH}")
    seen: list[dict[str, object]] = []
    gh = _Gh(open_pr="https://github.com/x/y/pull/7")
    outcome = _work(_session(seen=seen), gh, existing="continue")

    assert outcome == PrAlreadyOpen(url="https://github.com/x/y/pull/7", branch=_BRANCH,
                                    task_id="T-1")
    assert seen == [] and gh.created == []


@pytest.mark.parametrize("left_by", ["escalation", "refused handoff"])
def test_sc14_a_run_left_by_an_escalation_or_refusal_starts_afresh(
    repo: Path, left_by: str,
) -> None:
    """SC-14: a fresh worktree cut from `origin/main`; the earlier commits
    are reachable from an `attempt/` branch."""
    if left_by == "escalation":
        first = _work(_session(status="escalated"))
        assert isinstance(first, Escalated)
    else:
        first = _work(_session(change=(".github/workflows/ci.yml", "on: []\n")))
        assert isinstance(first, HandoffRefused)
    earlier = _git(_TREE, "rev-parse", "HEAD")

    seen: list[dict[str, object]] = []
    outcome = _work(_session(seen=seen), existing="continue")

    [s] = seen
    assert s["head"] == _git(repo, "rev-parse", "origin/main")
    assert s["branch"] == _BRANCH and s["result"] is False
    [kept] = _git(repo, "branch", "--list", "--format=%(refname:short)",
                  "attempt/*").splitlines()
    assert kept.startswith("attempt/fixture-t-1-")
    _git(repo, "merge-base", "--is-ancestor", earlier, kept)  # raises if not
    assert isinstance(outcome, PrOpened)


def test_sc18_by_default_a_worktree_or_branch_left_behind_is_refused(repo: Path) -> None:
    """SC-18: without `existing`, today's refusals and messages; no session."""
    assert isinstance(_work(_session(status="escalated")), Escalated)
    seen: list[dict[str, object]] = []
    with pytest.raises(WorktreeError, match="worktree already exists"):
        _work(_session(seen=seen))
    _git(repo, "worktree", "remove", "--force", str(_TREE))
    with pytest.raises(WorktreeError, match="branch already exists"):
        _work(_session(seen=seen))
    assert seen == []
    assert not _git(repo, "branch", "--list", "attempt/*")


def test_an_unknown_choice_for_existing_is_refused(repo: Path) -> None:
    with pytest.raises(Exception, match="existing must be"):
        _work(_session(), existing="overwrite")
