"""Print the resume card for the current repository.

    python -m agent_framework.status [--no-github]

Reads the artifacts under the current directory; adds open PRs and alert
issues from GitHub unless --no-github, and says so when GitHub is unreachable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..proc import Runner, run_command
from .card import GitHubSnapshot, github_snapshot, read_repo, render


def main(argv: list[str] | None = None, *, run: Runner = run_command) -> int:
    ap = argparse.ArgumentParser(description="Print where the project stands and what's next")
    ap.add_argument("--no-github", action="store_true", help="artifacts only; skip gh")
    args = ap.parse_args(argv)

    github: GitHubSnapshot | None = None
    error: str | None = "skipped (--no-github)" if args.no_github else None
    if not args.no_github:
        try:
            github = github_snapshot(run)
        except Exception as e:  # noqa: BLE001 — unreachable GitHub is reported, never fatal (R-2)
            error = str(e).splitlines()[0]
    print(render(read_repo(Path(".")), github, error), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
