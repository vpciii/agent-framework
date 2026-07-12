"""The session seam and the `.worker-result.json` contract.

T-2 infrastructure tests (SC-5's orchestrator-level citation lands with
T-3): result-contract happy paths, every loud deviation, and a *real*
timeout kill through the default subprocess seam.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from agent_framework.errors import SessionResultError, SessionTimeoutError
from agent_framework.worker.session import run_claude, run_session

def _noop_runner(
    record: list[tuple[list[str], Path, float]],
) -> Callable[[Sequence[str], Path, float], None]:
    def run(args: Sequence[str], cwd: Path, timeout_s: float) -> None:
        record.append((list(args), cwd, timeout_s))

    return run


def _write_result(worktree: Path, payload: object) -> None:
    (worktree / ".worker-result.json").write_text(json.dumps(payload), encoding="utf-8")


def test_completed_result_round_trips(tmp_path: Path) -> None:
    _write_result(tmp_path, {"status": "completed", "detail": "done the thing"})
    record: list[tuple[list[str], Path, float]] = []

    result = run_session(
        "the brief", tmp_path, model="worker-model", timeout_s=60, run=_noop_runner(record)
    )

    assert result.status == "completed" and result.detail == "done the thing"
    [(cmd, cwd, timeout)] = record
    assert cmd[:3] == ["claude", "-p", "the brief"]
    assert "--model" in cmd and "worker-model" in cmd
    assert cwd == tmp_path and timeout == 60


def test_escalated_result_carries_spec_location(tmp_path: Path) -> None:
    _write_result(
        tmp_path,
        {"status": "escalated", "detail": "SC text contradicts R text",
         "spec_location": "spec.md#requirements"},
    )
    result = run_session("b", tmp_path, model="m", timeout_s=60, run=_noop_runner([]))
    assert result.status == "escalated"
    assert result.spec_location == "spec.md#requirements"


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        (None, "wrote no"),  # no file at all
        ("not json{", "not valid JSON"),
        # Valid JSON that is not an object — the validator's own live REJECT
        # finding on this PR (#27): must be the typed error, not AttributeError.
        ("null", "must be a JSON object"),
        ("[]", "must be a JSON object"),
        ('"status-text"', "must be a JSON object"),
        ({"status": "maybe", "detail": "x"}, "invalid status"),
        ({"status": "completed"}, "non-empty detail"),
        ({"status": "escalated", "detail": "q", "spec_location": 7}, "must be a string"),
    ],
)
def test_result_contract_deviations_are_loud(
    tmp_path: Path, payload: object, match: str
) -> None:
    if isinstance(payload, str):
        (tmp_path / ".worker-result.json").write_text(payload, encoding="utf-8")
    elif payload is not None:
        _write_result(tmp_path, payload)
    with pytest.raises(SessionResultError, match=match):
        run_session("b", tmp_path, model="m", timeout_s=60, run=_noop_runner([]))


def test_default_seam_kills_on_budget_expiry(tmp_path: Path) -> None:
    """A real subprocess overrunning its budget is killed and raises the
    typed timeout — the enforcement mechanism itself, not a fake."""
    with pytest.raises(SessionTimeoutError, match="budget"):
        run_claude(
            [sys.executable, "-c", "import time; time.sleep(30)"], tmp_path, 0.2
        )


def test_default_seam_missing_cli_is_loud(tmp_path: Path) -> None:
    with pytest.raises(SessionResultError, match="not installed"):
        run_claude(["definitely-not-a-real-binary-xyz"], tmp_path, 5)
