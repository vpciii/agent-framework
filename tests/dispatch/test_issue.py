"""Whether a dispatch issue may start a run (specs/dispatch-from-issue).

Verifies spec success criteria:
- SC-1: `decide` accepts only the configured author's well-formed title
  naming a task that exists, is not done and claims a criterion; it
  refuses each other case with its own reason; the oldest issue is chosen.
- SC-2: no author, and `enabled = false`, are each reported as off.
- SC-4: a title carrying anything beyond a slug and a task id is refused.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agent_framework.dispatch.issue import (
    Accepted,
    Issue,
    Refusal,
    Refused,
    decide,
    oldest,
    parse_title,
)
from agent_framework.project import DispatchConfig

ON = DispatchConfig(author="vpciii")

TASKS = """\
# Tasks: Example

### [ ] T-1 — Open, claims a criterion
- **Satisfies:** SC-1, SC-2
- **Depends on:** —

### [x] T-2 — Done
- **Satisfies:** SC-3

### [ ] T-3 — Claims nothing
- **Satisfies:** —

### [ ] T-10 — Two digits
- **Satisfies:** SC-4
"""


def _issue(title: str, author: str = "vpciii", number: int = 7, day: int = 1) -> Issue:
    return Issue(number=number, title=title, author=author,
                 opened=datetime(2026, 11, day, tzinfo=UTC))


def test_sc1_accepts_the_configured_authors_title_for_an_open_task() -> None:
    """SC-1: the one accepted shape yields the slug and task id."""
    assert decide(_issue("example T-1"), ON, TASKS) == Accepted("example", "T-1")
    assert decide(_issue("dispatch-from-issue T-10"), ON, TASKS) == Accepted(
        "dispatch-from-issue", "T-10"
    )


@pytest.mark.parametrize(
    ("issue", "tasks", "reason"),
    [
        (_issue("example T-1", author="someone-else"), TASKS, Refusal.AUTHOR),
        (_issue("example T-1", author="VPCIII"), TASKS, Refusal.AUTHOR),
        (_issue("example T-1 please"), TASKS, Refusal.TITLE),
        (_issue("example T-1"), None, Refusal.UNKNOWN_SPEC),
        (_issue("example T-9"), TASKS, Refusal.UNKNOWN_TASK),
        (_issue("example T-2"), TASKS, Refusal.DONE),
        (_issue("example T-3"), TASKS, Refusal.NO_CRITERION),
    ],
)
def test_sc1_refuses_each_other_case_with_its_own_reason(
    issue: Issue, tasks: str | None, reason: Refusal
) -> None:
    """SC-1: another author, another title shape, an unknown spec or task,
    a task done, a task that claims nothing — each refused, by its code."""
    assert decide(issue, ON, tasks) == Refused(reason)


def test_sc1_another_author_is_refused_before_the_title_is_looked_at() -> None:
    """SC-1: the author check comes first, whatever the title holds."""
    bad_title = _issue("rm -rf / T-1; echo", author="someone-else")
    assert decide(bad_title, ON, None) == Refused(Refusal.AUTHOR)


def test_sc1_a_refusal_carries_nothing_taken_from_the_issue() -> None:
    """SC-1: a refusal is a reason code only."""
    refused = decide(_issue("MARKER-TEXT T-1", author="MARKER-AUTHOR"), ON, TASKS)
    assert refused == Refused(Refusal.AUTHOR)
    assert "MARKER" not in repr(refused)
    assert {f for f in vars(refused)} == {"reason"}


def test_sc1_the_oldest_of_several_issues_is_chosen() -> None:
    """SC-1: with several issues, only the earliest opened is acted on."""
    newer = _issue("example T-1", number=3, day=9)
    older = _issue("example T-10", number=12, day=2)
    tied = _issue("example T-1", number=11, day=2)
    assert oldest([newer, older]) == older
    assert oldest([newer, older, tied]) == tied
    assert oldest([]) is None


@pytest.mark.parametrize(
    "config",
    [
        DispatchConfig(),  # no author
        DispatchConfig(author=None, enabled=True),
        DispatchConfig(author="vpciii", enabled=False),
    ],
)
def test_sc2_no_author_and_disabled_are_each_reported_as_off(config: DispatchConfig) -> None:
    """SC-2: with no author, or switched off, every issue is refused as off,
    before anything else is looked at."""
    assert not config.on
    assert decide(_issue("example T-1"), config, TASKS) == Refused(Refusal.OFF)
    assert decide(_issue("bad", author="x"), config, None) == Refused(Refusal.OFF)


@pytest.mark.parametrize(
    "title",
    [
        "example T-1 and more",  # text after the task id
        "example T-1\n",
        "example T-1; echo hi",
        "example\tT-1",  # another separator
        "example  T-1",
        "example:T-1",
        "example/T-1",
        "example-T-1",
        "Example T-1",  # other letter case
        "example t-1",
        "EXAMPLE T-1",
        " example T-1",  # leading or trailing space
        "example T-1 ",
        "",
        "example",
        "example T-",
        "example_slug T-1",
        "-example T-1",
        "example- T-1",
        "example T-1a",
        "exämple T-1",
        "example T-١",  # a non-ASCII digit
    ],
)
def test_sc4_a_title_beyond_a_slug_and_a_task_id_is_refused(title: str) -> None:
    """SC-4: the whole title must match, nothing trimmed or lowered."""
    assert parse_title(title) is None
    assert decide(_issue(title), ON, TASKS) == Refused(Refusal.TITLE)


def test_sc4_only_the_matched_slug_and_task_id_come_from_the_title() -> None:
    """SC-4: what a title yields is the two matched parts, nothing else."""
    assert parse_title("dispatch-from-issue T-1") == ("dispatch-from-issue", "T-1")
