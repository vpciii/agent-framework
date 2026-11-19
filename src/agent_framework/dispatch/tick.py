"""One pass of the dispatch tick (specs/dispatch-from-issue, the plan's *One pass*).

In order: take the lock; recover a run that died with the pass that started
it; bring the checkout to `origin/main` by fast-forward (refusing a changed,
diverged or nested checkout, and asking to start again once if it moved);
read the configuration; list the open `dispatch` issues; take the oldest;
read the named spec's `tasks.md` at the fetched commit; `decide`. A refused
issue loses its `dispatch` label, gets one comment and is closed. An accepted
issue is claimed by removing its label, written into the lock file as the run
in progress, run through `work()` exactly as a hand dispatch runs it (but at
the fetched commit, starting again if need be, with the session's process
group recorded as it starts), then answered with one comment, closed, and its
run marked finished.

Every step logs one line. A fetch or a listing that fails is a failed pass; a
checkout that cannot be used is a refused one; anything else that ends the
pass early (another pass running, dispatch off, no issue) is a completed one.

When it stops working (R-13, R-18 to R-20): a run that raised an error raises
a `failed` alert naming its kind; a configured CLI version the installed CLI
does not report starts no session and raises one; failed passes are counted
in `.worktrees/dispatch-state.json` and the third in a row raises one; a
completed pass sends the heartbeat. The alerts the tick raises about itself
reach the phone once per condition, not once per pass.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from functools import partial
from pathlib import Path
from typing import Protocol

from ..alerts import GhIssueTracker, IssueTracker, Push, notify, push_from_env
from ..errors import ProjectConfigError, WorkerError
from ..proc import Runner, run_command
from ..project import ProjectConfig, load_project_config
from ..roster import Roster
from ..worker.brief import parse_task_at
from ..worker.handoff import write_handoff_note
from ..worker.orchestrator import RECORDS_DIR, work
from ..worker.session import (
    DEFAULT_SPEND_LIMIT_USD,
    claude_code_version,
    last_line,
    run_claude,
    stop_group,
)
from ..worker.types import TaskSpec, WorkerOutcome
from ..worker.worktree import BASE_BRANCH, BASE_REF, BASE_REMOTE, WORKTREES_DIR
from . import lock
from .issue import Accepted, Issue, decide, oldest, parse_title
from .report import (
    FAILED_PASSES_ALERT_AT,
    CheckoutRefusal,
    checkout_alert,
    count_failed_pass,
    dead_run_comment,
    failed_passes_alert,
    failure_alert,
    refusal_comment,
    reported_version,
    reset_failed_passes,
    run_comment,
    send_heartbeat,
    version_alert,
)

logger = logging.getLogger(__name__)

LABEL = "dispatch"
# What is asked of the tracker about an issue, and nothing else: never the
# body, the comments or the labels (R-6).
LIST_FIELDS = "number,title,author,createdAt"
# The kind and key every refused-checkout alert is raised under: one issue.
CHECKOUT_ALERT = ("failed", "dispatch/checkout")
# Likewise for a CLI version mismatch and for failed passes in a row.
CLI_VERSION_ALERT = ("failed", "dispatch/cli-version")
FAILED_PASSES_ALERT = ("failed", "dispatch/failed-passes")
# The failed-pass count, beside the lock file (R-19).
STATE_FILE = WORKTREES_DIR / "dispatch-state.json"

WorkFn = Callable[..., WorkerOutcome]
# `run_claude`'s shape: the session seam plus `on_start`, a keyword told the
# session's process group as it starts.
StartingSessionRunner = Callable[..., None]


class PassResult(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    REFUSED = "refused"  # the checkout could not be used (R-8)
    RESTART = "restart"  # the checkout moved: start the command again, once


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
    session_run: StartingSessionRunner = run_claude,
    alert_tracker: IssueTracker | None = None,
    push_factory: Callable[[], Push | None] = push_from_env,
    heartbeat: Callable[[], str] = send_heartbeat,
    restarted: bool = False,
) -> PassResult:
    """One pass; held under the lock for its whole length (R-1, R-5).

    `limits`, `work_fn` and `session_run` are what a run is started with; a
    pass that only refuses never uses them. A pass whose fast-forward moved
    the checkout returns `RESTART` before reading anything else, unless
    `restarted` marks it as the pass the command already started again.
    A completed pass then sends `heartbeat`, whose outcome is only logged.
    """
    with lock.hold(repo / lock.LOCK_FILE) as taken:
        if not taken:
            logger.info("dispatch: another pass is running — nothing to do")
            result = PassResult.COMPLETED
        else:
            logger.info("dispatch: lock taken")
            p = _Pass(tracker, repo, run, limits, work_fn, session_run, alert_tracker,
                      push_factory)
            result = _steps(p, restarted)
            p.count(result)
    if result is PassResult.COMPLETED:
        logger.info("dispatch: heartbeat — %s", heartbeat())
    return result


def _steps(p: _Pass, restarted: bool) -> PassResult:
    if not p.recover():
        return PassResult.FAILED
    refused = p.checkout()
    if refused is not None:
        return refused
    if p.moved and not restarted:
        logger.info("dispatch: the checkout moved — starting again on the fetched code")
        return PassResult.RESTART
    return _locked_pass(p)


@dataclass
class _Pass:
    tracker: DispatchTracker
    repo: Path
    run: Runner
    limits: Limits
    work_fn: WorkFn
    session_run: StartingSessionRunner
    alert_tracker: IssueTracker | None
    push_factory: Callable[[], Push | None]
    moved: bool = False

    @property
    def lock_file(self) -> Path:
        return self.repo / lock.LOCK_FILE

    def git(self, *args: str) -> str:
        return self.run(["git", "-C", str(self.repo), *args])

    def alert(self, kind: str, key: str, title: str, body: str,
              *, quiet: bool = False) -> tuple[str, ...]:
        # notify never raises: a failed channel is in its report, not the pass's.
        # `quiet`: a condition the tick raises on every pass is pushed once.
        report = notify(kind, key, title, body, f"{title}.",
                        tracker=self.alert_tracker or GhIssueTracker(self.run),
                        push=self.push_factory(), update_existing=True,
                        quiet_if_open=quiet)
        logger.info("dispatch: %s alert — %s", kind, "; ".join(report.lines()))
        return report.lines()

    def count(self, result: PassResult) -> None:
        """R-19: a failed pass adds one to the count, and the third in a row
        alerts; a completed pass starts it again. Others leave it alone."""
        state = self.repo / STATE_FILE
        if result is PassResult.COMPLETED:
            reset_failed_passes(state)
        elif result is PassResult.FAILED:
            n = count_failed_pass(state)
            logger.info("dispatch: %d failed pass(es) in a row", n)
            if n == FAILED_PASSES_ALERT_AT:
                self.alert(*FAILED_PASSES_ALERT, *failed_passes_alert(n), quiet=True)

    def recover(self) -> bool:
        """Step 2 (R-15): a run recorded and not finished died with its pass —
        the lock is ours, so no process holds it. Stop what is left of its
        session, write its handoff note, alert, answer its issue, clear the
        record. False when the issue could not be answered: the record is
        then kept, and the next pass tries again."""
        dead = lock.read_run(self.lock_file)
        if dead is None or dead.finished:
            return True
        logger.info("dispatch: #%d's run (%s %s) died unfinished — recovering",
                    dead.issue, dead.spec, dead.task)
        if dead.session_pgid is not None:
            stop_group(dead.session_pgid)
            logger.info("dispatch: process group %d stopped", dead.session_pgid)
        note = write_handoff_note(self._task(dead), self.repo / dead.worktree,
                                  budget_s=self.limits.timeout_s,
                                  elapsed_s=dead.elapsed_s(), run=self.run)
        logger.info("dispatch: handoff note written to %s", note)
        alerts = self.alert(
            "timeout", f"{dead.spec}/{dead.task}", f"{dead.task} of {dead.spec} stopped",
            "The worker run stopped without finishing: the dispatch pass that started it "
            f"ended first.\n\nWorktree preserved at `{dead.worktree}`; handoff note at "
            f"`{Path(dead.worktree) / note.name}`.",
        )
        try:
            self.tracker.comment(dead.issue, dead_run_comment(alerts))
            self.tracker.close(dead.issue)
        except Exception as e:  # noqa: BLE001 — reported as a failed pass, never raised
            logger.error("dispatch: FAILED — cannot answer #%d: %s", dead.issue, e)
            return False
        lock.write_run(None, self.lock_file)
        logger.info("dispatch: #%d commented and closed; the record cleared", dead.issue)
        return True

    def _task(self, dead: lock.Run) -> TaskSpec:
        try:
            return parse_task_at(dead.spec, dead.task, BASE_REF, repo=self.repo, run=self.run)
        except WorkerError:  # the note still says what it can without the criteria
            return TaskSpec(dead.spec, dead.task, (), "", {}, "")

    def checkout(self) -> PassResult | None:
        """Step 3 (R-8): the checkout at `origin/main` by fast-forward. None
        when it is there; otherwise how the pass ends."""
        try:
            self.run(["git", "-C", str(self.repo.resolve().parent),
                      "rev-parse", "--show-toplevel"])
        except RuntimeError:
            pass  # the parent directory is in no working tree
        else:
            return self.refuse(CheckoutRefusal.NESTED)
        try:
            if self.git("status", "--porcelain", "--untracked-files=no").strip():
                return self.refuse(CheckoutRefusal.CHANGED)
            self.git("fetch", BASE_REMOTE, BASE_BRANCH)
            commit = self.git("rev-parse", "--verify", f"{BASE_REF}^{{commit}}").strip()
            head = self.git("rev-parse", "--verify", "HEAD^{commit}").strip()
        except RuntimeError as e:
            logger.error("dispatch: FAILED — cannot fetch %s: %s", BASE_REF, e)
            return PassResult.FAILED
        if head != commit:
            try:
                self.git("merge-base", "--is-ancestor", head, commit)
                self.git("reset", "-q", "--keep", commit)
            except RuntimeError:
                return self.refuse(CheckoutRefusal.DIVERGED)
            self.moved = True
        logger.info("dispatch: the checkout is at %s (%s)", BASE_REF, commit[:12])
        return None

    def refuse(self, reason: CheckoutRefusal) -> PassResult:
        logger.error("dispatch: REFUSED — the checkout cannot be used: %s", reason.value)
        self.alert(*CHECKOUT_ALERT, *checkout_alert(reason, str(self.repo.resolve())),
                   quiet=True)
        return PassResult.REFUSED


def _locked_pass(p: _Pass) -> PassResult:
    """Steps 4 to 7: the configuration, the issues, the decision."""
    tracker, repo, run = p.tracker, p.repo, p.run
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
    commit = run([*git, "rev-parse", "--verify", f"{BASE_REF}^{{commit}}"]).strip()

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
        return _claim_and_run(p, issue.number, decision, commit=commit, project=project)

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
    p: _Pass, number: int, task: Accepted, *, commit: str, project: ProjectConfig
) -> PassResult:
    """Claim the issue, run its task, answer it (R-4, R-9, R-10, R-11).

    `work()` gets what a hand dispatch gives it — the roster, the limits and
    the project's configuration — plus only the fetched commit,
    `existing="continue"`, and the session seam told to record the session's
    process group in the lock file (R-15); never any text of the tick's own.
    """
    tracker, repo, limits = p.tracker, p.repo, p.limits
    wanted = project.dispatch.worker_cli_version
    if wanted is not None:
        installed = reported_version(claude_code_version(p.run))
        if installed != wanted:  # R-18: no claim, no session; the issue waits
            logger.error("dispatch: the worker CLI reports %s, not the configured %s — "
                         "no session", installed, wanted)
            p.alert(*CLI_VERSION_ALERT, *version_alert(wanted, installed), quiet=True)
            return PassResult.COMPLETED
        logger.info("dispatch: the worker CLI is the configured %s", wanted)
    try:
        tracker.remove_label(number)
    except Exception as e:  # noqa: BLE001 — an unclaimed issue starts nothing (R-4)
        logger.error("dispatch: FAILED — cannot claim #%d: %s", number, e)
        return PassResult.FAILED
    logger.info("dispatch: #%d claimed — label removed", number)

    lock_file = p.lock_file
    worktree = WORKTREES_DIR / f"{task.spec_slug}-{task.task_id.lower()}"
    started = lock.Run(
        pid=os.getpid(), started=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        issue=number, spec=task.spec_slug, task=task.task_id, worktree=worktree.as_posix(),
    )
    lock.write_run(started, lock_file)
    logger.info("dispatch: #%d run written to the lock file", number)

    def record_group(pgid: int) -> None:
        nonlocal started
        started = replace(started, session_pgid=pgid)
        lock.write_run(started, lock_file)
        logger.info("dispatch: #%d session's process group %d recorded", number, pgid)

    records = repo / RECORDS_DIR
    pattern = f"{task.spec_slug}-{task.task_id.lower()}-*.jsonl"
    before = set(records.glob(pattern))
    try:
        outcome = p.work_fn(
            task.spec_slug, task.task_id, Roster.from_file(repo / limits.roster),
            timeout_s=limits.timeout_s, spend_limit_usd=limits.spend_limit_usd,
            project=project, at=commit, existing="continue",
            session_run=partial(p.session_run, on_start=record_group),
        )
    except Exception as e:  # noqa: BLE001 — a run that raises is still answered
        logger.error("dispatch: #%d run ended in an error — %s", number, e)
        record = max(set(records.glob(pattern)) - before, default=None)
        alerts = p.alert("failed", f"{task.spec_slug}/{task.task_id}", *failure_alert(
            task.spec_slug, task.task_id, str(e), record,
            last_line(record) if record is not None else ""))
        comment = run_comment(None, alerts)
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
