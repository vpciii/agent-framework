"""The worker lifecycle: brief → worktree → session → result → handoff.

One invocation runs one task (parallelism is the caller running two —
isolation makes that safe). Retry policy is deliberately absent: that is
chief territory; this slice fails loudly once.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path

from ..alerts import GhIssueTracker, IssueTracker, Push, notify, push_from_env
from ..errors import SessionTimeoutError
from ..proc import Runner, run_command
from ..project import DEFAULTS, ProjectConfig
from ..roster import Roster
from .brief import build_brief, parse_task
from .handoff import open_pr, write_escalation, write_handoff_note
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
    tracker: IssueTracker | None = None,
    push_factory: Callable[[], Push | None] = push_from_env,
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
    def alert(kind: str, title: str, body: str) -> tuple[str, ...]:
        # A failed notification never changes the outcome (R-7): notify never raises.
        report = notify(
            kind, f"{spec_slug}/{task_id}", title, body, f"{title}.",
            tracker=tracker or GhIssueTracker(run), push=push_factory(),
        )
        logger.info("worker %s/%s: %s alert — %s", spec_slug, task_id, kind, "; ".join(report.lines()))
        return report.lines()

    started = time.monotonic()
    try:
        result = run_session(
            brief, worktree,
            model=model, timeout_s=timeout_s,
            session_args=session_args, run=session_run,
        )
    except SessionTimeoutError:
        note = write_handoff_note(task, worktree, budget_s=timeout_s,
                                  elapsed_s=time.monotonic() - started, run=run)
        logger.info("worker %s/%s: TIMED OUT — worktree preserved at %s, handoff note %s",
                    spec_slug, task_id, worktree, note)
        alerts = alert(
            "timeout", f"{task_id} of {spec_slug} timed out",
            f"The worker session hit its {timeout_s:.0f}s budget and was stopped.\n\n"
            f"Worktree preserved at `{worktree}`; handoff note at `{note}`.",
        )
        return TimedOut(worktree_path=str(worktree), handoff_path=str(note), alerts=alerts)

    if result.status == "escalated":
        artifact = write_escalation(task, result, specs_dir=specs_dir)
        logger.info("worker %s/%s: ESCALATED → %s (worktree preserved)",
                    spec_slug, task_id, artifact)
        alerts = alert(
            "escalation", f"{task_id} of {spec_slug} needs a decision",
            f"{result.detail}\n\nEscalation artifact: `{artifact}`.",
        )
        return Escalated(artifact_path=str(artifact), detail=result.detail, alerts=alerts)

    url = open_pr(task, result, worktree, branch, run=run)
    remove_worktree(worktree, run=run)
    logger.info("worker %s/%s: PR OPENED %s", spec_slug, task_id, url)
    return PrOpened(url=url, branch=branch, task_id=task_id)
