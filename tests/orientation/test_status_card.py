"""The resume card.

Verifies spec success criteria (specs/orientation-and-alerts):
- SC-1: the card lists non-terminal specs, their open tasks, bets and
  escalation files, and renders identically twice.
- SC-2: the next action follows the precedence rule, exactly one shown.
- SC-3: with GitHub unavailable, the card says so instead of omitting it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_framework.status import __main__ as status_cli
from agent_framework.status.card import (
    GitHubItem,
    GitHubSnapshot,
    next_action,
    read_repo,
    render,
)

_EMPTY_GH = GitHubSnapshot((), ())


def _spec(root: Path, slug: str, status: str, tasks: str | None = None, extra: str = "") -> None:
    d = root / "specs" / slug
    d.mkdir(parents=True)
    (d / "spec.md").write_text(f"# Spec: {slug}\n\n- **Status:** {status}\n{extra}", encoding="utf-8")
    if tasks is not None:
        (d / "tasks.md").write_text(tasks, encoding="utf-8")


def _bet(root: Path, slug: str, status: str) -> None:
    d = root / "planning" / slug
    d.mkdir(parents=True)
    (d / "bet.md").write_text(f"# Bet\n\n- **Status:** {status}\n", encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    _spec(root, "alpha", "Approved", "### [x] T-1 — done thing (#3)\n\n### [ ] T-2 — widget spins\n")
    _spec(root, "beta", "Implemented")
    _spec(root, "gamma", "Draft")
    _bet(root, "bet-one", "Placed")
    esc = root / "specs" / "alpha" / "escalations"
    esc.mkdir()
    (esc / "t-2-1.md").write_text("# Escalation\n\n- **Status:** Open\n", encoding="utf-8")
    return root


def test_sc1_card_lists_active_work_and_is_deterministic(repo: Path) -> None:
    """SC-1: non-terminal specs + statuses, open tasks, bets, escalation files; stable output."""
    card = render(read_repo(repo), _EMPTY_GH)
    assert "`alpha` — Approved" in card and "`gamma` — Draft" in card
    assert "beta" not in card  # Implemented is terminal
    assert "`alpha` T-2 — widget spins" in card and "T-1" not in card
    assert "`bet-one` — Placed" in card
    assert "`specs/alpha/escalations/t-2-1.md` — Open" in card
    assert render(read_repo(repo), _EMPTY_GH) == card
    assert card.count("**Next action:**") == 1


def test_sc2_next_action_precedence(tmp_path: Path) -> None:
    """SC-2: each rule branch, highest first; exactly one action."""
    root = tmp_path / "p"
    _bet(root, "lonely", "Placed")
    assert next_action(read_repo(root), _EMPTY_GH) == "Write the spec for bet lonely"

    pr = GitHubSnapshot((GitHubItem(7, "a PR", "u/7"),), ())
    assert next_action(read_repo(root), pr).startswith("Review PR #7")

    _spec(root, "compact", "Approved")  # no tasks.md
    assert next_action(read_repo(root), pr) == "Implement spec compact (compact spec)"

    _spec(root, "tasked", "Approved", "### [ ] T-4 — do it\n")
    assert next_action(read_repo(root), pr) == "Implement spec compact (compact spec)"  # slug order

    _spec(root, "aaa-draft", "Under review")
    assert next_action(read_repo(root), pr) == "Sign off spec aaa-draft (Under review)"

    alert = GitHubSnapshot((), (GitHubItem(9, "[timeout:x/T-1] t", "u/9"),))
    assert next_action(read_repo(root), alert).startswith("Answer #9")

    # Without GitHub, an Open escalation file stands in for the alert issue.
    esc = root / "specs" / "tasked" / "escalations"
    esc.mkdir()
    (esc / "t-4-1.md").write_text("- **Status:** Open\n", encoding="utf-8")
    assert next_action(read_repo(root), None) == "Answer the escalation in specs/tasked/escalations/t-4-1.md"


def test_sc2_bet_with_a_spec_is_not_pending(tmp_path: Path) -> None:
    """SC-2: a Placed bet whose spec names its planning folder needs no spec."""
    root = tmp_path / "p"
    _bet(root, "b", "Placed")
    _spec(root, "s", "Implemented", extra="- **Planning record:** `planning/b/`\n")
    assert next_action(read_repo(root), _EMPTY_GH) == "Nothing pending"


def test_sc3_unavailable_github_is_stated(repo: Path) -> None:
    """SC-3: the GitHub section says it's unavailable, with the reason."""
    card = render(read_repo(repo), None, "gh: not logged in")
    assert "Pull request and issue status unavailable: gh: not logged in" in card


def test_sc3_cli_reports_a_failing_gh(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SC-3: the CLI keeps going when gh fails, and says so on the card."""
    monkeypatch.chdir(repo)

    def failing(args: object) -> str:
        raise RuntimeError("command failed (1): gh pr list\nauth required")

    assert status_cli.main([], run=failing) == 0
    out = capsys.readouterr().out
    assert "unavailable: command failed (1): gh pr list" in out
    assert "**Next action:** Answer the escalation in specs/alpha/escalations/t-2-1.md" in out
