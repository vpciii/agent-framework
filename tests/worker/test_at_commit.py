"""The worker reads its task at a commit (specs/dispatch-from-issue T-2).

Verifies:
- SC-5: with `at`, the brief is built from `tasks.md` and `spec.md` as they
  are at that commit, whatever the working files hold, and the worktree's
  head is that commit.
- SC-18: with no `at`, `work()` issues exactly the commands it issued before
  this change, and still refuses an existing worktree or branch.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from agent_framework.errors import UnknownTaskError, WorktreeError
from agent_framework.worker import handoff, worktree
from agent_framework.worker.orchestrator import work
from agent_framework.worker.types import Escalated

from .test_brief import _SPEC_MD, _TASKS_MD
from .test_orchestrator import _GitGh, _roster, _session
from .test_timeout_and_escalation_alerts import FakeTracker


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


@pytest.fixture
def checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    """A real repository whose working `tasks.md` differs from the commit returned."""
    root = tmp_path / "repo"
    specs = root / "specs" / "fixture"
    specs.mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    (specs / "tasks.md").write_text(_TASKS_MD, encoding="utf-8")
    (specs / "spec.md").write_text(_SPEC_MD, encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "start")
    commit = _git(root, "rev-parse", "HEAD")
    (specs / "tasks.md").write_text(
        _TASKS_MD.replace("WIDGET-DETAIL-SENTINEL", "WORKING-COPY-ONLY"), encoding="utf-8"
    )
    monkeypatch.chdir(root)
    return root, commit


def test_sc5_the_brief_and_the_worktree_come_from_the_commit_not_the_working_files(
    checkout: tuple[Path, str],
) -> None:
    """SC-5: working `tasks.md` differs from the commit's → the session's brief
    is the commit's, and its worktree's head is that commit."""
    root, commit = checkout
    seen: list[tuple[str, str]] = []

    def session(
        args: Sequence[str], cwd: Path, timeout_s: float, env: Mapping[str, str],
        record: Path,
    ) -> None:
        seen.append((args[list(args).index("-p") + 1], _git(cwd, "rev-parse", "HEAD")))
        (cwd / ".worker-result.json").write_text(
            json.dumps({"status": "escalated", "detail": "stop here"}), encoding="utf-8"
        )

    outcome = work("fixture", "T-1", _roster(), specs_dir=root / "specs", at=commit,
                   session_run=session, tracker=FakeTracker(), push_factory=lambda: None)

    assert isinstance(outcome, Escalated)
    [(prompt, head)] = seen
    assert "WIDGET-DETAIL-SENTINEL" in prompt
    assert "WORKING-COPY-ONLY" not in prompt
    assert head == commit


def test_sc5_with_a_commit_nothing_is_fetched_and_the_tree_is_cut_there(
    checkout: tuple[Path, str],
) -> None:
    """SC-5: the commit given is the base; no fetch of the remote's main."""
    root, commit = checkout
    git = _GitGh()

    def run(args: Sequence[str]) -> str:
        if "show" in args:  # the artifacts, from the real repository
            return subprocess.run(list(args), check=True, capture_output=True,
                                  text=True).stdout
        return git(args)

    _, session = _session({"status": "escalated", "detail": "stop here"})
    work("fixture", "T-1", _roster(), specs_dir=root / "specs", at=commit, run=run,
         session_run=session, tracker=FakeTracker(), push_factory=lambda: None)

    assert not git.having("fetch")
    assert ["git", "worktree", "add", "--no-track", ".worktrees/fixture-t-1",
            "-b", "feat/fixture-t-1", commit] in git.calls


@pytest.mark.parametrize(("slug", "task_id"), [("fixture", "T-404"), ("absent", "T-1")])
def test_sc5_a_commit_without_the_spec_or_the_task_is_refused_before_any_worktree(
    checkout: tuple[Path, str], slug: str, task_id: str,
) -> None:
    """SC-5: a missing task or spec at the commit → refused; no worktree exists."""
    root, commit = checkout
    _, session = _session({"status": "completed", "detail": "never"})
    with pytest.raises(UnknownTaskError):
        work(slug, task_id, _roster(), specs_dir=root / "specs", at=commit,
             session_run=session, tracker=FakeTracker(), push_factory=lambda: None)
    assert not (root / ".worktrees").exists()
    assert _git(root, "worktree", "list").count("\n") == 0  # only the checkout itself


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "specs" / "fixture"
    d.mkdir(parents=True)
    (d / "tasks.md").write_text(_TASKS_MD, encoding="utf-8")
    (d / "spec.md").write_text(_SPEC_MD, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


# The commands `work()` issued before this change, for a completed session
# on a task with no worktree or branch left behind (recorded at 25a0cbd).
_BEFORE = [
    ["git", "branch", "--list", "feat/fixture-t-1"],
    ["git", "fetch", "origin", "main"],
    ["git", "rev-parse", "--path-format=absolute", "--git-path", "info/exclude"],
    ["git", "worktree", "add", "--no-track", ".worktrees/fixture-t-1", "-b",
     "feat/fixture-t-1", "origin/main"],
    ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
    ["git", "-c", "core.hooksPath=/dev/null", "-C", ".worktrees/fixture-t-1",
     "merge-base", "origin/main", "HEAD"],
    ["git", "-c", "core.hooksPath=/dev/null", "-C", ".worktrees/fixture-t-1",
     "diff", "--name-status", "--no-renames", "-z", "", "HEAD"],
    ["git", "-c", "core.hooksPath=/dev/null", "-C", ".worktrees/fixture-t-1",
     "rev-list", "--count", "origin/main..HEAD"],
    ["git", "-c", "core.hooksPath=/dev/null", "-C", ".worktrees/fixture-t-1",
     "push", "-u", "origin", "feat/fixture-t-1"],
    ["gh", "pr", "create", "--head", "feat/fixture-t-1",
     "--title", "feat: T-1 Build the widget (fixture)",
     "--body", ("Implements **T-1** from `specs/fixture/tasks.md` — authored by a worker "
                "agent session (ADR 0004).\n\nSatisfies: SC-1, SC-2\n\nSession summary: d\n\n"
                "🤖 Worker agent PR — gated by the cite-the-test validator (ADR 0005); the "
                "human is author of record.")],
    ["git", "-c", "core.hooksPath=/dev/null", "worktree", "remove", "--force",
     ".worktrees/fixture-t-1"],
]


def test_sc18_with_no_commit_work_issues_the_commands_it_issued_before(repo: Path) -> None:
    """SC-18: no `at`, nothing left behind → the very command list of before."""
    git = _GitGh()
    _, session = _session({"status": "completed", "detail": "d"})
    work("fixture", "T-1", _roster(), specs_dir=repo / "specs", run=git, session_run=session)
    assert git.calls == _BEFORE


def test_sc18_an_existing_worktree_or_branch_is_still_refused(repo: Path) -> None:
    """SC-18: a worktree or a branch left behind is refused; no session starts."""
    record, session = _session({"status": "completed", "detail": "d"})
    (repo / ".worktrees" / "fixture-t-1").mkdir(parents=True)
    with pytest.raises(WorktreeError, match="worktree already exists"):
        work("fixture", "T-1", _roster(), specs_dir=repo / "specs", run=_GitGh(),
             session_run=session)
    (repo / ".worktrees" / "fixture-t-1").rmdir()

    def branch_left(args: Sequence[str]) -> str:
        return "  feat/fixture-t-1\n" if list(args[:3]) == ["git", "branch", "--list"] else ""

    with pytest.raises(WorktreeError, match="branch already exists"):
        work("fixture", "T-1", _roster(), specs_dir=repo / "specs", run=branch_left,
             session_run=session)
    assert record == []


def test_the_handoff_note_is_excluded_beside_the_result_file(tmp_path: Path) -> None:
    """The exclude file lists `HANDOFF.md` and the commit-message file beside
    the result file, each once."""
    exclude = tmp_path / "info" / "exclude"
    exclude.parent.mkdir()
    exclude.write_text(".worker-result.json\n", encoding="utf-8")
    def run(args: Sequence[str]) -> str:
        return str(exclude)

    worktree._ignore_result_file(run)
    worktree._ignore_result_file(run)
    lines = exclude.read_text(encoding="utf-8").splitlines()
    assert lines == [".worker-result.json", "HANDOFF.md", ".worker-commit-msg"]
    assert worktree.HANDOFF_FILE == handoff.HANDOFF_FILE
