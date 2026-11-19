"""The heartbeat: one request for every completed pass, none for a failed one
(specs/dispatch-from-issue T-7).

The real tick over a real repository with a bare remote; the session, `gh`
and the alert channels are faked, and so is the request where it is counted.

Verifies:
- SC-17: a completed pass sends one heartbeat, with an issue or without; a
  failed pass sends none; with no address, or one that refuses, the pass's
  outcome and the command's exit status are unchanged.
"""

from __future__ import annotations

import urllib.request
from functools import partial
from pathlib import Path

import pytest

from agent_framework.alerts import WEBHOOK_ENV
from agent_framework.dispatch.__main__ import RESTARTED_ENV, main
from agent_framework.dispatch.issue import Issue
from agent_framework.dispatch.report import HEARTBEAT_ENV, send_heartbeat
from agent_framework.dispatch.tick import PassResult, run_pass

from . import test_pass_runs
from .test_failures import Alerts, Unreachable
from .test_pass_runs import LIMITS, Runner, Session, Tracker, _issue

repo = test_pass_runs.repo  # the fixture: a clone of a bare remote
URL = "https://ha.example/api/webhook/heartbeat"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (WEBHOOK_ENV, HEARTBEAT_ENV, RESTARTED_ENV):
        monkeypatch.delenv(name, raising=False)


def _beats(tracker: Tracker, *issues: Issue) -> tuple[PassResult, list[str]]:
    sent: list[str] = []

    def opener(req: urllib.request.Request, timeout_s: float) -> int:
        sent.append(req.full_url)
        return 200

    runner = Runner()
    result = run_pass(tracker, limits=LIMITS, run=runner,
                      work_fn=test_pass_runs._tick_seams(runner), session_run=Session([]),
                      alert_tracker=Alerts(), push_factory=lambda: None,
                      heartbeat=partial(send_heartbeat, {HEARTBEAT_ENV: URL}, opener=opener))
    return result, sent


def test_sc17_a_completed_pass_with_an_issue_sends_one_heartbeat(repo: Path) -> None:
    """SC-17: a pass that ran a session sends one request to the address."""
    result, sent = _beats(Tracker([], _issue()))
    assert result is PassResult.COMPLETED and sent == [URL]


def test_sc17_a_completed_pass_without_an_issue_sends_one_heartbeat(repo: Path) -> None:
    """SC-17: a pass that found nothing to do still sends one."""
    result, sent = _beats(Tracker([]))
    assert result is PassResult.COMPLETED and sent == [URL]


def test_sc17_a_failed_pass_sends_no_heartbeat(repo: Path) -> None:
    """SC-17: a pass that cannot list the issues sends none."""
    result, sent = _beats(Unreachable())
    assert result is PassResult.FAILED and sent == []


@pytest.mark.parametrize("env", [{}, {HEARTBEAT_ENV: "http://127.0.0.1:9/heartbeat"}],
                         ids=["no-address", "refused"])
def test_sc17_no_address_or_a_refusing_one_leaves_outcome_and_exit_status(
    repo: Path, env: dict[str, str]
) -> None:
    """SC-17: the command exits 0 for a completed pass and 1 for a failed
    one, whether the heartbeat had no address or its address refused."""
    assert main([], tracker=Tracker([]), alert_tracker=Alerts(), environ=env) == 0
    assert main([], tracker=Unreachable(), alert_tracker=Alerts(), environ=env) == 1
    if env:
        assert send_heartbeat(env, timeout_s=5).startswith("failed: ")
