"""The roster currency check's tracking issue.

Verifies spec success criteria (specs/roster-currency-check):
- SC-4: a failing run updates an open tracking issue rather than opening a
  duplicate, and opens exactly one when none is open.
Also covers R-11 (a SHOULD): a clean run closes the open issue.
"""

from __future__ import annotations

from agent_framework.currency.check import Finding, Severity
from agent_framework.currency.issue import LABEL, GhIssueTracker, sync_issue

_FAILING = [Finding(Severity.FAILING, "validator", "google", "gemini-3-pro", "not served")]
_ADVISORY = [Finding(Severity.ADVISORY, "worker", "anthropic", "claude-sonnet-5", "newer")]


class FakeTracker:
    def __init__(self, open_issue: int | None = None) -> None:
        self.open_issue = open_issue
        self.calls: list[tuple[str, int | None]] = []

    def find_open(self, label: str) -> int | None:
        assert label == LABEL
        return self.open_issue

    def create(self, title: str, body: str, label: str) -> int:
        self.calls.append(("create", None))
        return 7

    def update(self, number: int, body: str) -> None:
        self.calls.append(("update", number))

    def close(self, number: int, comment: str) -> None:
        self.calls.append(("close", number))


def test_sc4_failing_run_updates_the_open_issue() -> None:
    """SC-4: an open issue is updated; no second issue is created."""
    tracker = FakeTracker(open_issue=3)
    assert sync_issue(_FAILING, tracker) == "updated #3"
    assert tracker.calls == [("update", 3)]


def test_sc4_failing_run_opens_exactly_one_issue() -> None:
    """SC-4: with no open issue, exactly one is created."""
    tracker = FakeTracker()
    assert sync_issue(_FAILING, tracker) == "opened #7"
    assert tracker.calls == [("create", None)]


def test_r11_clean_run_closes_the_issue_and_advisories_alone_do_not_open_one() -> None:
    """R-11: nothing failing or unchecked → the open issue is closed; none is opened."""
    tracker = FakeTracker(open_issue=3)
    assert sync_issue(_ADVISORY, tracker) == "closed #3"
    assert tracker.calls == [("close", 3)]
    assert sync_issue(_ADVISORY, FakeTracker()) == "no issue needed"


def test_sc4_gh_tracker_finds_and_creates_through_the_gh_cli() -> None:
    """SC-4: the gh-backed tracker reads the open issue number and the created issue's URL."""
    commands: list[list[str]] = []

    def run(args: object) -> str:
        cmd = list(args)  # type: ignore[call-overload]
        commands.append(cmd)
        if cmd[:3] == ["gh", "issue", "list"]:
            return "\n"
        if cmd[:3] == ["gh", "issue", "create"]:
            return "https://github.com/vpciii/agent-framework/issues/12\n"
        return ""

    tracker = GhIssueTracker(run=run)
    assert tracker.find_open(LABEL) is None
    assert tracker.create("t", "b", LABEL) == 12
    assert ["gh", "label", "create", LABEL] == commands[1][:4]
