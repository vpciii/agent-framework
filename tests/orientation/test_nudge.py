"""The weekly nudge.

Verifies spec success criteria (specs/orientation-and-alerts):
- SC-4: the nudge updates an existing `status` issue (opening none) or opens
  exactly one, and sends one push with the next action and the issue link.
- SC-8: with GitHub and the push failing, the nudge still completes and
  reports each failure.
- SC-9: the nudge never touches the worker: it imports nothing from
  `agent_framework.worker`.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from agent_framework import nudge
from agent_framework.alerts import marker

from .test_alerts import FakePush, FakeTracker


def _repo(tmp_path: Path) -> Path:
    d = tmp_path / "proj" / "specs" / "s"
    d.mkdir(parents=True)
    (d / "spec.md").write_text("- **Status:** Draft\n", encoding="utf-8")
    return tmp_path / "proj"


def _no_gh(args: object) -> str:
    return "[]"


def test_sc4_nudge_updates_the_existing_status_issue(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """SC-4: an existing status issue is updated; nothing new is opened; one push."""
    tracker = FakeTracker({marker("status", "weekly"): (12, "https://gh/i/12")})
    push = FakePush()
    assert nudge.main(root=_repo(tmp_path), run=_no_gh, tracker=tracker,
                      push_factory=lambda: push) == 0
    assert tracker.updated == [12] and tracker.created == []
    [(_title, message)] = push.sent
    assert message == "Next: Sign off spec s (Draft) https://gh/i/12"
    assert "github issue: updated #12" in capsys.readouterr().out


def test_sc4_nudge_opens_exactly_one_status_issue_when_none(tmp_path: Path) -> None:
    """SC-4: with no status issue, exactly one is opened, labelled status."""
    tracker, push = FakeTracker(), FakePush()
    nudge.main(root=_repo(tmp_path), run=_no_gh, tracker=tracker, push_factory=lambda: push)
    assert len(tracker.created) == 1 and tracker.created[0][1] == "status"
    assert len(push.sent) == 1 and "Next: Sign off spec s (Draft)" in push.sent[0][1]


def test_sc8_nudge_survives_failing_channels(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """SC-8: gh down and push failing → exit 0, both failures printed."""

    def gh_down(args: object) -> str:
        raise RuntimeError("gh: network down")

    code = nudge.main(root=_repo(tmp_path), run=gh_down, tracker=FakeTracker(fail=True),
                      push_factory=lambda: FakePush(fail=True))
    out = capsys.readouterr().out
    assert code == 0
    assert "Pull request and issue status unavailable: gh: network down" in out
    assert "github issue: failed: gh: network down" in out
    assert "phone push: failed: no route to host" in out


def test_sc9_nudge_imports_nothing_from_the_worker() -> None:
    """SC-9: structurally unable to dispatch a session."""
    tree = ast.parse(inspect.getsource(nudge))
    modules = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    modules += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    assert modules and not [m for m in modules if "worker" in m]
