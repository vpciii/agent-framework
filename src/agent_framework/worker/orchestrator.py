"""The worker lifecycle: brief → worktree → session → result → handoff.

One invocation runs one task (parallelism is the caller running two —
isolation makes that safe). Retry policy is deliberately absent: that is
chief territory; this slice fails loudly once.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..errors import SessionTimeoutError
from ..proc import Runner, run_command
from ..project import DEFAULTS, ProjectConfig
from ..roster import Roster
from .brief import build_brief, parse_task
from .handoff import open_pr, write_escalation
from .session import SessionRunner, run_claude, run_session
from .types import Escalated, PrOpened, TimedOut, WorkerOutcome
from .worktree import create_worktree, remove_worktree

logger = logging.getLogger(__name__)


def work(
    spec_slug: str,
    task_id: str,
    roster: Roster,
    *,
    timeout_s: float = 1800,
    specs_dir: Path = Path("specs"),
    project: ProjectConfig = DEFAULTS,
    session_args: tuple[str, ...] = (),
    run: Runner = run_command,
    session_run: SessionRunner = run_claude,
) -> WorkerOutcome:
    """Dispatch one task to one headless session; return its outcome."""
    task = parse_task(spec_slug, task_id, specs_dir=specs_dir)
    brief = build_brief(task, project)
    logger.info("worker %s/%s: brief built (%d criteria)", spec_slug, task_id, len(task.criteria))

    worktree, branch = create_worktree(task, run=run)
    logger.info("worker %s/%s: worktree %s on %s", spec_slug, task_id, worktree, branch)

    model = roster.resolve("worker").model
    logger.info("worker %s/%s: session start (model=%s, timeout=%ss)",
                spec_slug, task_id, model, timeout_s)
    try:
        result = run_session(
            brief, worktree,
            model=model, timeout_s=timeout_s,
            session_args=session_args, run=session_run,
        )
    except SessionTimeoutError:
        logger.info("worker %s/%s: TIMED OUT — worktree preserved at %s",
                    spec_slug, task_id, worktree)
        return TimedOut(worktree_path=str(worktree))

    if result.status == "escalated":
        artifact = write_escalation(task, result, specs_dir=specs_dir)
        logger.info("worker %s/%s: ESCALATED → %s (worktree preserved)",
                    spec_slug, task_id, artifact)
        return Escalated(artifact_path=str(artifact), detail=result.detail)

    url = open_pr(task, result, worktree, branch, run=run)
    remove_worktree(worktree, run=run)
    logger.info("worker %s/%s: PR OPENED %s", spec_slug, task_id, url)
    return PrOpened(url=url, branch=branch, task_id=task_id)
