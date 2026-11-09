"""The worker lifecycle: brief → worktree → session → result → handoff check → handoff.

One invocation runs one task (parallelism is the caller running two —
isolation makes that safe). Retry policy is deliberately absent: that is
chief territory; this slice fails loudly once.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable, Mapping
from pathlib import Path

from ..alerts import GhIssueTracker, IssueTracker, Push, notify, push_from_env
from ..errors import SessionTimeoutError
from ..proc import Runner, run_command
from ..project import DEFAULTS, ProjectConfig
from ..roster import Roster
from .brief import build_brief, parse_task
from .confinement import profile_args, session_env
from .handoff import open_pr, write_escalation, write_handoff_note
from .handoff_check import check_handoff
from .session import SessionRunner, run_claude, run_session
from .types import Escalated, HandoffRefused, PrOpened, TimedOut, WorkerOutcome
from .worktree import create_worktree, remove_worktree

logger = logging.getLogger(__name__)


def _specs_root(specs_dir: Path) -> str:
    """The specs directory as a repository-relative POSIX path."""
    try:
        return specs_dir.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return specs_dir.name


def _read_roots(run: Runner) -> tuple[str, ...]:
    """The repository's own directories: its root, and its git directory when
    that lies outside the root (the dispatching checkout is itself a linked
    worktree). The only home-directory paths a session reads undeclared."""
    root = Path.cwd().resolve()
    roots = [str(root)]
    try:
        common = run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"]).strip()
    except RuntimeError:
        common = ""
    if common and not Path(common).is_relative_to(root):
        roots.append(common)
    return tuple(roots)


def work(
    spec_slug: str,
    task_id: str,
    roster: Roster,
    *,
    timeout_s: float = 1800,
    specs_dir: Path = Path("specs"),
    project: ProjectConfig = DEFAULTS,
    environ: Mapping[str, str] = os.environ,
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
    # The confinement profile (ADR 0007): computed here from project config,
    # never taken from the caller.
    profile = profile_args(project, _read_roots(run))
    env = session_env(project, environ)
    logger.info(
        "worker %s/%s: session start (model=%s, timeout=%ss; confined: "
        "%d network host(s), %d extra writable path(s), %d extra readable path(s), "
        "%d environment variable(s))",
        spec_slug, task_id, model, timeout_s, len(project.session_network),
        len(project.session_write_paths), len(project.session_read_paths), len(env),
    )
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
            profile=profile, env=env, run=session_run,
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

    # The handoff check (ADR 0007): code decides what may leave the machine.
    findings = check_handoff(worktree, project, specs_root=_specs_root(specs_dir), run=run)
    if findings:
        for f in findings:
            logger.info("worker %s/%s: handoff finding — %s: %s (%s)",
                        spec_slug, task_id, f.rule, f.path, f.detail)
        listing = "\n".join(f"- **{f.rule}** `{f.path}` — {f.detail}" for f in findings)
        alerts = alert(
            "refused", f"{task_id} of {spec_slug}: handoff refused",
            "The session finished, but its commits may not be handed back. Nothing "
            f"was pushed and no pull request was opened.\n\n{listing}\n\n"
            f"Worktree preserved at `{worktree}`.",
        )
        logger.info("worker %s/%s: HANDOFF REFUSED (%d finding(s)) — worktree preserved at %s",
                    spec_slug, task_id, len(findings), worktree)
        return HandoffRefused(worktree_path=str(worktree), findings=findings, alerts=alerts)

    url = open_pr(task, result, worktree, branch, run=run)
    remove_worktree(worktree, run=run)
    logger.info("worker %s/%s: PR OPENED %s", spec_slug, task_id, url)
    return PrOpened(url=url, branch=branch, task_id=task_id)
