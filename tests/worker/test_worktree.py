"""Worktree isolation.

Verifies SC-6: distinct tasks derive distinct worktrees and branches;
the same task derives the same pair (deterministic). Plus the loud
collision paths.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from agent_framework.errors import WorktreeError
from agent_framework.worker.types import TaskSpec
from agent_framework.worker.worktree import create_worktree, derive


def _task(slug: str = "fixture", task_id: str = "T-1") -> TaskSpec:
    return TaskSpec(
        spec_slug=slug,
        task_id=task_id,
        criteria=("SC-1",),
        section="### section",
        criterion_texts={"SC-1": "text"},
        requirements="reqs",
    )


def test_sc6_distinct_tasks_derive_distinct_trees_and_branches() -> None:
    """SC-6: no shared mutable state between concurrent tasks — including
    equal task ids under different specs."""
    a = derive(_task(task_id="T-1"))
    b = derive(_task(task_id="T-2"))
    c = derive(_task(slug="other-spec", task_id="T-1"))

    paths = {a[0], b[0], c[0]}
    branches = {a[1], b[1], c[1]}
    assert len(paths) == 3 and len(branches) == 3

    # Deterministic: the same task always derives the same pair.
    assert derive(_task(task_id="T-1")) == a


def test_create_worktree_invokes_git_with_derived_pair(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def run(args: Sequence[str]) -> str:
        calls.append(list(args))
        return ""  # branch --list: empty → no collision

    import agent_framework.worker.worktree as wt

    task = _task()
    expected_path, expected_branch = derive(task)
    path, branch = create_worktree(task, run=run)

    assert (path, branch) == (expected_path, expected_branch)
    # Cut from the fetched remote main: a worker PR contains only its own work.
    assert ["git", "worktree", "add", "--no-track", str(expected_path), "-b", expected_branch, "origin/main"] in calls
    assert wt.WORKTREES_DIR.name == ".worktrees"


def test_create_worktree_collisions_fail_loudly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    task = _task()

    # Existing branch → loud error, no worktree command issued.
    def run_branch_exists(args: Sequence[str]) -> str:
        assert args[:2] == ["git", "branch"] or list(args[:2]) == ["git", "branch"]
        return "  feat/fixture-t-1\n"

    with pytest.raises(WorktreeError, match="branch already exists"):
        create_worktree(task, run=run_branch_exists)

    # Existing tree path → loud error before any git call.
    monkeypatch.chdir(tmp_path)
    path, _ = derive(task)
    path.mkdir(parents=True)
    with pytest.raises(WorktreeError, match="worktree already exists"):
        create_worktree(task, run=lambda args: "")


def test_remove_worktree_forces_past_the_result_file() -> None:
    """Regression (first live smoke, #31): the success path always has the
    untracked .worker-result.json, so a non-forced remove ALWAYS fails
    ("contains modified or untracked files") after an otherwise perfect run."""
    from agent_framework.worker.worktree import remove_worktree

    calls: list[list[str]] = []

    def run(args: Sequence[str]) -> str:
        calls.append(list(args))
        return ""

    remove_worktree(Path(".worktrees/x"), run=run)
    assert calls == [["git", "worktree", "remove", "--force", ".worktrees/x"]]


def _git(cwd: Path, *args: str) -> str:
    import subprocess

    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


@pytest.fixture
def stale_clone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    """A clone whose local `main` is one commit behind `origin/main` — the
    state of any checkout that has not pulled since the last merge."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    seed = tmp_path / "seed"
    _git(tmp_path, "clone", "-q", str(origin), str(seed))
    _git(seed, "commit", "-q", "--allow-empty", "-m", "first")
    _git(seed, "push", "-q", "origin", "HEAD:main")
    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(origin), str(clone))
    _git(seed, "commit", "-q", "--allow-empty", "-m", "merged upstream later")
    _git(seed, "push", "-q", "origin", "HEAD:main")
    monkeypatch.chdir(clone)
    return clone, _git(seed, "rev-parse", "HEAD")


def test_worktree_is_cut_from_the_remote_main_not_a_stale_local_one(
    stale_clone: tuple[Path, str],
) -> None:
    """Regression: the tree was cut from local `main`, so a checkout that had
    not pulled gave the worker stale code (found 2026-11-09 with this repo's
    own `main` 4 commits behind origin)."""
    clone, upstream_head = stale_clone
    assert _git(clone, "rev-parse", "main") != upstream_head  # the precondition

    path, _ = create_worktree(_task())

    assert _git(clone / path, "rev-parse", "HEAD") == upstream_head


def test_a_session_that_commits_nothing_is_caught_even_when_local_main_is_stale(
    stale_clone: tuple[Path, str],
) -> None:
    """Regression: "committed nothing" must be counted against the ref the
    tree was cut from; against a stale local `main` the upstream commits
    would pass for the session's own work."""
    from agent_framework.errors import SessionResultError
    from agent_framework.worker.handoff import open_pr
    from agent_framework.worker.types import SessionResult

    path, branch = create_worktree(_task())

    with pytest.raises(SessionResultError, match="committed nothing"):
        open_pr(_task(), SessionResult("completed", "did nothing"), path, branch)


def test_an_unreachable_remote_fails_loudly_before_any_tree_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No silent fallback to a possibly stale local `main`."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "first")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(WorktreeError, match="origin"):
        create_worktree(_task())
    assert not derive(_task())[0].exists()
