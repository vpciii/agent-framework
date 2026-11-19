"""What a push may say: `[alerts] push_detail` and the worker's question.

Drives the real orchestrator; only the session, `gh`, the Home Assistant
push and Pushover's network call are faked.

Verifies spec success criteria (specs/pushover-push):
- SC-5: with no `[alerts]` table, or `push_detail = "pointer"`, an
  escalation's decrypted Pushover message holds none of the worker's
  question; with `"full"` it holds it and the Home Assistant push does not;
  a timeout's and a refused handoff's messages hold only the short line.
"""

from __future__ import annotations

import urllib.parse
from pathlib import Path

import pytest
from orientation.test_pushover import KEY, TOKEN, USER, FakePost, decrypt

from agent_framework import alerts
from agent_framework.project import AlertsConfig, ProjectConfig, load_project_config
from agent_framework.worker.orchestrator import work
from agent_framework.worker.types import Escalated, HandoffRefused, TimedOut

from .test_handoff_refused import _FORBIDDEN, _RealGitFakeGh, project_repo  # noqa: F401
from .test_handoff_refused import _session as _committing_session
from .test_orchestrator import _GitGh, _roster, _session, repo  # noqa: F401
from .test_timeout_and_escalation_alerts import (
    FakePush,
    FakeTracker,
    _GitWithState,
    _timeout_session,
)

FULL = ProjectConfig(alerts=AlertsConfig(push_detail="full"))

QUESTION_MARKER = "QUESTION-MARKER-7f3e"


@pytest.fixture
def post(monkeypatch: pytest.MonkeyPatch) -> FakePost:
    """Pushover configured, its network call recorded."""
    monkeypatch.setenv("AF_PUSHOVER_TOKEN", TOKEN)
    monkeypatch.setenv("AF_PUSHOVER_USER", USER)
    monkeypatch.setenv("AF_PUSHOVER_KEY", KEY)
    fake = FakePost()
    monkeypatch.setattr(alerts, "_post", fake)
    return fake


def _message(post: FakePost) -> str:
    [(_, body, _)] = post.requests
    return decrypt(dict(urllib.parse.parse_qsl(body.decode()))["message"])


def _escalate(repo: Path, project: ProjectConfig, push: FakePush) -> None:  # noqa: F811
    _, session = _session({"status": "escalated", "spec_location": "spec.md#r-1",
                           "detail": f"Which way? {QUESTION_MARKER}"})
    outcome = work("fixture", "T-1", _roster(), specs_dir=repo / "specs", run=_GitGh(),
                   session_run=session, tracker=FakeTracker(), push_factory=lambda: push,
                   project=project)
    assert isinstance(outcome, Escalated)


@pytest.mark.parametrize("toml", ["", "[project]\n", '[alerts]\npush_detail = "pointer"\n'])
def test_sc5_by_default_the_escalation_push_holds_none_of_the_question(
    repo: Path, post: FakePost, tmp_path: Path, toml: str,  # noqa: F811
) -> None:
    """SC-5: no `[alerts]` table, or `"pointer"` → the decrypted message is
    the short line and holds none of the worker's question."""
    (tmp_path / "agent-framework.toml").write_text(toml, encoding="utf-8")
    push = FakePush()
    _escalate(repo, load_project_config(tmp_path), push)
    message = _message(post)
    assert QUESTION_MARKER not in message
    assert message == "T-1 of fixture needs a decision."
    assert all(QUESTION_MARKER not in m for _, m in push.sent)


def test_sc5_full_carries_the_question_to_pushover_and_not_home_assistant(
    repo: Path, post: FakePost, tmp_path: Path,  # noqa: F811
) -> None:
    """SC-5: `"full"` → the decrypted message holds the question; the Home
    Assistant push for the same alert says only what it says today."""
    (tmp_path / "agent-framework.toml").write_text(
        '[alerts]\npush_detail = "full"\n', encoding="utf-8")
    push = FakePush()
    _escalate(repo, load_project_config(tmp_path), push)
    assert QUESTION_MARKER in _message(post)
    [(title, message)] = push.sent
    assert QUESTION_MARKER not in title + message
    assert message == "T-1 of fixture needs a decision. https://gh/i/40"


def test_sc5_with_full_a_timeout_push_holds_only_the_short_line(
    repo: Path, post: FakePost,  # noqa: F811
) -> None:
    """SC-5: `"full"` passes no detail with a timeout."""
    outcome = work("fixture", "T-1", _roster(), specs_dir=repo / "specs", timeout_s=5,
                   run=_GitWithState(), session_run=_timeout_session, tracker=FakeTracker(),
                   push_factory=lambda: None, project=FULL)
    assert isinstance(outcome, TimedOut)
    assert _message(post) == "T-1 of fixture timed out."


def test_sc5_with_full_a_refused_handoff_push_holds_only_the_short_line(
    project_repo: Path, post: FakePost,  # noqa: F811
) -> None:
    """SC-5: `"full"` passes no detail with a refused handoff."""
    outcome = work("fixture", "T-1", _roster(), run=_RealGitFakeGh(),
                   session_run=_committing_session(_FORBIDDEN), tracker=FakeTracker(),
                   push_factory=lambda: None, project=FULL)
    assert isinstance(outcome, HandoffRefused)
    assert _message(post) == "T-1 of fixture: handoff refused."
