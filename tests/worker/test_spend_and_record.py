"""A worker session's spend limit and its session record.

Verifies spec success criteria (specs/worker-spend-and-record):
- SC-1: every session is launched with the spend limit and the streamed
  output format; a dispatch cannot remove the limit.
- SC-2: a session stopped at its spend limit is handled as a timeout.
- SC-3: the record is outside the worktree and outlives it.
- SC-4: a session killed at its time budget leaves what it wrote (a real
  process, not a fake).
- SC-5: the record is never published.
- SC-6: `.worker-result.json` alone decides a normal ending.
- SC-7: any other failed exit is reported as before, record kept.
- SC-8: cost and turns are logged, or "cost unknown".
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from agent_framework.errors import SessionResultError, SessionTimeoutError, WorkerError
from agent_framework.worker import __main__ as worker_cli
from agent_framework.worker.orchestrator import work
from agent_framework.worker.session import run_claude
from agent_framework.worker.types import PrOpened, SpendLimitReached

from .test_orchestrator import _GitGh, _roster, repo  # noqa: F401 — shared fixture

_SENTINEL = "RECORD-CONTENT-SENTINEL"
_INIT = {"type": "system", "subtype": "init"}
_SAID = {"type": "assistant", "message": {"content": [{"type": "text", "text": _SENTINEL}]}}
_COMPLETED = {"status": "completed", "detail": "did it"}
_TREE = Path(".worktrees/fixture-t-1")


def _final(subtype: str = "success", cost: float = 0.42, turns: int = 7) -> dict[str, Any]:
    return {"type": "result", "subtype": subtype, "is_error": subtype != "success",
            "total_cost_usd": cost, "num_turns": turns}


Seen = list[tuple[list[str], Path, Path]]


def _fake(
    entries: Sequence[Mapping[str, Any]],
    *,
    result: Mapping[str, Any] | None = None,
    failed_exit: bool = False,
    seen: Seen | None = None,
) -> Callable[[Sequence[str], Path, float, Mapping[str, str], Path], None]:
    """A session that writes `entries` to its record, then optionally the
    result file, then exits as the real seam reports a non-zero exit."""

    def run(args: Sequence[str], cwd: Path, timeout_s: float, env: Mapping[str, str],
            record: Path) -> None:
        if seen is not None:
            seen.append((list(args), cwd, record))
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
        cwd.mkdir(parents=True, exist_ok=True)
        if result is not None:
            (cwd / ".worker-result.json").write_text(json.dumps(result), encoding="utf-8")
        if failed_exit:
            raise SessionResultError("session exited 1: ")

    return run


class _Tracker:
    """Keeps every issue's title, body and label."""

    def __init__(self) -> None:
        self.created: list[tuple[str, str, str]] = []

    def find_open(self, label: str, mark: str) -> tuple[int, str] | None:
        return None

    def create(self, title: str, body: str, label: str) -> str:
        self.created.append((title, body, label))
        return "https://gh/i/40"

    def update(self, number: int, body: str) -> None:
        pass


class _Push:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def __call__(self, title: str, message: str) -> None:
        self.sent.append((title, message))


def _value(args: list[str], flag: str) -> str:
    return args[args.index(flag) + 1]


def test_sc1_every_session_carries_the_spend_limit_and_the_stream_format(
    repo: Path,  # noqa: F811
) -> None:
    """SC-1: the dispatch's limit, or the $10 default, and the stream format;
    a limit that is not a positive amount is refused before anything runs."""
    seen: Seen = []
    work("fixture", "T-1", _roster(), specs_dir=repo / "specs", run=_GitGh(),
         session_run=_fake([_final()], result=_COMPLETED, seen=seen))
    shutil.rmtree(_TREE)  # the fake git removes nothing; free the path for the next run
    work("fixture", "T-1", _roster(), specs_dir=repo / "specs", run=_GitGh(),
         session_run=_fake([_final()], result=_COMPLETED, seen=seen), spend_limit_usd=2.5)

    [(default, _, _), (given, _, _)] = seen
    assert _value(default, "--max-budget-usd") == "10.00"
    assert _value(given, "--max-budget-usd") == "2.50"
    for args in (default, given):
        assert _value(args, "--output-format") == "stream-json" and "--verbose" in args

    for bad in (0.0, -1.0, 0.001, float("nan"), float("inf")):
        calls: Seen = []
        git, refused = _GitGh(), _fake([_final()], result=_COMPLETED, seen=calls)
        with pytest.raises(WorkerError, match="spend limit"):
            work("fixture", "T-1", _roster(), specs_dir=repo / "specs", run=git,
                 session_run=refused, spend_limit_usd=bad)
        assert git.calls == [] and calls == []


def test_sc2_a_session_stopped_at_its_spend_limit_is_handled_as_a_timeout(
    repo: Path, capsys: pytest.CaptureFixture[str]  # noqa: F811
) -> None:
    """SC-2: no PR, worktree kept, a handoff note naming the limit and the
    reported cost, a `timeout` alert, CLI exit 3."""
    git, tracker, push = _GitGh(), _Tracker(), _Push()
    stopped = _fake([_INIT, _final("error_max_budget_usd", cost=10.37, turns=41)],
                    failed_exit=True)

    outcome = work("fixture", "T-1", _roster(), specs_dir=repo / "specs", run=git,
                   session_run=stopped, spend_limit_usd=10, tracker=tracker,
                   push_factory=lambda: push)

    assert outcome == SpendLimitReached(worktree_path=str(_TREE), spend_limit_usd=10.0,
                                        cost_usd=10.37)
    assert isinstance(outcome, SpendLimitReached) and outcome.handoff_path
    assert not git.named("gh", "pr", "create") and not git.having("push")
    assert not git.having("worktree", "remove")
    note = Path(outcome.handoff_path).read_text(encoding="utf-8")
    assert "T-1 (fixture) reached its spend limit" in note
    assert "**Spend limit:** $10.00" in note and "**reported cost:** $10.37" in note
    [(title, _, label)] = tracker.created
    assert (title, label) == ("[timeout:fixture/T-1] T-1 of fixture reached its spend limit",
                              "timeout")
    assert len(push.sent) == 1

    (repo / "agent-framework.toml").write_text(
        '[roles]\nworker = { provider = "anthropic", model = "m" }\n', encoding="utf-8")
    code = worker_cli.main(["fixture", "T-1"], work_fn=lambda *a, **k: outcome)
    assert code == 3
    assert json.loads(capsys.readouterr().out)["outcome"] == "spend_limit_reached"


def test_sc2_the_cli_passes_its_spend_limit_to_the_dispatch(repo: Path) -> None:  # noqa: F811
    """SC-2/SC-1 at the edge: `--spend-limit` reaches `work()`; absent, the default."""
    (repo / "agent-framework.toml").write_text(
        '[roles]\nworker = { provider = "anthropic", model = "m" }\n', encoding="utf-8")
    given: list[object] = []

    def work_fn(*args: object, **kwargs: object) -> PrOpened:
        given.append(kwargs.get("spend_limit_usd"))
        return PrOpened(url="u", branch="b", task_id="T-1")

    worker_cli.main(["fixture", "T-1", "--spend-limit", "3.5"], work_fn=work_fn)
    worker_cli.main(["fixture", "T-1"], work_fn=work_fn)
    assert given == [3.5, 10.0]


def test_sc3_the_record_is_outside_the_worktree_and_outlives_it(repo: Path) -> None:  # noqa: F811
    """SC-3: the session's output is in a record beside the worktrees, which
    is still there once the worktree is gone."""
    seen: Seen = []
    outcome = work("fixture", "T-1", _roster(), specs_dir=repo / "specs", run=_GitGh(),
                   session_run=_fake([_INIT, _SAID, _final()], result=_COMPLETED, seen=seen))

    assert isinstance(outcome, PrOpened)
    [(_, cwd, record)] = seen
    assert record.parent == Path(".worktrees/records")
    assert re.fullmatch(r"fixture-t-1-\d{8}T\d{6}Z\.jsonl", record.name)
    assert not record.resolve().is_relative_to(cwd.resolve())
    shutil.rmtree(cwd)  # what `git worktree remove` does to the tree
    assert _SENTINEL in record.read_text(encoding="utf-8")


def test_sc4_a_session_killed_at_its_time_budget_leaves_its_record(tmp_path: Path) -> None:
    """SC-4: a real process writes, then overruns; its record keeps what it wrote."""
    record = tmp_path / "records" / "session.jsonl"
    script = f"import time; print({json.dumps(json.dumps(_INIT))}, flush=True); time.sleep(30)"

    with pytest.raises(SessionTimeoutError):
        run_claude([sys.executable, "-c", script], tmp_path, 1.5, {}, record)

    assert record.read_text(encoding="utf-8") == json.dumps(_INIT) + "\n"


def test_sc5_the_record_is_never_published(repo: Path) -> None:  # noqa: F811
    """SC-5: neither the record nor anything in it reaches the worktree, a
    git command, the pull request or an alert."""
    seen: Seen = []
    git = _GitGh()
    work("fixture", "T-1", _roster(), specs_dir=repo / "specs", run=git,
         session_run=_fake([_INIT, _SAID, _final()], result=_COMPLETED, seen=seen))
    [(_, cwd, record)] = seen
    assert not any(_SENTINEL in p.read_text(encoding="utf-8", errors="replace")
                   for p in cwd.rglob("*") if p.is_file())
    assert not [c for c in git.calls if any(record.name in a or _SENTINEL in a for a in c)]

    shutil.rmtree(cwd)
    tracker, push = _Tracker(), _Push()
    work("fixture", "T-1", _roster(), specs_dir=repo / "specs", run=_GitGh(),
         session_run=_fake([_INIT, _SAID, _final("error_max_budget_usd")], failed_exit=True),
         tracker=tracker, push_factory=lambda: push)
    published = [text for issue in tracker.created for text in issue[:2]]
    published += [text for message in push.sent for text in message]
    assert published and not any(_SENTINEL in t or "records/" in t for t in published)


def test_sc6_the_result_file_alone_decides_a_normal_ending(repo: Path) -> None:  # noqa: F811
    """SC-6: a clean exit is judged by `.worker-result.json`, whatever the record says."""
    with pytest.raises(SessionResultError, match="wrote no"):
        work("fixture", "T-1", _roster(), specs_dir=repo / "specs", run=_GitGh(),
             session_run=_fake([_final("success")]))

    shutil.rmtree(_TREE)
    outcome = work("fixture", "T-1", _roster(), specs_dir=repo / "specs", run=_GitGh(),
                   session_run=_fake([_final("error_max_budget_usd")], result=_COMPLETED))
    assert isinstance(outcome, PrOpened)


@pytest.mark.parametrize("entries", [[_INIT, _final("error_during_execution")], []],
                         ids=["another-error", "empty-record"])
def test_sc7_any_other_failed_exit_is_reported_as_before(
    repo: Path, entries: list[dict[str, Any]]  # noqa: F811
) -> None:
    """SC-7: a failed exit that is not the spend limit stays a
    `SessionResultError`, and its record is kept."""
    seen: Seen = []
    with pytest.raises(SessionResultError, match="exited 1"):
        work("fixture", "T-1", _roster(), specs_dir=repo / "specs", run=_GitGh(),
             session_run=_fake(entries, failed_exit=True, seen=seen))
    [(_, _, record)] = seen
    assert record.is_file()


def test_sc8_cost_and_turns_are_logged_or_unknown(
    repo: Path, caplog: pytest.LogCaptureFixture  # noqa: F811
) -> None:
    """SC-8: the final entry's cost and turns are logged; without one, "cost
    unknown" — and the outcome is the same either way."""
    caplog.set_level(logging.INFO, logger="agent_framework.worker.orchestrator")
    first = work("fixture", "T-1", _roster(), specs_dir=repo / "specs", run=_GitGh(),
                 session_run=_fake([_INIT, _final(cost=0.42, turns=7)], result=_COMPLETED))
    assert "cost $0.42 over 7 turn(s)" in caplog.text

    caplog.clear()
    shutil.rmtree(_TREE)
    second = work("fixture", "T-1", _roster(), specs_dir=repo / "specs", run=_GitGh(),
                  session_run=_fake([_INIT], result=_COMPLETED))
    assert "cost unknown" in caplog.text
    assert isinstance(first, PrOpened) and first == second
