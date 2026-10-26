"""The weekly nudge: the resume card to its GitHub issue, the next action to vpc's phone.

    python -m agent_framework.nudge

Run by a weekly launchd agent from the repository root (R-3). It only reads
artifacts and reports; it never dispatches a worker session (R-8), so it
imports nothing from `agent_framework.worker`. Channel failures are printed,
never fatal (R-7).
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from .alerts import GhIssueTracker, IssueTracker, Push, notify, push_from_env
from .proc import Runner, run_command
from .status.card import GitHubSnapshot, github_snapshot, next_action, read_repo, render

STATUS_KIND = "status"
STATUS_KEY = "weekly"


def main(
    argv: list[str] | None = None,
    *,
    root: Path = Path("."),
    run: Runner = run_command,
    tracker: IssueTracker | None = None,
    push_factory: Callable[[], Push | None] = push_from_env,
) -> int:
    state = read_repo(root)
    github: GitHubSnapshot | None = None
    error: str | None = None
    try:
        github = github_snapshot(run)
    except Exception as e:  # noqa: BLE001 — reported on the card, never fatal (R-2, R-7)
        error = (str(e).splitlines() or [type(e).__name__])[0]

    card = render(state, github, error)
    action = next_action(state, github)
    report = notify(
        STATUS_KIND, STATUS_KEY, f"{state.name} resume card", card, f"Next: {action}",
        tracker=tracker or GhIssueTracker(run), push=push_factory(), update_existing=True,
    )
    print(card, end="")
    print("\n".join(report.lines()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
