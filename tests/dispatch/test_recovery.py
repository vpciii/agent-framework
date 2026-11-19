"""A run that died: the next pass recovers it, and a later issue resumes it
(specs/dispatch-from-issue T-6).

A real process takes the lock, records a run whose session leads a process
group of its own, and is killed. The real tick and the real `work()` then run
over the real repository; only the session, `gh` and the alert channels are
faked.

Verifies:
- SC-12: after the holder is killed, the next pass stops what is left of the
  session, clears the record, leaves a handoff note in the worktree, raises a
  `timeout` alert and comments on and closes the claimed issue; a dispatch
  issue for the same task then resumes in that worktree, on that branch.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from agent_framework.alerts import WEBHOOK_ENV
from agent_framework.dispatch import lock
from agent_framework.dispatch.tick import PassResult, run_pass
from agent_framework.worker.handoff import HANDOFF_FILE
from agent_framework.worker.session import run_claude

from . import test_pass_runs
from .test_checkout import Alerts
from .test_pass_runs import BRANCH, LIMITS, Runner, Session, Tracker, _git, _issue, _tick_seams

WORKTREE = ".worktrees/fixture-t-1"

# Takes the lock, starts a "session" leading its own process group, records
# the run naming it, says so, and waits to be killed.
_HOLDER = """
import fcntl, json, os, subprocess, sys
fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o644)
fcntl.flock(fd, fcntl.LOCK_EX)
session = subprocess.Popen(["sleep", "300"], start_new_session=True)
os.ftruncate(fd, 0)
os.write(fd, json.dumps({"pid": os.getpid(), "started": "2026-11-20T14:02:11Z",
    "issue": 7, "spec": "fixture", "task": "T-1", "worktree": sys.argv[2],
    "session_pgid": session.pid}).encode() + b"\\n")
print(session.pid, flush=True)
sys.stdin.read()
"""

repo = test_pass_runs.repo  # the fixture: a clone of a bare remote


def _alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    return True


@pytest.fixture
def died(repo: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[int]:
    """A run of #7 that died: its worktree holds a commit, its holder was
    killed, its session's process group outlived it. The group's id."""
    monkeypatch.delenv(WEBHOOK_ENV, raising=False)
    _git(repo, "worktree", "add", "-q", "-b", BRANCH, WORKTREE, "origin/main")
    (repo / WORKTREE / "half.py").write_text("x = 0\n", encoding="utf-8")
    _git(repo / WORKTREE, "add", "half.py")
    _git(repo / WORKTREE, "commit", "-q", "-m", "feat: half done")
    holder = subprocess.Popen(
        [sys.executable, "-c", _HOLDER, str(repo / lock.LOCK_FILE), WORKTREE],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
    )
    assert holder.stdout is not None
    pgid = int(holder.stdout.readline())
    holder.send_signal(signal.SIGKILL)
    holder.wait()
    assert _alive(pgid)
    yield pgid
    if _alive(pgid):
        os.killpg(pgid, signal.SIGKILL)


def _pass(tracker: Tracker, alerts: Alerts, session: Session, runner: Runner) -> PassResult:
    return run_pass(tracker, limits=LIMITS, run=runner, work_fn=_tick_seams(runner),
                    session_run=session, alert_tracker=alerts, push_factory=lambda: None)


def test_sc12_a_killed_holders_run_is_recovered_and_then_resumed(
    repo: Path, died: int
) -> None:
    """SC-12: the next pass recovers #7; the issue after it resumes the task."""
    events: list[str] = []
    tracker, alerts = Tracker(events, _issue()), Alerts()
    tracker.issues[7].labels.discard("dispatch")  # claimed by the run that died
    session, runner = Session(events), Runner()

    assert _pass(tracker, alerts, session, runner) is PassResult.COMPLETED
    deadline = time.monotonic() + 10
    while _alive(died) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not _alive(died)  # what was left of the session is stopped
    assert lock.read_run(repo / lock.LOCK_FILE) is None
    note = (repo / WORKTREE / HANDOFF_FILE).read_text(encoding="utf-8")
    assert "T-1" in note and "feat: half done" in note
    assert [label for label, _ in alerts.raised] == ["timeout"]
    assert events == ["comment #7", "close #7"] and session.seen == []
    assert "handoff note" in tracker.written[0] and "#40" in tracker.written[0]
    assert not tracker.issues[7].open

    tracker.issues[8] = type(tracker.issues[7])(_issue(number=8, day=2))
    assert _pass(tracker, alerts, session, runner) is PassResult.COMPLETED
    (seen,) = session.seen
    assert "== HANDOFF NOTE" in seen["brief"] and "feat: half done" in seen["brief"]
    log = _git(repo, "log", "--format=%s", BRANCH).splitlines()
    assert log[:2] == ["feat: work", "feat: half done"]  # same branch, carried on
    assert not tracker.issues[8].open


def test_sc12_the_session_group_is_recorded_as_the_session_starts(tmp_path: Path) -> None:
    """SC-12: `run_claude` tells its callback the group the session leads."""
    told: list[int] = []
    record = tmp_path / "record"
    run_claude([sys.executable, "-c", "import os; print(os.getpgid(0))"], tmp_path, 30, {},
               record, on_start=told.append)
    assert told == [int(record.read_text(encoding="utf-8"))]


def test_sc12_the_tick_writes_the_group_into_the_lock_file(repo: Path) -> None:
    """SC-12: what the session seam is told, the lock file records at once."""
    seen: list[lock.Run | None] = []

    class Telling(Session):
        def __call__(self, *args: object, on_start: object = None, **kw: object) -> None:
            assert callable(on_start)
            on_start(os.getpid())
            seen.append(lock.read_run(repo / lock.LOCK_FILE))
            super().__call__(*args, **kw)  # type: ignore[arg-type]

    events: list[str] = []
    runner = Runner()
    run_pass(Tracker(events, _issue()), limits=LIMITS, run=runner,
             work_fn=_tick_seams(runner), session_run=Telling(events))
    (run,) = seen
    assert run is not None and run.session_pgid == os.getpid() and not run.finished
    after = lock.read_run(repo / lock.LOCK_FILE)
    assert after is not None and after.finished  # never mistaken for a dead run
