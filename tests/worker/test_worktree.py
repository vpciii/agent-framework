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
    assert ["git", "worktree", "add", str(expected_path), "-b", expected_branch] in calls
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
