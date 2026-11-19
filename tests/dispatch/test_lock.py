"""The dispatch tick's lock and the run it names (specs/dispatch-from-issue T-4).

The lock is taken against a second, real process; the run's record is read
back as it was written.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from agent_framework.dispatch.lock import Run, hold, read_run, write_run

# Takes the lock, says so, and holds it until its stdin closes.
_HOLDER = """
import fcntl, os, sys
fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o644)
fcntl.flock(fd, fcntl.LOCK_EX)
print("held", flush=True)
sys.stdin.read()
"""


@pytest.fixture
def holder(tmp_path: Path) -> Iterator[tuple[Path, subprocess.Popen[str]]]:
    """A second process holding the lock on a file in `tmp_path`."""
    path = tmp_path / ".worktrees" / "dispatch.lock"
    path.parent.mkdir(parents=True)
    proc = subprocess.Popen(
        [sys.executable, "-c", _HOLDER, str(path)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
    )
    assert proc.stdout is not None and proc.stdout.readline().strip() == "held"
    try:
        yield path, proc
    finally:
        proc.kill()
        proc.wait()


def test_the_lock_is_not_taken_while_another_process_holds_it(
    holder: tuple[Path, subprocess.Popen[str]],
) -> None:
    path, proc = holder
    with hold(path) as taken:
        assert not taken
    proc.kill()
    proc.wait()
    with hold(path) as taken:
        assert taken  # the operating system released it with the process


def test_the_lock_is_released_when_the_pass_ends(tmp_path: Path) -> None:
    path = tmp_path / ".worktrees" / "dispatch.lock"
    with hold(path) as taken:
        assert taken
    with hold(path) as again:
        assert again


def test_the_run_is_read_back_as_written_and_cleared(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.lock"
    assert read_run(path) is None
    run = Run(pid=4812, started="2026-11-20T14:02:11Z", issue=151,
              spec="dispatch-from-issue", task="T-2",
              worktree=".worktrees/dispatch-from-issue-t-2", session_pgid=4830)
    with hold(path) as taken:
        assert taken
        inode = path.stat().st_ino
        write_run(run, path)
        assert read_run(path) == run
        write_run(None, path)
        assert read_run(path) is None
        assert path.stat().st_ino == inode  # rewritten in place: the lock still holds
