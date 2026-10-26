"""Alerts: one GitHub issue per key, plus a best-effort phone push.

Verifies spec success criteria (specs/orientation-and-alerts):
- SC-5: an alert opens one issue and sends one push; a repeat for the same
  key finds the existing issue and opens none.
- SC-8: failing channels never raise; each failure is reported.
- SC-10: the push endpoint comes from the environment only; unset → no
  push attempted, the skip reported.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from agent_framework.alerts import (
    WEBHOOK_ENV,
    GhIssueTracker,
    marker,
    notify,
    push_from_env,
)


class FakeTracker:
    def __init__(self, existing: dict[str, tuple[int, str]] | None = None, fail: bool = False) -> None:
        self.existing = dict(existing or {})
        self.fail = fail
        self.created: list[tuple[str, str]] = []
        self.updated: list[int] = []

    def find_open(self, label: str, mark: str) -> tuple[int, str] | None:
        if self.fail:
            raise RuntimeError("gh: network down")
        return self.existing.get(mark)

    def create(self, title: str, body: str, label: str) -> str:
        n = 40 + len(self.created)
        self.created.append((title, label))
        self.existing[title.split(" ", 1)[0]] = (n, f"https://gh/i/{n}")
        return f"https://gh/i/{n}"

    def update(self, number: int, body: str) -> None:
        self.updated.append(number)


class FakePush:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[tuple[str, str]] = []

    def __call__(self, title: str, message: str) -> None:
        if self.fail:
            raise OSError("no route to host")
        self.sent.append((title, message))


def test_sc5_alert_opens_one_issue_and_pushes_once_then_finds_it() -> None:
    """SC-5: first alert opens + pushes; the same key again finds the issue."""
    tracker, push = FakeTracker(), FakePush()
    first = notify("escalation", "spec/T-1", "T-1 needs a decision", "body", "T-1 needs a decision.",
                   tracker=tracker, push=push)
    assert first.issue == "opened #40" and first.push == "sent"
    assert tracker.created == [("[escalation:spec/T-1] T-1 needs a decision", "escalation")]
    assert push.sent == [("[escalation:spec/T-1] T-1 needs a decision",
                          "T-1 needs a decision. https://gh/i/40")]

    again = notify("escalation", "spec/T-1", "T-1 needs a decision", "body", "x",
                   tracker=tracker, push=push)
    assert again.issue == "found #40" and len(tracker.created) == 1


def test_sc8_failing_channels_are_reported_not_raised() -> None:
    """SC-8: GitHub and push both failing → a report, no exception."""
    report = notify("timeout", "s/T-1", "t", "b", "m",
                    tracker=FakeTracker(fail=True), push=FakePush(fail=True))
    assert report.issue == "failed: gh: network down"
    assert report.push == "failed: no route to host"
    assert report.lines() == ("github issue: failed: gh: network down",
                              "phone push: failed: no route to host")


def test_sc10_push_endpoint_only_from_environment() -> None:
    """SC-10: unset → None (and notify reports the skip); set → a push."""
    assert push_from_env({}) is None
    assert push_from_env({WEBHOOK_ENV: "  "}) is None
    assert push_from_env({WEBHOOK_ENV: "http://ha.local:8123/api/webhook/x"}) is not None
    report = notify("timeout", "s/T-1", "t", "b", "m", tracker=FakeTracker(), push=None)
    assert report.push == f"skipped: {WEBHOOK_ENV} not set"


def test_sc5_gh_tracker_finds_by_marker_and_creates_with_label() -> None:
    """SC-5: the gh tracker matches the title marker, and labels new issues."""
    calls: list[list[str]] = []

    def run(args: Sequence[str]) -> str:
        cmd = list(args)
        calls.append(cmd)
        if cmd[:3] == ["gh", "issue", "list"]:
            return json.dumps([{"number": 5, "title": "[timeout:a/T-9] other", "url": "u5"},
                               {"number": 6, "title": f"{marker('timeout', 'a/T-1')} t", "url": "u6"}])
        if cmd[:3] == ["gh", "issue", "create"]:
            return "https://github.com/o/r/issues/77\n"
        return ""

    tracker = GhIssueTracker(run=run)
    assert tracker.find_open("timeout", marker("timeout", "a/T-1")) == (6, "u6")
    assert tracker.find_open("timeout", marker("timeout", "a/T-2")) is None
    assert tracker.create("[timeout:a/T-2] t", "b", "timeout") == "https://github.com/o/r/issues/77"
    assert ["gh", "label", "create", "timeout", "--force"] == calls[2][:5]
