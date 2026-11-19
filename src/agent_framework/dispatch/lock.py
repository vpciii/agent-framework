"""The dispatch tick's lock and the run it names (specs/dispatch-from-issue).

At most one run is in progress per checkout (R-5): a pass holds an advisory
`flock` on `.worktrees/dispatch.lock` for as long as it runs. The operating
system releases the lock when the process dies, so whether a pass is running
never rests on guessing whether a process id is still the same process.

The file's content is the run in progress, or nothing — in the plan's shape,
plus whether that run finished. It is always rewritten in place, never
replaced: a new file would be a new inode, and the lock is held on the old.

The session holds a second lock, on `.worktrees/dispatch-session.lock`, for
as long as it lives: the tick takes it, hands the descriptor to the session,
and closes its own copy, so the operating system frees it when the session
and the last process it started are gone. Whether a recorded session is
still alive is asked of that lock, never of a process id (R-15).
"""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

LOCK_FILE = Path(".worktrees") / "dispatch.lock"
SESSION_LOCK_FILE = Path(".worktrees") / "dispatch-session.lock"


@contextmanager
def hold(path: Path = LOCK_FILE) -> Iterator[bool]:
    """Take the lock without waiting; yields whether it was taken.

    When it was, it is held until the `with` block ends or the process exits,
    whichever comes first.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            taken = True
        except BlockingIOError:
            taken = False
        yield taken
    finally:
        os.close(fd)  # closing the only descriptor releases the lock


def take_session(path: Path = SESSION_LOCK_FILE) -> int | None:
    """Take the session lock without waiting: the open descriptor holding
    it, for the session to inherit, or None when a session still holds it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    return fd


def session_alive(path: Path = SESSION_LOCK_FILE) -> bool:
    """Whether a session holds the session lock. When none does, the lock
    is taken and released at once; nothing is signalled or asked."""
    fd = take_session(path)
    if fd is None:
        return True
    os.close(fd)
    return False


@dataclass(frozen=True)
class Run:
    """The run in progress, as the lock file records it."""

    pid: int
    started: str  # UTC, e.g. "2026-11-20T14:02:11Z"
    issue: int
    spec: str
    task: str
    worktree: str
    session_pgid: int | None = None
    finished: bool = False

    def elapsed_s(self, now: datetime | None = None) -> float:
        """Seconds from when the run started to `now` (by default, now)."""
        began = datetime.strptime(self.started, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        return max(0.0, ((now or datetime.now(UTC)) - began).total_seconds())


def read_run(path: Path = LOCK_FILE) -> Run | None:
    """The run the lock file names, or None when it names none."""
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None
    return Run(**json.loads(text))


def write_run(run: Run | None, path: Path = LOCK_FILE) -> None:
    """Record `run` in the lock file (None clears it), in place."""
    with path.open("r+" if path.exists() else "w", encoding="utf-8") as f:
        f.truncate(0)
        f.write("" if run is None else json.dumps(asdict(run)) + "\n")
