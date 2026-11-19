"""What the dispatch tick writes back on an issue (specs/dispatch-from-issue).

Every comment is fixed wording plus values the code computed; none carries
text taken from an issue — not its title, body, comments, labels or author
(R-11, R-12).
"""

from __future__ import annotations

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
