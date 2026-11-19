"""When it stops working: the `failed` alert, the CLI version, failed passes
(specs/dispatch-from-issue T-7).

The real tick drives the real `work()` over a real repository with a bare
remote; only the session, `gh` and the alert channels are faked.

Verifies:
- SC-10: a run that raised an error raises one `failed` alert, naming a
  login failure, a usage limit and a CLI version mismatch as such and
  anything else as "other" — never quoting the session's output; the issue's
  comment gives the alert's address.
- SC-15: a configured CLI version the installed CLI does not report starts
  no session and raises a `failed` alert naming both; with none configured
  the session starts.
- SC-16: the third failed pass in a row raises one `failed` alert, the
  fourth none, and the count starts again after a completed pass.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest

from agent_framework.alerts import notify
from agent_framework.dispatch.issue import Issue
from agent_framework.dispatch.tick import STATE_FILE, PassResult, run_pass
from agent_framework.errors import SessionResultError

from . import test_pass_runs
from .test_pass_runs import LIMITS, AlertTracker, Runner, Session, Tracker, _git, _issue

repo = test_pass_runs.repo  # the fixture: a clone of a bare remote
SECRET = "OUTPUT-SENTINEL-4471"


class Alerts(AlertTracker):
    """Every alert the tick raises: (label, title, body)."""

    def __init__(self) -> None:
        super().__init__()
        self.raised: list[tuple[str, str, str]] = []

    def create(self, title: str, body: str, label: str) -> str:
        self.raised.append((label, title, body))
        return super().create(title, body, label)


class FailingSession(Session):
    """A session that exits non-zero, its record ending in `last`."""

    def __init__(self, events: list[str], stderr: str, last: str) -> None:
        super().__init__(events)
        self.stderr, self.last = stderr, last

    def __call__(self, args: Sequence[str], cwd: Path, timeout_s: float,
                 env: Mapping[str, str], record: Path,
                 on_start: Callable[[int], None] | None = None) -> None:
        self.events.append("session")
        self.seen.append({"argv": list(args)})
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(f'{{"type": "system", "note": "{SECRET}"}}\n{self.last}\n',
                          encoding="utf-8")
        raise SessionResultError(f"session exited 1: {self.stderr} {SECRET}")


def _result_line(text: str) -> str:
    return json.dumps({"type": "result", "subtype": "success", "is_error": True,
                       "result": text})


KINDS = {
    "login": ("", _result_line("Invalid API key · Please run /login")),
    "usage limit": ("", _result_line("Claude AI usage limit reached|1763600000")),
    "CLI version": ("This model requires a newer version of Claude Code; please update.",
                    '{"type": "system"}'),
    "other": ("Segmentation fault", _result_line("something went wrong")),
}


@pytest.mark.parametrize("kind", list(KINDS))
def test_sc10_a_failed_run_raises_one_failed_alert_naming_its_kind(
    repo: Path, kind: str
) -> None:
    """SC-10: one `failed` alert, its kind named, the exit status and the
    record's place given, no output quoted; the comment gives its address."""
    events: list[str] = []
    stderr, last = KINDS[kind]
    tracker, runner, alerts = Tracker(events, _issue()), Runner(), Alerts()
    session = FailingSession(events, stderr, last)
    result = run_pass(tracker, limits=LIMITS, run=runner,
                      work_fn=test_pass_runs._tick_seams(runner), session_run=session,
                      alert_tracker=alerts, push_factory=lambda: None,
                      heartbeat=lambda: "sent")
    assert result is PassResult.COMPLETED and len(session.seen) == 1
    ((label, title, body),) = alerts.raised
    assert label == "failed" and title.endswith(f"failed: {kind}")
    assert f"Kind: {kind}." in body and "Exit status: `1`" in body
    assert str((repo / ".worktrees" / "records").resolve()) in body
    assert SECRET not in body and "usage limit reached" not in body
    if stderr:
        assert stderr not in body
    (comment,) = tracker.written
    assert "ended in an error" in comment and "Alert: #40." in comment


def _configure_version(root: Path, version: str) -> None:
    toml = root / "agent-framework.toml"
    toml.write_text(toml.read_text(encoding="utf-8").replace(
        '[dispatch]\nauthor = "vpciii"\n',
        f'[dispatch]\nauthor = "vpciii"\nworker_cli_version = "{version}"\n'),
        encoding="utf-8")
    _git(root, "commit", "-q", "-am", "chore: pin the CLI")
    _git(root, "push", "-q", "origin", "HEAD:main")


class VersionRunner(Runner):
    """As `Runner`, and `claude --version` reports `installed`."""

    def __init__(self, installed: str) -> None:
        super().__init__()
        self.installed = installed

    def __call__(self, args: Sequence[str]) -> str:
        if list(args) == ["claude", "--version"]:
            self.calls.append(list(args))
            return f"{self.installed} (Claude Code)\n"
        return super().__call__(args)


def _run(runner: Runner, alerts: Alerts, *issues: Issue,
         ) -> tuple[PassResult, Tracker, Session]:
    events: list[str] = []
    tracker, session = Tracker(events, *issues), Session(events)
    result = run_pass(tracker, limits=LIMITS, run=runner,
                      work_fn=test_pass_runs._tick_seams(runner), session_run=session,
                      alert_tracker=alerts, push_factory=lambda: None,
                      heartbeat=lambda: "sent")
    return result, tracker, session


def test_sc15_a_different_installed_version_starts_no_session(repo: Path) -> None:
    """SC-15: no claim, no session; one `failed` alert naming both versions."""
    _configure_version(repo, "2.1.325")
    alerts = Alerts()
    _, tracker, session = _run(VersionRunner("2.1.400"), alerts, _issue())
    assert session.seen == []
    ((label, _, body),) = alerts.raised
    assert label == "failed" and "`2.1.325`" in body and "`2.1.400`" in body
    left = tracker.issues[7]
    assert left.open and "dispatch" in left.labels  # a later pass runs it


def test_sc15_with_no_version_configured_the_session_starts(repo: Path) -> None:
    """SC-15: nothing configured — the CLI is not asked and the session runs."""
    runner, alerts = VersionRunner("2.1.400"), Alerts()
    _, _, session = _run(runner, alerts, _issue())
    assert len(session.seen) == 1 and alerts.raised == []
    assert ["claude", "--version"] not in runner.calls


def test_sc15_the_configured_version_installed_starts_the_session(repo: Path) -> None:
    """SC-15: the versions agree — the session runs."""
    _configure_version(repo, "2.1.325")
    _, _, session = _run(VersionRunner("2.1.325"), Alerts(), _issue())
    assert len(session.seen) == 1


class Unreachable(Tracker):
    """A tracker whose listing fails while `down` is set."""

    def __init__(self) -> None:
        super().__init__([])
        self.down = True

    def list_open(self) -> list[Issue]:
        if self.down:
            raise RuntimeError("gh: could not connect")
        return super().list_open()


def test_sc16_the_third_failed_pass_in_a_row_alerts_once(repo: Path) -> None:
    """SC-16: alerts at the third failed pass only, none at the fourth; a
    completed pass sets the count to zero, so it takes three more again."""
    tracker, alerts = Unreachable(), Alerts()

    def one_pass() -> int:
        before = len(alerts.raised)
        result = run_pass(tracker, alert_tracker=alerts, push_factory=lambda: None,
                          heartbeat=lambda: "sent")
        assert result is (PassResult.FAILED if tracker.down else PassResult.COMPLETED)
        return len(alerts.raised) - before

    assert [one_pass() for _ in range(4)] == [0, 0, 1, 0]
    assert alerts.raised[0][0] == "failed"
    tracker.down = False
    assert one_pass() == 0
    assert json.loads((repo / STATE_FILE).read_text(encoding="utf-8")) == {"failed_passes": 0}
    tracker.down = True
    assert [one_pass() for _ in range(3)] == [0, 0, 1]


def test_sc16_a_condition_already_open_is_not_pushed_again() -> None:
    """SC-16: the switch the tick's own alerts use — an open issue, no push."""
    pushed: list[str] = []

    class Open(AlertTracker):
        def find_open(self, label: str, mark: str) -> tuple[int, str] | None:
            return 12, "https://github.com/x/y/issues/12"

    def push(title: str, message: str) -> None:
        pushed.append(title)

    quiet = notify("failed", "dispatch/failed-passes", "t", "b", "m", tracker=Open(),
                   push=push, quiet_if_open=True)
    assert pushed == [] and quiet.push == "skipped: already reported in #12"
    notify("failed", "dispatch/failed-passes", "t", "b", "m", tracker=Open(), push=push)
    assert pushed == ["[failed:dispatch/failed-passes] t"]
