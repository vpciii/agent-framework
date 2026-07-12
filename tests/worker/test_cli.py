"""The worker CLI: outcome JSON on stdout, composable exit codes.

Delivery-edge tests (T-5) — the core criteria are covered by the SC-cited
tests in test_brief / test_worktree / test_orchestrator.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agent_framework.errors import UnknownTaskError
from agent_framework.worker.__main__ import main
from agent_framework.worker.types import Escalated, PrOpened, TimedOut, WorkerOutcome

_ROSTER = """\
[roles]
worker = { provider = "anthropic", model = "m" }
"""


@pytest.fixture
def roster_file(tmp_path: Path) -> Path:
    p = tmp_path / "roster.toml"
    p.write_text(_ROSTER, encoding="utf-8")
    return p


def _run(
    capsys: pytest.CaptureFixture[str], roster: Path, outcome: WorkerOutcome | Exception
) -> tuple[int, dict[str, Any]]:
    def work_fn(*args: Any, **kwargs: Any) -> WorkerOutcome:
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    # Session args starting with "-" require the "=" form (argparse):
    # e.g. --session-arg=--dangerously-skip-permissions
    code = main(
        ["fixture", "T-1", "--roster", str(roster), "--session-arg=--verbose"],
        work_fn=work_fn,
    )
    return code, json.loads(capsys.readouterr().out)


def test_pr_opened_exits_zero(capsys: pytest.CaptureFixture[str], roster_file: Path) -> None:
    code, out = _run(capsys, roster_file, PrOpened(url="u", branch="b", task_id="T-1"))
    assert code == 0
    assert out == {"outcome": "pr_opened", "url": "u", "branch": "b", "task_id": "T-1"}


def test_escalated_exits_two(capsys: pytest.CaptureFixture[str], roster_file: Path) -> None:
    code, out = _run(capsys, roster_file, Escalated(artifact_path="a.md", detail="q"))
    assert code == 2 and out["outcome"] == "escalated"


def test_timed_out_exits_three(capsys: pytest.CaptureFixture[str], roster_file: Path) -> None:
    code, out = _run(capsys, roster_file, TimedOut(worktree_path=".worktrees/x"))
    assert code == 3 and out["outcome"] == "timed_out"


def test_worker_error_exits_three_with_detail(
    capsys: pytest.CaptureFixture[str], roster_file: Path
) -> None:
    code, out = _run(capsys, roster_file, UnknownTaskError("task T-1 not found"))
    assert code == 3
    assert out == {"outcome": "error", "detail": "task T-1 not found"}
