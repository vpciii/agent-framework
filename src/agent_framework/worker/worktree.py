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
from .session import RESULT_FILE
from .types import TaskSpec

WORKTREES_DIR = Path(".worktrees")
# What a worker's tree is cut from and its work is measured against: the
# remote's main, fetched at dispatch. Never local `main`, which is only as
# fresh as the dispatching checkout's last pull.
BASE_REMOTE = "origin"
BASE_BRANCH = "main"
BASE_REF = f"{BASE_REMOTE}/{BASE_BRANCH}"
# Every git command the orchestrator runs for a worktree *after* a session
# has been in it carries this: the session could have written a hook, and
# the orchestrator must never execute one (ADR 0007, worker-confinement R-9).
NO_HOOKS = ("-c", "core.hooksPath=/dev/null")


def derive(task: TaskSpec) -> tuple[Path, str]:
    """The deterministic (worktree path, branch) for a task."""
    key = f"{task.spec_slug}-{task.task_id.lower()}"
    return WORKTREES_DIR / key, branch_name(task)


def _ignore_result_file(run: Runner) -> None:
    """Record RESULT_FILE in the repository's exclude file, once.

    The exclude file is shared by every worktree and tracked by nothing, so
    the result file is ignored without touching any tracked file.
    """
    located = run(
        ["git", "rev-parse", "--path-format=absolute", "--git-path", "info/exclude"]
    ).strip()
    if not located:
        raise WorktreeError(
            "git reported no location for the exclude file (info/exclude) — "
            f"cannot ignore {RESULT_FILE}, so no worktree was created"
        )
    exclude = Path(located)
    existing = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    if RESULT_FILE in existing.splitlines():
        return
    exclude.parent.mkdir(parents=True, exist_ok=True)
    if existing and not existing.endswith("\n"):
        existing += "\n"
    exclude.write_text(existing + RESULT_FILE + "\n", encoding="utf-8")


def create_worktree(task: TaskSpec, *, run: Runner = run_command) -> tuple[Path, str]:
    """Create the task's fresh worktree + branch; loud on any collision."""
    path, branch = derive(task)
    if path.exists():
        raise WorktreeError(f"worktree already exists: {path} — remove it or finish the task")
    if run(["git", "branch", "--list", branch]).strip():
        raise WorktreeError(f"branch already exists: {branch} — no silent reuse")
    # Cut from the freshly fetched remote main, never from the orchestrator's
    # checkout or its local `main` — a worker PR must contain only its own
    # work, on top of what is actually merged.
    try:
        run(["git", "fetch", BASE_REMOTE, BASE_BRANCH])
    except RuntimeError as e:
        raise WorktreeError(
            f"cannot fetch {BASE_BRANCH} from {BASE_REMOTE} — refusing to cut the "
            f"worktree from a possibly stale local {BASE_BRANCH}: {e}"
        ) from None
    _ignore_result_file(run)
    # --no-track: the branch is pushed with `-u origin <branch>` at handoff;
    # it must not track main in the meantime.
    run(["git", "worktree", "add", "--no-track", str(path), "-b", branch, BASE_REF])
    return path, branch


def remove_worktree(path: Path, *, run: Runner = run_command) -> None:
    """Clean up after a successful push (failures keep their tree, by design).

    --force is required and safe here: the tree always contains the
    untracked `.worker-result.json` (the result contract), and this is
    only called after the branch is pushed — nothing unpushed is lost.
    """
    run(["git", *NO_HOOKS, "worktree", "remove", "--force", str(path)])
