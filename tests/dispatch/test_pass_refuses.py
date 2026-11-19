"""A pass that refuses (specs/dispatch-from-issue T-4).

A fake tracker and a real repository with a bare remote in `tmp_path`.

Verifies:
- SC-1: for each refused case a pass starts no session.
- SC-2: with no author, and with dispatch switched off, the tracker is never
  asked for issues and the pass says why.
- SC-3: a pass made while another process holds the lock lists nothing and
  leaves its issue open and labelled.
- SC-9: each refusal leaves exactly one comment, the label removed and the
  issue closed, and marker text in the issue's title is not in the comment.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from agent_framework.dispatch.__main__ import main
from agent_framework.dispatch.issue import Issue
from agent_framework.dispatch.tick import LIST_FIELDS, GhDispatchTracker, PassResult, run_pass
from agent_framework.worker.types import WorkerOutcome

MARKER = "ZQX-MARKER-7731"

_TASKS = """\
# Tasks: Example

### [ ] T-1 — Open, claims a criterion
- **Satisfies:** SC-1

### [x] T-2 — Done
- **Satisfies:** SC-1

### [ ] T-3 — Claims nothing
- **Satisfies:** —
"""


@dataclass
class FakeIssue:
    issue: Issue
    labels: set[str] = field(default_factory=lambda: {"dispatch"})
    comments: list[str] = field(default_factory=list)
    open: bool = True


class FakeTracker:
    def __init__(self, *issues: Issue, fail_list: bool = False) -> None:
        self.issues = {i.number: FakeIssue(i) for i in issues}
        self.listed = 0
        self.fail_list = fail_list

    def list_open(self) -> list[Issue]:
        self.listed += 1
        if self.fail_list:
            raise RuntimeError("gh: could not reach GitHub")
        return [f.issue for f in self.issues.values() if f.open and "dispatch" in f.labels]

    def remove_label(self, number: int) -> None:
        self.issues[number].labels.discard("dispatch")

    def comment(self, number: int, body: str) -> None:
        self.issues[number].comments.append(body)

    def close(self, number: int) -> None:
        self.issues[number].open = False


class NoSession:
    """A `work()` that records every call: none may come from a refusal."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> WorkerOutcome:
        self.calls.append(args)
        raise AssertionError("a refused issue started a session")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _issue(title: str, author: str = "vpciii", number: int = 7, day: int = 1) -> Issue:
    return Issue(number=number, title=title, author=author,
                 opened=datetime(2026, 11, day, tzinfo=UTC))


def _seed(root: Path, dispatch_table: str) -> None:
    for rel, text in {
        "agent-framework.toml": dispatch_table,
        "specs/example/tasks.md": _TASKS,
        "specs/example/spec.md": "# Spec: Example\n",
        ".gitignore": ".worktrees/\n",
    }.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "seed")
    _git(root, "push", "-q", "origin", "HEAD:main")


def _repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, table: str) -> Path:
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    root = tmp_path / "proj"
    _git(tmp_path, "clone", "-q", str(origin), str(root))
    _seed(root, table)
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return _repo(tmp_path, monkeypatch, '[dispatch]\nauthor = "vpciii"\n')


_REFUSED = [
    pytest.param(_issue("example T-1", author=f"someone-{MARKER.lower()}"), id="author"),
    pytest.param(_issue(f"example T-1 {MARKER}"), id="title"),
    pytest.param(_issue(f"{MARKER} T-1"), id="title-case"),
    pytest.param(_issue("nosuchspec T-1"), id="unknown-spec"),
    pytest.param(_issue("example T-9"), id="unknown-task"),
    pytest.param(_issue("example T-2"), id="done"),
    pytest.param(_issue("example T-3"), id="no-criterion"),
]


@pytest.mark.parametrize("issue", _REFUSED)
def test_sc1_a_refused_issue_starts_no_session(repo: Path, issue: Issue) -> None:
    """SC-1: another author, any other title, an unknown spec or task, a task
    done or claiming nothing — the pass completes and no session starts."""
    tracker, session = FakeTracker(issue), NoSession()
    assert run_pass(tracker, work_fn=session) is PassResult.COMPLETED
    assert session.calls == []
    assert not (repo / ".worktrees" / "example-t-1").exists()


@pytest.mark.parametrize("issue", _REFUSED)
def test_sc9_each_refusal_leaves_one_comment_no_label_and_a_closed_issue(
    repo: Path, issue: Issue
) -> None:
    """SC-9: exactly one comment, the label removed, the issue closed; the
    comment names the reason and carries none of the issue's text."""
    tracker = FakeTracker(issue)
    run_pass(tracker, work_fn=NoSession())
    fake = tracker.issues[issue.number]
    assert len(fake.comments) == 1
    assert "dispatch" not in fake.labels
    assert not fake.open
    comment = fake.comments[0]
    assert comment.startswith("Refused") and "Reason code:" in comment
    assert MARKER not in comment and MARKER.lower() not in comment
    assert issue.title not in comment and issue.author not in comment


def test_sc9_marker_text_in_the_title_is_not_in_the_comment(repo: Path) -> None:
    """SC-9: a title carrying marker text is refused for its shape, and the
    one comment it gets quotes none of it."""
    tracker = FakeTracker(_issue(f"example T-1 {MARKER}"))
    run_pass(tracker, work_fn=NoSession())
    (comment,) = tracker.issues[7].comments
    assert "title-shape" in comment and MARKER not in comment


@pytest.mark.parametrize(
    ("table", "why"),
    [
        pytest.param("", "no [dispatch] author", id="no-author"),
        pytest.param('[dispatch]\nauthor = "vpciii"\nenabled = false\n',
                     "enabled is false", id="disabled"),
    ],
)
def test_sc2_with_dispatch_off_the_tracker_is_never_asked_and_the_pass_says_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
    table: str, why: str,
) -> None:
    """SC-2: no author, or `enabled = false`: nothing listed, nothing
    started, the log says why, and the pass completes."""
    _repo(tmp_path, monkeypatch, table)
    tracker, session = FakeTracker(_issue("example T-1")), NoSession()
    caplog.set_level("INFO")
    assert run_pass(tracker, work_fn=session) is PassResult.COMPLETED
    assert tracker.listed == 0 and session.calls == []
    assert tracker.issues[7].open and tracker.issues[7].comments == []
    assert any(why in r.getMessage() for r in caplog.records)


def test_sc3_a_pass_while_another_process_holds_the_lock_lists_nothing(
    repo: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """SC-3: with the lock held by a second, real process, the pass lists
    nothing, starts nothing and leaves its issue open and labelled."""
    lock = repo / ".worktrees" / "dispatch.lock"
    lock.parent.mkdir(exist_ok=True)
    holder = subprocess.Popen(
        [sys.executable, "-c",
         ("import fcntl,os,sys\n"
          "fd=os.open(sys.argv[1],os.O_RDWR|os.O_CREAT)\n"
          "fcntl.flock(fd,fcntl.LOCK_EX)\nprint('held',flush=True)\nsys.stdin.read()"),
         str(lock)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
    )
    try:
        assert holder.stdout is not None and holder.stdout.readline().strip() == "held"
        tracker, session = FakeTracker(_issue("example T-2")), NoSession()
        caplog.set_level("INFO")
        assert run_pass(tracker, work_fn=session) is PassResult.COMPLETED
    finally:
        holder.kill()
        holder.wait()
    fake = tracker.issues[7]
    assert tracker.listed == 0 and session.calls == []
    assert fake.open and fake.labels == {"dispatch"} and fake.comments == []
    assert any("another pass is running" in r.getMessage() for r in caplog.records)


def test_an_accepted_issue_is_left_as_it_was_found(repo: Path) -> None:
    tracker, session = FakeTracker(_issue("example T-1")), NoSession()
    assert run_pass(tracker, work_fn=session) is PassResult.COMPLETED
    fake = tracker.issues[7]
    assert fake.open and fake.labels == {"dispatch"} and fake.comments == []
    assert session.calls == []


def test_only_the_oldest_issue_is_answered(repo: Path) -> None:
    newer = _issue("example T-2", number=3, day=5)
    older = _issue("example T-3", number=9, day=2)
    tracker = FakeTracker(newer, older)
    run_pass(tracker, work_fn=NoSession())
    assert not tracker.issues[9].open
    assert tracker.issues[3].open and tracker.issues[3].comments == []


def test_a_listing_that_fails_is_a_failed_pass(repo: Path) -> None:
    tracker = FakeTracker(_issue("example T-2"), fail_list=True)
    assert run_pass(tracker, work_fn=NoSession()) is PassResult.FAILED
    assert main([], tracker=FakeTracker(fail_list=True)) == 1


def test_a_fetch_that_fails_is_a_failed_pass(repo: Path) -> None:
    _git(repo, "remote", "set-url", "origin", str(repo.parent / "gone.git"))
    tracker = FakeTracker(_issue("example T-2"))
    assert run_pass(tracker, work_fn=NoSession()) is PassResult.FAILED
    assert tracker.listed == 0 and tracker.issues[7].open


def test_the_command_exits_0_for_a_completed_pass(repo: Path) -> None:
    tracker = FakeTracker(_issue("example T-2"))
    assert main(["--timeout", "60"], tracker=tracker) == 0
    assert not tracker.issues[7].open


def test_the_gh_tracker_asks_for_four_fields_and_nothing_else() -> None:
    """R-6: never the body, the comments or the labels."""
    seen: list[list[str]] = []

    def fake(args: Sequence[str]) -> str:
        seen.append(list(args))
        return json.dumps([{"number": 4, "title": "example T-1",
                            "author": {"login": "vpciii"},
                            "createdAt": "2026-11-19T10:00:00Z"}])

    (issue,) = GhDispatchTracker(fake).list_open()
    assert issue == Issue(4, "example T-1", "vpciii", datetime(2026, 11, 19, 10, tzinfo=UTC))
    assert seen[0][seen[0].index("--json") + 1] == LIST_FIELDS == "number,title,author,createdAt"
