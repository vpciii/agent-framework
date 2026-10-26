"""The worker's timeout and escalation paths, and the process-group kill.

Verifies spec success criteria (specs/orientation-and-alerts):
- SC-5: an escalation opens one `escalation` issue and sends one push.
- SC-6: a budget expiry leaves no descendant process running (real
  processes, not a fake).
- SC-7: a timeout writes a handoff note (task, budget, elapsed, git status,
  diff summary, progress notes), opens one `timeout` issue, sends one push.
- SC-8: with every channel failing, the worker's outcome and exit code are
  unchanged and each failure is reported.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path

import pytest

from agent_framework.errors import SessionTimeoutError
from agent_framework.worker import __main__ as worker_cli
from agent_framework.worker.orchestrator import work
from agent_framework.worker.session import run_claude
from agent_framework.worker.types import Escalated, TimedOut

from .test_orchestrator import _GitGh, _roster, _session, repo  # noqa: F401 — shared fixture


class FakeTracker:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.created: list[tuple[str, str]] = []

    def find_open(self, label: str, mark: str) -> tuple[int, str] | None:
        if self.fail:
            raise RuntimeError("gh: network down")
        return None

    def create(self, title: str, body: str, label: str) -> str:
        self.created.append((title, label))
        return f"https://gh/i/{40 + len(self.created) - 1}"

    def update(self, number: int, body: str) -> None:
        pass


class FakePush:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[tuple[str, str]] = []

    def __call__(self, title: str, message: str) -> None:
        if self.fail:
            raise OSError("no route to host")
        self.sent.append((title, message))


def _timeout_session(args: Sequence[str], cwd: Path, timeout_s: float) -> None:
    cwd.mkdir(parents=True, exist_ok=True)
    (cwd / ".worker-progress").write_text("halfway through the widget", encoding="utf-8")
    raise SessionTimeoutError("over budget")


class _GitWithState(_GitGh):
    def __call__(self, args: Sequence[str]) -> str:
        call = list(args)
        if "status" in call and "--short" in call:
            self.calls.append(call)
            return " M widget.py\n"
        if "diff" in call and "--stat" in call:
            self.calls.append(call)
            return " widget.py | 3 ++-\n"
        return super().__call__(args)


def test_sc7_timeout_leaves_a_handoff_note_and_alerts(repo: Path) -> None:  # noqa: F811
    """SC-7: note contents; one timeout issue; one push."""
    tracker, push = FakeTracker(), FakePush()
    outcome = work("fixture", "T-1", _roster(), specs_dir=repo / "specs", timeout_s=5,
                   run=_GitWithState(), session_run=_timeout_session,
                   tracker=tracker, push_factory=lambda: push)

    assert outcome == TimedOut(worktree_path=".worktrees/fixture-t-1")  # identity unchanged
    assert isinstance(outcome, TimedOut) and outcome.handoff_path
    note = Path(outcome.handoff_path).read_text(encoding="utf-8")
    assert "T-1 (fixture) timed out" in note and "**Budget:** 5s" in note
    assert "**elapsed:**" in note
    assert "M widget.py" in note and "widget.py | 3 ++-" in note
    assert "halfway through the widget" in note
    assert tracker.created == [("[timeout:fixture/T-1] T-1 of fixture timed out", "timeout")]
    assert len(push.sent) == 1
    assert outcome.alerts == ("github issue: opened #40", "phone push: sent")


def test_sc5_escalation_opens_one_issue_and_pushes(repo: Path) -> None:  # noqa: F811
    """SC-5: escalation file as before, plus one escalation issue and one push."""
    tracker, push = FakeTracker(), FakePush()
    _, session = _session({"status": "escalated", "detail": "SC-2 contradicts R-1"})
    outcome = work("fixture", "T-1", _roster(), specs_dir=repo / "specs",
                   run=_GitGh(), session_run=session, tracker=tracker, push_factory=lambda: push)

    assert isinstance(outcome, Escalated) and Path(outcome.artifact_path).is_file()
    assert tracker.created == [("[escalation:fixture/T-1] T-1 of fixture needs a decision",
                                "escalation")]
    assert len(push.sent) == 1


def test_sc8_failing_channels_change_neither_outcome_nor_exit_code(
    repo: Path, capsys: pytest.CaptureFixture[str]  # noqa: F811
) -> None:
    """SC-8: same outcome and exit code with all channels down; failures in the output."""
    broken = work("fixture", "T-1", _roster(), specs_dir=repo / "specs", timeout_s=5,
                  run=_GitGh(), session_run=_timeout_session,
                  tracker=FakeTracker(fail=True), push_factory=lambda: FakePush(fail=True))
    assert broken == TimedOut(worktree_path=".worktrees/fixture-t-1")
    assert isinstance(broken, TimedOut)
    assert broken.alerts == ("github issue: failed: gh: network down",
                             "phone push: failed: no route to host")

    (repo / "agent-framework.toml").write_text(
        '[roles]\nworker = { provider = "anthropic", model = "m" }\n', encoding="utf-8")
    code = worker_cli.main(["fixture", "T-1"], work_fn=lambda *a, **k: broken)
    assert code == 3  # a timeout's exit code, notifications or not
    out = capsys.readouterr().out
    assert "github issue: failed: gh: network down" in out


def _alive(pids: list[int]) -> list[int]:
    alive = []
    for pid in pids:
        try:
            os.kill(pid, 0)
            alive.append(pid)
        except ProcessLookupError:
            pass
    return alive


def test_sc6_budget_expiry_leaves_no_descendants(tmp_path: Path) -> None:
    """SC-6: a real session that spawns long-lived children; none survive the kill."""
    pidfile = tmp_path / "children"
    script = (
        "import subprocess, sys, time\n"
        f"kids = [subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']) for _ in range(2)]\n"
        f"open({str(pidfile)!r}, 'w').write(' '.join(str(k.pid) for k in kids))\n"
        "time.sleep(60)\n"
    )
    with pytest.raises(SessionTimeoutError):
        run_claude([sys.executable, "-c", script], tmp_path, 1.5)
    kids = [int(p) for p in pidfile.read_text().split()]
    assert len(kids) == 2
    deadline = time.monotonic() + 3
    while _alive(kids) and time.monotonic() < deadline:
        time.sleep(0.05)
    leftover = _alive(kids)
    for pid in leftover:  # never leak processes from the suite itself
        os.kill(pid, signal.SIGKILL)
    assert leftover == []


def test_sc6_a_plain_subprocess_kill_would_have_orphaned_them(tmp_path: Path) -> None:
    """SC-6 (control): the old kill-only-the-parent behavior leaves children running,
    so the test above is measuring the fix, not luck."""
    pidfile = tmp_path / "children"
    script = (
        "import subprocess, sys, time\n"
        "k = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"open({str(pidfile)!r}, 'w').write(str(k.pid))\n"
        "time.sleep(60)\n"
    )
    with pytest.raises(subprocess.TimeoutExpired):
        subprocess.run([sys.executable, "-c", script], cwd=tmp_path, timeout=1.5,
                       capture_output=True, check=False)
    kid = int(pidfile.read_text())
    try:
        assert _alive([kid]) == [kid]
    finally:
        os.kill(kid, signal.SIGKILL)
