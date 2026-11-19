"""One pass of the dispatch tick (specs/dispatch-from-issue, the plan's *One pass*).

In order: take the lock; read the configuration; fetch `origin/main` and
resolve the commit; list the open `dispatch` issues; take the oldest; read
the named spec's `tasks.md` at that commit; `decide`. A refused issue loses
its `dispatch` label, gets one comment and is closed. An accepted issue is
claimed by removing its label, written into the lock file as the run in
progress, run through `work()` exactly as a hand dispatch runs it (but at
the fetched commit, starting again if need be), then answered with one
comment, closed, and its run marked finished.

Every step logs one line. A fetch or a listing that fails is a failed pass;
anything else that ends the pass early (another pass running, dispatch off,
no issue) is a completed one.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from ..errors import ProjectConfigError
from ..proc import Runner, run_command
from ..project import ProjectConfig, load_project_config
from ..roster import Roster
from ..worker.orchestrator import work
from ..worker.session import DEFAULT_SPEND_LIMIT_USD
from ..worker.types import WorkerOutcome
from ..worker.worktree import BASE_BRANCH, BASE_REF, BASE_REMOTE, WORKTREES_DIR
from . import lock
from .issue import Accepted, Issue, decide, oldest, parse_title
from .report import refusal_comment, run_comment

logger = logging.getLogger(__name__)

LABEL = "dispatch"
# What is asked of the tracker about an issue, and nothing else: never the
# body, the comments or the labels (R-6).
LIST_FIELDS = "number,title,author,createdAt"

WorkFn = Callable[..., WorkerOutcome]


class PassResult(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class Limits:
    """What the command line gives a run: the worker's own defaults."""

    roster: Path = Path("agent-framework.toml")
    timeout_s: float = 1800
    spend_limit_usd: float = DEFAULT_SPEND_LIMIT_USD


DEFAULT_LIMITS = Limits()


class DispatchTracker(Protocol):
    """The dispatch issues, as the tick sees and answers them."""

    def list_open(self) -> list[Issue]: ...
    def remove_label(self, number: int) -> None: ...
    def comment(self, number: int, body: str) -> None: ...
    def close(self, number: int) -> None: ...


class GhDispatchTracker:
    """A `DispatchTracker` over the `gh` CLI, through the shared subprocess seam."""

    def __init__(self, run: Runner = run_command) -> None:
        self._run = run

    def list_open(self) -> list[Issue]:
        raw = self._run(["gh", "issue", "list", "--state", "open", "--label", LABEL,
                         "--json", LIST_FIELDS, "--limit", "100"])
        return [
            Issue(
                number=int(item["number"]),
                title=str(item["title"]),
                author=str(item["author"]["login"]),
                opened=datetime.fromisoformat(str(item["createdAt"])),
            )
            for item in json.loads(raw or "[]")
        ]

    def remove_label(self, number: int) -> None:
        self._run(["gh", "issue", "edit", str(number), "--remove-label", LABEL])

    def comment(self, number: int, body: str) -> None:
        self._run(["gh", "issue", "comment", str(number), "--body", body])

    def close(self, number: int) -> None:
        self._run(["gh", "issue", "close", str(number)])


def run_pass(
    tracker: DispatchTracker,
    *,
    limits: Limits = DEFAULT_LIMITS,
    repo: Path = Path("."),
    run: Runner = run_command,
    work_fn: WorkFn = work,
) -> PassResult:
    """One pass; held under the lock for its whole length (R-1, R-5).

    `limits` and `work_fn` are what a run is started with; a pass that only
    refuses never uses them.
    """
    with lock.hold(repo / lock.LOCK_FILE) as taken:
        if not taken:
            logger.info("dispatch: another pass is running — nothing to do")
            return PassResult.COMPLETED
        logger.info("dispatch: lock taken")
        return _locked_pass(tracker, repo=repo, run=run, limits=limits, work_fn=work_fn)


def _locked_pass(
    tracker: DispatchTracker, *, repo: Path, run: Runner, limits: Limits, work_fn: WorkFn
) -> PassResult:
    try:
        project = load_project_config(repo)
        config = project.dispatch
    except ProjectConfigError as e:
        logger.error("dispatch: cannot read the configuration — %s", e)
        return PassResult.FAILED
    if config.author is None:
        logger.info("dispatch: off — no [dispatch] author is configured")
        return PassResult.COMPLETED
    if not config.enabled:
        logger.info("dispatch: off — [dispatch] enabled is false")
        return PassResult.COMPLETED
    logger.info("dispatch: on for issues opened by the configured author")

    git = ["git", "-C", str(repo)]
    try:
        run([*git, "fetch", BASE_REMOTE, BASE_BRANCH])
        commit = run([*git, "rev-parse", "--verify", f"{BASE_REF}^{{commit}}"]).strip()
    except RuntimeError as e:
        logger.error("dispatch: FAILED — cannot fetch %s: %s", BASE_REF, e)
        return PassResult.FAILED
    logger.info("dispatch: %s is %s", BASE_REF, commit)

    try:
        issues = tracker.list_open()
    except Exception as e:  # noqa: BLE001 — any failure to list is a failed pass (R-19)
        logger.error("dispatch: FAILED — cannot list the open %s issues: %s", LABEL, e)
        return PassResult.FAILED
    issue = oldest(issues)
    if issue is None:
        logger.info("dispatch: no open %s issue", LABEL)
        return PassResult.COMPLETED
    logger.info("dispatch: %d open %s issue(s); the oldest is #%d", len(issues), LABEL,
                issue.number)

    tasks_text: str | None = None
    parsed = parse_title(issue.title) if issue.author == config.author else None
    if parsed is not None:
        try:
            tasks_text = run([*git, "show", f"{commit}:specs/{parsed[0]}/tasks.md"])
        except RuntimeError:
            tasks_text = None
    logger.info("dispatch: #%d — tasks.md %s at %s", issue.number,
                "read" if tasks_text is not None else "not read", commit[:12])

    decision = decide(issue, config, tasks_text)
    if isinstance(decision, Accepted):
        logger.info("dispatch: #%d accepted (%s %s)", issue.number,
                    decision.spec_slug, decision.task_id)
        return _claim_and_run(tracker, issue.number, decision, commit=commit, repo=repo,
                              project=project, limits=limits, work_fn=work_fn)

    logger.info("dispatch: #%d refused — %s", issue.number, decision.reason.value)
    try:
        tracker.remove_label(issue.number)
        tracker.comment(issue.number, refusal_comment(decision.reason))
        tracker.close(issue.number)
    except Exception as e:  # noqa: BLE001 — reported as a failed pass, never raised
        logger.error("dispatch: FAILED — cannot answer #%d: %s", issue.number, e)
        return PassResult.FAILED
    logger.info("dispatch: #%d label removed, commented and closed", issue.number)
    return PassResult.COMPLETED


def _claim_and_run(
    tracker: DispatchTracker,
    number: int,
    task: Accepted,
    *,
    commit: str,
    repo: Path,
    project: ProjectConfig,
    limits: Limits,
    work_fn: WorkFn,
) -> PassResult:
    """Claim the issue, run its task, answer it (R-4, R-9, R-10, R-11).

    `work()` gets what a hand dispatch gives it — the roster, the limits and
    the project's configuration — plus only the fetched commit and
    `existing="continue"`; never any seam or text of the tick's own.
    """
    try:
        tracker.remove_label(number)
    except Exception as e:  # noqa: BLE001 — an unclaimed issue starts nothing (R-4)
        logger.error("dispatch: FAILED — cannot claim #%d: %s", number, e)
        return PassResult.FAILED
    logger.info("dispatch: #%d claimed — label removed", number)

    lock_file = repo / lock.LOCK_FILE
    worktree = WORKTREES_DIR / f"{task.spec_slug}-{task.task_id.lower()}"
    started = lock.Run(
        pid=os.getpid(), started=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        issue=number, spec=task.spec_slug, task=task.task_id, worktree=worktree.as_posix(),
    )
    lock.write_run(started, lock_file)
    logger.info("dispatch: #%d run written to the lock file", number)

    try:
        outcome = work_fn(
            task.spec_slug, task.task_id, Roster.from_file(repo / limits.roster),
            timeout_s=limits.timeout_s, spend_limit_usd=limits.spend_limit_usd,
            project=project, at=commit, existing="continue",
        )
    except Exception as e:  # noqa: BLE001 — a run that raises is still answered
        logger.error("dispatch: #%d run ended in an error — %s", number, e)
        comment = run_comment(None)
    else:
        logger.info("dispatch: #%d run ended — %s", number, type(outcome).__name__)
        comment = run_comment(outcome)

    result = PassResult.COMPLETED
    try:
        tracker.comment(number, comment)
        tracker.close(number)
        logger.info("dispatch: #%d commented and closed", number)
    except Exception as e:  # noqa: BLE001 — reported as a failed pass, never raised
        logger.error("dispatch: FAILED — cannot answer #%d: %s", number, e)
        result = PassResult.FAILED
    lock.write_run(replace(started, finished=True), lock_file)
    logger.info("dispatch: #%d run marked finished", number)
    return result
