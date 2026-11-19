"""What the dispatch tick writes back on an issue (specs/dispatch-from-issue).

Every comment is fixed wording plus values the code computed; none carries
text taken from an issue — not its title, body, comments, labels or author
(R-11, R-12).
"""

from __future__ import annotations

import re
from enum import StrEnum

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


def run_comment(outcome: WorkerOutcome | None) -> str:
    """The one comment an accepted issue gets once its run has ended; None
    is a run that raised an error. Names the pull request or the alert."""
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
                f"{_CLOSED}")
    return f"The worker run {why}\n\n{_alert(alerts)} {_CLOSED}"


def dead_run_comment(alerts: tuple[str, ...]) -> str:
    """The one comment an issue gets whose run died with the pass that
    started it: a later pass found it unfinished (R-15)."""
    return ("The worker run stopped without finishing: the pass that started it ended "
            "before it did. The worktree and a handoff note are kept; a new dispatch issue "
            f"resumes it.\n\n{_alert(alerts)} {_CLOSED}")


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
