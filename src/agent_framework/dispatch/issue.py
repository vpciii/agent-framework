"""Whether a dispatch issue may start a worker run (specs/dispatch-from-issue).

Pure: no git, no network, no session. The tick lists the open dispatch
issues, picks the oldest, and asks `decide` about it with the dispatch
configuration and the named spec's `tasks.md` as it is on `origin/main`.

The only values taken from an issue that leave this module are the spec
slug and task id, and only after the whole title has matched
`TITLE_PATTERN` (R-6). A refusal carries a reason code and nothing else.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ..artifacts import claimed_criteria, task_block, task_done
from ..project import DispatchConfig

# The plan's API changes: the whole title, nothing trimmed or lowered.
TITLE_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)* T-[0-9]+$"
_TITLE_RE = re.compile(TITLE_PATTERN, re.ASCII)


@dataclass(frozen=True)
class Issue:
    """What the tick reads of a dispatch issue: nothing beyond these four."""

    number: int
    title: str
    author: str
    opened: datetime


class Refusal(StrEnum):
    """Why an issue starts no run, checked in this order."""

    OFF = "dispatch-off"
    AUTHOR = "other-author"
    TITLE = "title-shape"
    UNKNOWN_SPEC = "unknown-spec"
    UNKNOWN_TASK = "unknown-task"
    DONE = "task-done"
    NO_CRITERION = "no-criterion"


@dataclass(frozen=True)
class Accepted:
    """The run an issue asks for: a spec slug and a task id that matched."""

    spec_slug: str
    task_id: str


@dataclass(frozen=True)
class Refused:
    """An issue that starts no run, and the code for why."""

    reason: Refusal


def parse_title(title: str) -> tuple[str, str] | None:
    """`(spec_slug, task_id)` when the whole title is exactly
    `<spec-slug> <task-id>`, else None."""
    if _TITLE_RE.fullmatch(title) is None:
        return None
    slug, task_id = title.split(" ")
    return slug, task_id


def decide(
    issue: Issue, config: DispatchConfig, tasks_text: str | None
) -> Accepted | Refused:
    """Whether `issue` may start a run (R-2, R-3).

    `tasks_text` is the named spec's `tasks.md` on `origin/main`, or None
    when that spec is not there. The checks run in `Refusal`'s order, so an
    issue from another author is refused before its title is looked at.
    """
    if not config.on:
        return Refused(Refusal.OFF)
    if issue.author != config.author:
        return Refused(Refusal.AUTHOR)
    parsed = parse_title(issue.title)
    if parsed is None:
        return Refused(Refusal.TITLE)
    if tasks_text is None:
        return Refused(Refusal.UNKNOWN_SPEC)
    slug, task_id = parsed
    block = task_block(tasks_text, task_id)
    if block is None:
        return Refused(Refusal.UNKNOWN_TASK)
    if task_done(block):
        return Refused(Refusal.DONE)
    if not claimed_criteria(block):
        return Refused(Refusal.NO_CRITERION)
    return Accepted(spec_slug=slug, task_id=task_id)


def oldest(issues: list[Issue]) -> Issue | None:
    """The issue a pass acts on: the earliest opened (the lower number on a
    tie), or None when there is none (R-1)."""
    return min(issues, key=lambda i: (i.opened, i.number), default=None)
