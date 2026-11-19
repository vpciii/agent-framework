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
- SC-12 (T-9): only the session is stopped — a live group with the recorded
  number but without the session lock gets no signal, one holding it does;
  the session keeps the lock after its launcher dies and frees it when it is
  stopped. A run whose worktree was never cut gets no worktree and no note,
  is answered and closed, and the next issue starts afresh from `origin/main`.
  A pass that finds the session lock held starts nothing and fails; the pass
  after the lock is freed runs the issue.
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
from agent_framework.worker.session import run_claude, stop_group

from . import test_pass_runs
from .test_checkout import Alerts
from .test_pass_runs import BRANCH, LIMITS, Runner, Session, Tracker, _git, _issue, _tick_seams

WORKTREE = ".worktrees/fixture-t-1"

# Takes the lock and, as the tick does, the session lock; starts a "session"
# leading its own process group that inherits the session lock, closes its own
# copy, records the run naming the group, says so, and waits to be killed.
# Its last argument changes what it stands in for: "unlocked", a group that
# does not hold the session lock; "none", a run that died before any session.
_HOLDER = """
import fcntl, json, os, subprocess, sys
lock_file, worktree, session_lock, mode = sys.argv[1:5]
os.makedirs(os.path.dirname(lock_file), exist_ok=True)
fd =os.open(lock_file, os.O_RDWR | os.O_CREAT, 0o644)
fcntl.flock(fd, fcntl.LOCK_EX)
pgid = None
if mode != "none":
    sfd = os.open(session_lock, os.O_RDWR | os.O_CREAT, 0o644)
    fcntl.flock(sfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    fds = (sfd,) if mode == "locked" else ()
    pgid = subprocess.Popen(["sleep", "300"], start_new_session=True, pass_fds=fds).pid
    os.close(sfd)
os.ftruncate(fd, 0)
os.write(fd, json.dumps({"pid": os.getpid(), "started": "2026-11-20T14:02:11Z",
    "issue": 7, "spec": "fixture", "task": "T-1", "worktree": worktree,
    "session_pgid": pgid}).encode() + b"\\n")
print(pgid or 0, flush=True)
sys.stdin.read()
"""

# Starts a stand-in session through the real `run_claude`, as the tick does:
# takes the session lock, hands it to the session, closes its own copy once
# the session has started, says the group, and waits for the session.
_LAUNCHER = """
import os, sys
from pathlib import Path
from agent_framework.dispatch import lock
from agent_framework.worker.session import run_claude
fd = lock.take_session(Path(sys.argv[1]))
assert fd is not None
def started(pgid):
    os.close(fd)
    print(pgid, flush=True)
run_claude(["sleep", "300"], Path(sys.argv[2]), 600, {}, Path(sys.argv[3]),
           on_start=started, pass_fds=(fd,))
"""

repo = test_pass_runs.repo  # the fixture: a clone of a bare remote


def _alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    return True


def _gone(pgid: int) -> bool:
    deadline = time.monotonic() + 10
    while _alive(pgid) and time.monotonic() < deadline:
        time.sleep(0.05)
    return not _alive(pgid)


def _kill_holder(repo: Path, mode: str) -> int:
    """Start the holder, wait for its record, kill it. The session's group, or 0."""
    holder = subprocess.Popen(
        [sys.executable, "-c", _HOLDER, str(repo / lock.LOCK_FILE), WORKTREE,
         str(repo / lock.SESSION_LOCK_FILE), mode],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
    )
    assert holder.stdout is not None
    pgid = int(holder.stdout.readline())
    holder.send_signal(signal.SIGKILL)
    holder.wait()
    return pgid


@pytest.fixture
def no_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(WEBHOOK_ENV, raising=False)


def _cut_worktree(repo: Path) -> None:
    _git(repo, "worktree", "add", "-q", "-b", BRANCH, WORKTREE, "origin/main")
    (repo / WORKTREE / "half.py").write_text("x = 0\n", encoding="utf-8")
    _git(repo / WORKTREE, "add", "half.py")
    _git(repo / WORKTREE, "commit", "-q", "-m", "feat: half done")


@pytest.fixture
def died(repo: Path, no_webhook: None) -> Iterator[int]:
    """A run of #7 that died: its worktree holds a commit, its holder was
    killed, its session's process group outlived it holding the session
    lock. The group's id."""
    _cut_worktree(repo)
    pgid = _kill_holder(repo, "locked")
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


def test_sc12_a_group_not_holding_the_session_lock_gets_no_signal(
    repo: Path, no_webhook: None
) -> None:
    """SC-12: a live group with the recorded number but without the session
    lock is not the session: it is sent nothing and is alive afterwards."""
    _cut_worktree(repo)
    pgid = _kill_holder(repo, "unlocked")
    try:
        assert _alive(pgid) and not lock.session_alive(repo / lock.SESSION_LOCK_FILE)
        events: list[str] = []
        tracker, alerts = Tracker(events, _issue()), Alerts()
        assert _pass(tracker, alerts, Session(events), Runner()) is PassResult.COMPLETED
        time.sleep(0.5)
        assert _alive(pgid)  # no signal reached it
        assert lock.read_run(repo / lock.LOCK_FILE) is None
        assert (repo / WORKTREE / HANDOFF_FILE).is_file()
        assert [label for label, _ in alerts.raised] == ["timeout"]
        assert events == ["comment #7", "close #7"]
    finally:
        os.killpg(pgid, signal.SIGKILL)


def test_sc12_a_live_session_holding_the_session_lock_is_stopped(
    repo: Path, died: int
) -> None:
    """SC-12: the stand-in session holds the session lock and leads the
    recorded group; recovery stops it, and the lock is then free."""
    session_lock = repo / lock.SESSION_LOCK_FILE
    assert lock.session_alive(session_lock)
    events: list[str] = []
    tracker, alerts = Tracker(events, _issue()), Alerts()
    assert _pass(tracker, alerts, Session(events), Runner()) is PassResult.COMPLETED
    assert _gone(died)
    assert not lock.session_alive(session_lock)


def test_sc12_the_session_keeps_the_lock_after_its_launcher_is_killed(
    tmp_path: Path,
) -> None:
    """SC-12: the session lock handed through `run_claude` is held by the
    session after its launcher is killed, and is free once it is stopped."""
    session_lock = tmp_path / lock.SESSION_LOCK_FILE
    launcher = subprocess.Popen(
        [sys.executable, "-c", _LAUNCHER, str(session_lock), str(tmp_path),
         str(tmp_path / "record")],
        stdout=subprocess.PIPE, text=True,
    )
    assert launcher.stdout is not None
    pgid = int(launcher.stdout.readline())
    try:
        launcher.send_signal(signal.SIGKILL)
        launcher.wait()
        assert _alive(pgid)
        assert lock.session_alive(session_lock)
        stop_group(pgid)
        assert _gone(pgid)
        assert not lock.session_alive(session_lock)
    finally:
        if _alive(pgid):
            os.killpg(pgid, signal.SIGKILL)


def test_sc12_a_run_that_died_before_its_worktree_was_cut_is_closed_and_started_afresh(
    repo: Path, no_webhook: None
) -> None:
    """SC-12: no worktree was cut, so recovery creates none and writes no
    note; it alerts, answers and closes #7, and clears the record. The next
    issue for the task runs in a fresh worktree cut from `origin/main`."""
    assert _kill_holder(repo, "none") == 0
    events: list[str] = []
    tracker, alerts = Tracker(events, _issue()), Alerts()
    tracker.issues[7].labels.discard("dispatch")  # claimed by the run that died
    session, runner = Session(events), Runner()

    assert _pass(tracker, alerts, session, runner) is PassResult.COMPLETED
    assert not (repo / WORKTREE).exists()
    assert lock.read_run(repo / lock.LOCK_FILE) is None
    assert [label for label, _ in alerts.raised] == ["timeout"]
    assert events == ["comment #7", "close #7"] and session.seen == []
    (comment,) = tracker.written
    assert "stopped before it started work" in comment and "#40" in comment
    assert "starts it afresh" in comment and "handoff note" not in comment
    assert not tracker.issues[7].open

    tracker.issues[8] = type(tracker.issues[7])(_issue(number=8, day=2))
    assert _pass(tracker, alerts, session, runner) is PassResult.COMPLETED
    (seen,) = session.seen
    assert "== HANDOFF NOTE" not in seen["brief"]
    assert _git(repo, "log", "--format=%s", BRANCH).splitlines()[0] == "feat: work"
    assert _git(repo, "rev-parse", f"{BRANCH}~1") == _git(repo, "rev-parse", "origin/main")
    assert not tracker.issues[8].open


def test_sc12_a_pass_that_finds_the_session_lock_held_starts_nothing(
    repo: Path, no_webhook: None
) -> None:
    """SC-12: while a session (here, this test) holds the session lock, a pass
    starts no session, leaves its issue open and labelled with no comment,
    records no run and ends as a failed pass. Once the lock is freed, the
    next pass runs the issue."""
    held = lock.take_session(repo / lock.SESSION_LOCK_FILE)
    assert held is not None
    events: list[str] = []
    tracker, alerts = Tracker(events, _issue()), Alerts()
    before = len(tracker.issues[7].comments)
    session, runner = Session(events), Runner()
    try:
        assert _pass(tracker, alerts, session, runner) is PassResult.FAILED
    finally:
        os.close(held)
    assert session.seen == [] and events == []
    fake = tracker.issues[7]
    assert fake.open and "dispatch" in fake.labels and len(fake.comments) == before
    assert lock.read_run(repo / lock.LOCK_FILE) is None
    assert alerts.raised == []

    assert _pass(tracker, alerts, session, runner) is PassResult.COMPLETED
    assert len(session.seen) == 1 and not tracker.issues[7].open
