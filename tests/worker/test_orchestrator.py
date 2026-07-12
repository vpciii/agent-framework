"""The worker lifecycle, end to end over fake seams.

Verifies:
- SC-2: the session runs in the fresh worktree, on the derived branch,
  with the roster's worker model and the brief as its prompt.
- SC-3: completed → push + declared PR, never a merge.
- SC-4: escalated → no PR, durable escalation artifact.
- SC-5: budget expiry → TimedOut, no PR, worktree preserved and reported.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from agent_framework.errors import SessionTimeoutError
from agent_framework.roster import Roster
from agent_framework.worker.orchestrator import work
from agent_framework.worker.types import Escalated, PrOpened, TimedOut

from .test_brief import _SPEC_MD, _TASKS_MD


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fake repo root: fixture spec artifacts, cwd switched so relative
    worktree paths land in tmp."""
    d = tmp_path / "specs" / "fixture"
    d.mkdir(parents=True)
    (d / "tasks.md").write_text(_TASKS_MD, encoding="utf-8")
    (d / "spec.md").write_text(_SPEC_MD, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _roster() -> Roster:
    return Roster.from_dict(
        {"roles": {"worker": {"provider": "anthropic", "model": "worker-model-x"}}}
    )


class _GitGh:
    """Records every git/gh call; answers the few that need output."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, args: Sequence[str]) -> str:
        call = list(args)
        self.calls.append(call)
        if call[:3] == ["git", "branch", "--list"]:
            return ""  # no branch collision
        if "rev-list" in call:
            return "3\n"  # the session committed
        if call[:3] == ["gh", "pr", "create"]:
            return "https://github.com/x/y/pull/99\n"
        return ""

    def named(self, *prefix: str) -> list[list[str]]:
        return [c for c in self.calls if c[: len(prefix)] == list(prefix)]


def _session(
    payload: object,
) -> tuple[
    list[tuple[list[str], Path, float]], Callable[[Sequence[str], Path, float], None]
]:
    """A fake session seam that records its invocation and writes the result file."""
    record: list[tuple[list[str], Path, float]] = []

    def run(args: Sequence[str], cwd: Path, timeout_s: float) -> None:
        record.append((list(args), cwd, timeout_s))
        cwd.mkdir(parents=True, exist_ok=True)
        (cwd / ".worker-result.json").write_text(json.dumps(payload), encoding="utf-8")

    return record, run


def test_sc2_session_runs_in_worktree_with_roster_model_and_brief(repo: Path) -> None:
    """SC-2: fresh worktree cwd, derived branch, roster's worker model, brief prompt."""
    git = _GitGh()
    record, session = _session({"status": "completed", "detail": "did it"})

    work("fixture", "T-1", _roster(), specs_dir=repo / "specs",
         run=git, session_run=session)

    [(args, cwd, timeout)] = record
    assert cwd == Path(".worktrees/fixture-t-1")  # the fresh, derived worktree
    assert ["git", "worktree", "add", ".worktrees/fixture-t-1", "-b", "feat/fixture-t-1"] in git.calls
    assert "--model" in args and "worker-model-x" in args  # roster binding
    prompt = args[args.index("-p") + 1]
    assert "WIDGET-DETAIL-SENTINEL" in prompt  # the brief is the prompt
    assert timeout == 1800


def test_sc3_completed_session_becomes_declared_pr_and_never_merges(repo: Path) -> None:
    """SC-3: push + PR with the exact Satisfies line; no merge command ever."""
    git = _GitGh()
    _, session = _session({"status": "completed", "detail": "widget spins"})

    outcome = work("fixture", "T-1", _roster(), specs_dir=repo / "specs",
                   run=git, session_run=session)

    assert outcome == PrOpened(
        url="https://github.com/x/y/pull/99", branch="feat/fixture-t-1", task_id="T-1"
    )
    assert git.named("git", "-C", ".worktrees/fixture-t-1", "push")
    [create] = git.named("gh", "pr", "create")
    body = create[create.index("--body") + 1]
    assert "Satisfies: SC-1, SC-2" in body  # exactly the task's criteria
    assert "T-1" in create[create.index("--title") + 1]
    assert not [c for c in git.calls if "merge" in c]  # never merges
    assert git.named("git", "worktree", "remove")  # cleaned up on success


def test_sc4_escalation_writes_artifact_and_opens_no_pr(repo: Path) -> None:
    """SC-4: the contract challenge becomes a durable artifact; no push, no PR."""
    git = _GitGh()
    _, session = _session({
        "status": "escalated",
        "detail": "SC-2 contradicts R-1: the widget cannot both spin and stop",
        "spec_location": "spec.md#success-criteria",
    })

    outcome = work("fixture", "T-1", _roster(), specs_dir=repo / "specs",
                   run=git, session_run=session)

    assert isinstance(outcome, Escalated)
    artifact = Path(outcome.artifact_path)
    assert artifact == repo / "specs" / "fixture" / "escalations" / "t-1-1.md"
    text = artifact.read_text(encoding="utf-8")
    assert "T-1" in text and "cannot both spin and stop" in text
    assert "spec.md#success-criteria" in text
    assert not git.named("gh", "pr", "create") and not git.named(
        "git", "-C", ".worktrees/fixture-t-1", "push"
    )
    assert not git.named("git", "worktree", "remove")  # preserved


def test_sc5_budget_expiry_times_out_with_preserved_worktree(repo: Path) -> None:
    """SC-5: expiry → TimedOut naming the preserved tree; no PR."""
    git = _GitGh()

    def session(args: Sequence[str], cwd: Path, timeout_s: float) -> None:
        raise SessionTimeoutError("over budget")

    outcome = work("fixture", "T-1", _roster(), specs_dir=repo / "specs",
                   timeout_s=5, run=git, session_run=session)

    assert outcome == TimedOut(worktree_path=".worktrees/fixture-t-1")
    assert not git.named("gh", "pr", "create")
    assert not git.named("git", "worktree", "remove")  # preserved for inspection
