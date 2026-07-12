"""Worktree isolation: one task, one fresh tree, one fresh branch.

Deterministic derivation from the spec slug + task id (SC-6) means two
concurrent invocations for different tasks cannot collide, and the same
task always lands in the same place. Collisions fail loudly — no silent
reuse of a stale tree or branch.

Note: trees are keyed by `<slug>-<task-id>` (not the plan's bare task id
sketch) — task ids repeat across specs, and isolation must hold globally.
"""

from __future__ import annotations

from pathlib import Path

from ..errors import WorktreeError
from ..proc import Runner, run_command
from .brief import branch_name
from .types import TaskSpec

WORKTREES_DIR = Path(".worktrees")


def derive(task: TaskSpec) -> tuple[Path, str]:
    """The deterministic (worktree path, branch) for a task."""
    key = f"{task.spec_slug}-{task.task_id.lower()}"
    return WORKTREES_DIR / key, branch_name(task)


def create_worktree(task: TaskSpec, *, run: Runner = run_command) -> tuple[Path, str]:
    """Create the task's fresh worktree + branch; loud on any collision."""
    path, branch = derive(task)
    if path.exists():
        raise WorktreeError(f"worktree already exists: {path} — remove it or finish the task")
    if run(["git", "branch", "--list", branch]).strip():
        raise WorktreeError(f"branch already exists: {branch} — no silent reuse")
    run(["git", "worktree", "add", str(path), "-b", branch])
    return path, branch


def remove_worktree(path: Path, *, run: Runner = run_command) -> None:
    """Clean up after a successful push (failures keep their tree, by design)."""
    run(["git", "worktree", "remove", str(path)])
