"""What the dispatch tick writes back (specs/dispatch-from-issue).

Every comment is fixed wording plus values the code computed; none carries
text taken from an issue — not its title, body, comments, labels or author
(R-11, R-12). Here too: the one table that names a failed run's kind, the
`failed` alerts' wordings, the failed-pass count and the heartbeat.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from collections.abc import Callable, Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any

from ..worker.types import (
    Escalated,
    HandoffRefused,
    PrAlreadyOpen,
    PrOpened,
    SpendLimitReached,
    TimedOut,
    WorkerOutcome,
)
from .issue import Refusal

_REFUSALS: dict[Refusal, str] = {
    Refusal.OFF: "dispatch from an issue is switched off in this project's configuration.",
    Refusal.AUTHOR: "this issue was not opened by the account the project's configuration "
    "names.",
    Refusal.TITLE: "the title is not exactly `<spec-slug> <task-id>` "
    "(for example `dispatch-from-issue T-4`).",
    Refusal.UNKNOWN_SPEC: "no spec of that name is on `origin/main`.",
    Refusal.UNKNOWN_TASK: "that spec's `tasks.md` on `origin/main` has no such task.",
    Refusal.DONE: "that task is already marked done on `origin/main`.",
    Refusal.NO_CRITERION: "that task claims no success criterion.",
}


def refusal_comment(reason: Refusal) -> str:
    """The one comment a refused issue gets: why, by its reason code."""
    return (
        f"Refused — no worker run was started: {_REFUSALS[reason]}\n\n"
        f"Reason code: `{reason.value}`. This issue is closed; open a new one to try again."
    )


# The alert issue as `notify` reports it, e.g. "github issue: opened #12".
_ALERT_ISSUE = re.compile(r"^github issue: (?:opened|found|updated) (#[0-9]+)$")
_CLOSED = "This issue is closed."


def _alert(alerts: tuple[str, ...]) -> str:
    for line in alerts:
        m = _ALERT_ISSUE.match(line)
        if m is not None:
            return f"Alert: {m.group(1)}."
    return "No alert issue could be recorded; the worker's log has the details."


def run_comment(outcome: WorkerOutcome | None, alerts: tuple[str, ...] = ()) -> str:
    """The one comment an accepted issue gets once its run has ended; None
    is a run that raised an error, and `alerts` its `failed` alert's report.
    Names the pull request or the alert."""
    if isinstance(outcome, PrOpened):
        return f"The worker run opened a pull request: {outcome.url}\n\n{_CLOSED}"
    if isinstance(outcome, PrAlreadyOpen):
        return (
            "Refused — no worker run was started: this task's branch already has an "
            f"open pull request: {outcome.url}\n\n"
            f"Reason code: `pr-already-open`. {_CLOSED}"
        )
    if isinstance(outcome, Escalated):
        why = "ended in an escalation: it needs a decision. Nothing was pushed."
        alerts = outcome.alerts
    elif isinstance(outcome, SpendLimitReached):
        why = (f"reached its ${outcome.spend_limit_usd:.2f} spend limit and was stopped. "
               "The worktree and a handoff note are kept; a new dispatch issue resumes it.")
        alerts = outcome.alerts
    elif isinstance(outcome, TimedOut):
        why = ("hit its time budget and was stopped. The worktree and a handoff note are "
               "kept; a new dispatch issue resumes it.")
        alerts = outcome.alerts
    elif isinstance(outcome, HandoffRefused):
        why = ("finished, but its handoff was refused: nothing was pushed and no pull "
               "request was opened.")
        alerts = outcome.alerts
    else:
        return ("The worker run ended in an error: no pull request was opened.\n\n"
                f"{_alert(alerts)} {_CLOSED}")
    return f"The worker run {why}\n\n{_alert(alerts)} {_CLOSED}"


def dead_run_comment(alerts: tuple[str, ...]) -> str:
    """The one comment an issue gets whose run died with the pass that
    started it: a later pass found it unfinished (R-15)."""
    return ("The worker run stopped without finishing: the pass that started it ended "
            "before it did. The worktree and a handoff note are kept; a new dispatch issue "
            f"resumes it.\n\n{_alert(alerts)} {_CLOSED}")


_UNSTARTED = ("stopped before it started work: the pass that started it ended before its "
              "worktree was cut. Nothing was kept; a new dispatch issue starts it afresh.")


def unstarted_run_alert(spec: str, task: str) -> tuple[str, str]:
    """The (title, body) of the `timeout` alert for a run that died before
    its worktree was cut (R-15): fixed wording and the matched slug and id."""
    return f"{task} of {spec} stopped", f"The worker run {_UNSTARTED}"


def unstarted_run_comment(alerts: tuple[str, ...]) -> str:
    """The one comment an issue gets whose run died before its worktree was
    cut: no note, no worktree, and a new issue starts the task afresh."""
    return f"The worker run {_UNSTARTED}\n\n{_alert(alerts)} {_CLOSED}"


class CheckoutRefusal(StrEnum):
    """Why a pass will not use its checkout (R-8)."""

    CHANGED = "tracked-file-changed"
    DIVERGED = "cannot-fast-forward"
    NESTED = "nested-checkout"


_CHECKOUT: dict[CheckoutRefusal, str] = {
    CheckoutRefusal.CHANGED: "a tracked file in the checkout has been changed",
    CheckoutRefusal.DIVERGED: "the checkout cannot be fast-forwarded to `origin/main`",
    CheckoutRefusal.NESTED: "the checkout lies inside another repository's working tree",
}


def checkout_alert(reason: CheckoutRefusal, checkout: str) -> tuple[str, str]:
    """The (title, body) of the alert a refused checkout raises."""
    return (
        "dispatch tick refused its checkout",
        (f"No dispatch pass will start a run until this is put right: {_CHECKOUT[reason]}."
         f"\n\nCheckout: `{checkout}`. Reason code: `{reason.value}`. Nothing was listed, "
         "claimed or started."),
    )


class FailureKind(StrEnum):
    """What a run that raised an error is named as (R-13)."""

    LOGIN = "login"
    USAGE_LIMIT = "usage limit"
    CLI_VERSION = "CLI version"
    OTHER = "other"


# The one table: what the session's exit or its record's last line says, by
# kind, tried in order. Corrected from real failures; anything else is OTHER.
FAILURE_PATTERNS: tuple[tuple[FailureKind, re.Pattern[str]], ...] = (
    (FailureKind.LOGIN, re.compile(
        r"not logged in|please run /login|invalid api key|authentication_error|"
        r"oauth token (?:has )?expired|login (?:has )?expired", re.IGNORECASE)),
    (FailureKind.USAGE_LIMIT, re.compile(
        r"usage limit|rate_limit_error|limit will reset|out of (?:extra )?usage",
        re.IGNORECASE)),
    (FailureKind.CLI_VERSION, re.compile(
        r"newer version|please update|unsupported (?:cli )?version|"
        r"version .{0,40}(?:no longer|not) supported|minimum (?:required )?version",
        re.IGNORECASE)),
)
_EXIT_STATUS = re.compile(r"\bsession exited (-?[0-9]+)")


def failure_kind(exit_text: str, record_end: str) -> FailureKind:
    """The kind a failed run is named as, from its exit and its record's end."""
    for kind, pattern in FAILURE_PATTERNS:
        if pattern.search(exit_text) or pattern.search(record_end):
            return kind
    return FailureKind.OTHER


def failure_alert(
    spec: str, task: str, exit_text: str, record: Path | None, record_end: str
) -> tuple[str, str]:
    """The (title, body) of a run's `failed` alert: the kind, the exit status
    and where the record is on this Mac — never the record or the output."""
    kind = failure_kind(exit_text, record_end)
    m = _EXIT_STATUS.search(exit_text)
    status = f"`{m.group(1)}`" if m else "none (the session did not exit with a status)"
    where = f"`{record.resolve()}`" if record is not None else "none was written"
    return (
        f"{task} of {spec} failed: {kind.value}",
        (f"The worker run ended in an error with no pull request.\n\nKind: {kind.value}. "
        f"Exit status: {status}. Session record on the tick's Mac: {where}."),
    )


def version_alert(configured: str, installed: str) -> tuple[str, str]:
    """The (title, body) of the alert a CLI version mismatch raises (R-18)."""
    return (
        "dispatch tick: the worker CLI version differs",
        (f"No session was started. Kind: {FailureKind.CLI_VERSION.value}. The configuration "
        f"names version `{configured}`; the installed CLI reports `{installed}`. The "
        "dispatch issue is left open; a pass after the two agree runs it."),
    )


def reported_version(text: str) -> str:
    """The version number in what `claude --version` printed, else all of it."""
    m = re.search(r"[0-9]+(?:\.[0-9]+)+", text)
    return m.group(0) if m else text.strip()


FAILED_PASSES_ALERT_AT = 3


def failed_passes_alert(count: int) -> tuple[str, str]:
    """The (title, body) of the alert the third failed pass in a row raises."""
    return (
        "dispatch tick: passes are failing",
        (f"{count} dispatch passes in a row have failed: they could not list the issues, "
        "fetch, or answer an issue. The tick's log has the details. No further alert is "
        "raised until a pass completes."),
    )


def count_failed_pass(state: Path) -> int:
    """Add one failed pass to the state file's count; the count now."""
    count = _failed_passes(state) + 1
    _write_failed_passes(state, count)
    return count


def reset_failed_passes(state: Path) -> None:
    """A completed pass: the count starts again."""
    if _failed_passes(state):
        _write_failed_passes(state, 0)


def _failed_passes(state: Path) -> int:
    try:
        value: Any = json.loads(state.read_text(encoding="utf-8")).get("failed_passes")
    except (OSError, ValueError, AttributeError):
        return 0
    return value if isinstance(value, int) and value >= 0 else 0


def _write_failed_passes(state: Path, count: int) -> None:
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({"failed_passes": count}) + "\n", encoding="utf-8")


HEARTBEAT_ENV = "AF_HA_HEARTBEAT_URL"

# Opens a request with a timeout in seconds; the shape of `urlopen`.
Opener = Callable[[urllib.request.Request, float], Any]


def _urlopen(req: urllib.request.Request, timeout_s: float) -> Any:
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return resp.status


def send_heartbeat(
    env: Mapping[str, str] = os.environ, *, opener: Opener = _urlopen, timeout_s: float = 10.0
) -> str:
    """One request to the heartbeat address (R-20). Never raises: what
    happened comes back as one line for the log."""
    url = env.get(HEARTBEAT_ENV, "").strip()
    if not url:
        return f"skipped: {HEARTBEAT_ENV} not set"
    try:
        opener(urllib.request.Request(url, b"{}", {"Content-Type": "application/json"},
                                      method="POST"), timeout_s)
    except Exception as e:  # noqa: BLE001 — a heartbeat never changes the pass (R-20)
        return f"failed: {(str(e).splitlines() or [type(e).__name__])[0]}"
    return "sent"
