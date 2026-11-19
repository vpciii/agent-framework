"""The checkout: brought to `origin/main` before any issue is read, or refused
(specs/dispatch-from-issue T-6).

The real command over a real repository with a bare remote in `tmp_path`;
only the trackers are faked.

Verifies:
- SC-6: a changed tracked file, a checkout that cannot be fast-forwarded and
  a checkout nested in another repository's working tree each start nothing,
  list nothing, raise one alert and exit 2; an untracked file is no reason to
  refuse; otherwise the checkout is at `origin/main` before the tracker is
  asked for anything, and a pass that moved it starts the command again once.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_framework.alerts import WEBHOOK_ENV
from agent_framework.dispatch import lock
from agent_framework.dispatch.__main__ import RESTARTED_ENV, main
from agent_framework.dispatch.issue import Issue
from agent_framework.dispatch.tick import PassResult, run_pass

from . import test_pass_runs
from .test_pass_runs import AlertTracker, Tracker, _git

repo = test_pass_runs.repo  # the fixture: a clone of a bare remote


class Alerts(AlertTracker):
    def __init__(self) -> None:
        super().__init__()
        self.raised: list[tuple[str, str]] = []

    def create(self, title: str, body: str, label: str) -> str:
        self.raised.append((label, title))
        return super().create(title, body, label)


class Listing(Tracker):
    """Counts the listings and, at each, records where the checkout stood."""

    def __init__(self, repo: Path) -> None:
        super().__init__([])
        self.repo = repo
        self.heads: list[tuple[str, str]] = []

    def list_open(self) -> list[Issue]:
        self.heads.append((_git(self.repo, "rev-parse", "HEAD"),
                           _git(self.repo, "rev-parse", "origin/main")))
        return super().list_open()


@pytest.fixture(autouse=True)
def _no_push(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(WEBHOOK_ENV, raising=False)
    monkeypatch.delenv(RESTARTED_ENV, raising=False)


def _advance_origin(repo: Path, name: str = "new.txt") -> str:
    """Another clone pushes a commit to the remote's main; its id."""
    other = repo.parent / "other"
    if not other.exists():
        _git(repo.parent, "clone", "-q", str(repo.parent / "origin.git"), str(other))
    _git(other, "pull", "-q", "--ff-only")
    (other / name).write_text("fetched\n", encoding="utf-8")
    _git(other, "add", name)
    _git(other, "commit", "-q", "-m", f"feat: {name}")
    _git(other, "push", "-q", "origin", "HEAD:main")
    return _git(other, "rev-parse", "HEAD")


def _refused(repo: Path) -> tuple[int, Listing, Alerts, list[list[str]]]:
    tracker, alerts = Listing(repo), Alerts()
    restarts: list[list[str]] = []

    def restart(argv: list[str]) -> int:
        restarts.append(argv)
        return 0

    code = main([], tracker=tracker, alert_tracker=alerts, restart=restart)
    return code, tracker, alerts, restarts


def _assert_refused(repo: Path) -> None:
    code, tracker, alerts, restarts = _refused(repo)
    assert code == 2
    assert tracker.heads == [] and tracker.events == []  # nothing listed, nothing answered
    assert [label for label, _ in alerts.raised] == ["failed"]
    assert alerts.raised[0][1].startswith("[failed:dispatch/checkout]")
    assert restarts == []
    assert not (repo / ".worktrees" / "fixture-t-1").exists()  # no run started


def test_sc6_a_changed_tracked_file_is_refused(repo: Path) -> None:
    """SC-6: one tracked file edited — refused, and the edit left alone."""
    (repo / "specs/fixture/spec.md").write_text("edited\n", encoding="utf-8")
    _advance_origin(repo)
    before = _git(repo, "rev-parse", "HEAD")
    _assert_refused(repo)
    assert _git(repo, "rev-parse", "HEAD") == before
    assert (repo / "specs/fixture/spec.md").read_text(encoding="utf-8") == "edited\n"


def test_sc6_a_checkout_that_cannot_be_fast_forwarded_is_refused(repo: Path) -> None:
    """SC-6: the checkout and the remote have each moved on — refused."""
    _advance_origin(repo)
    _git(repo, "commit", "-q", "--allow-empty", "-m", "local only")
    local = _git(repo, "rev-parse", "HEAD")
    _assert_refused(repo)
    assert _git(repo, "rev-parse", "HEAD") == local


def test_sc6_a_checkout_inside_another_repositorys_working_tree_is_refused(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SC-6: a clean clone, but under another repository's working tree."""
    outer = repo.parent / "outer"
    _git(repo.parent, "init", "-q", str(outer))
    nested = outer / "proj"
    _git(repo.parent, "clone", "-q", str(repo.parent / "origin.git"), str(nested))
    monkeypatch.chdir(nested)
    _assert_refused(nested)


def test_sc6_an_untracked_file_is_not_refused(repo: Path) -> None:
    """SC-6: an untracked file in the checkout — the pass completes and lists."""
    (repo / "notes.txt").write_text("mine\n", encoding="utf-8")
    code, tracker, alerts, _ = _refused(repo)
    assert code == 0
    assert len(tracker.heads) == 1 and alerts.raised == []
    assert (repo / "notes.txt").read_text(encoding="utf-8") == "mine\n"


def test_sc6_the_checkout_is_at_origin_main_before_the_tracker_is_asked(repo: Path) -> None:
    """SC-6: the remote moved; when the tracker is first asked, the checkout
    has been fast-forwarded to it, files and all."""
    (repo / "notes.txt").write_text("mine\n", encoding="utf-8")
    pushed = _advance_origin(repo)
    tracker = Listing(repo)
    result = run_pass(tracker, alert_tracker=Alerts(), restarted=True)
    assert result is PassResult.COMPLETED
    assert tracker.heads == [(pushed, pushed)]
    assert (repo / "new.txt").read_text(encoding="utf-8") == "fetched\n"


def test_sc6_a_pass_that_moved_the_checkout_starts_again_once(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SC-6: the command asks to start again, with the lock released and
    before listing; started again (marked), it lists and asks no more."""
    _advance_origin(repo)
    tracker, alerts, restarts = Listing(repo), Alerts(), []

    def restart(argv: list[str]) -> int:
        with lock.hold(repo / lock.LOCK_FILE) as taken:
            assert taken  # released before the command starts again
        restarts.append(argv)
        return main(argv, tracker=tracker, alert_tracker=alerts, environ={RESTARTED_ENV: "1"},
                    restart=restart)

    assert main(["--timeout", "60"], tracker=tracker, alert_tracker=alerts,
                restart=restart) == 0
    assert restarts == [["--timeout", "60"]]
    assert len(tracker.heads) == 1 and alerts.raised == []
