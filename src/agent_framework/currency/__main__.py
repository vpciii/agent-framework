"""The roster currency check's entry point (scheduled CI, or by hand).

    python -m agent_framework.currency [--roster PATH] [--sync-issue]

Prints one line per finding; exits 1 when any finding is failing or
unchecked, else 0. `--sync-issue` also opens, updates or closes the
tracking issue. Credentials come only from the environment (R-8).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from ..providers.anthropic import AnthropicProvider
from ..providers.google import GoogleProvider
from ..providers.registry import ProviderRegistry
from ..roster import Roster
from .check import check_roster
from .issue import GhIssueTracker, needs_attention, render, sync_issue


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check the roster's models are still served")
    ap.add_argument("--roster", type=Path, default=Path("agent-framework.toml"))
    ap.add_argument("--sync-issue", action="store_true",
                    help="open/update/close the roster-currency tracking issue")
    args = ap.parse_args(argv)

    # An unset Actions secret arrives as "", which would still win the SDK's
    # credential precedence over federation; treat empty as absent.
    for name in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        if os.environ.get(name) == "":
            del os.environ[name]

    registry = ProviderRegistry()
    registry.register("anthropic", AnthropicProvider())
    registry.register("google", GoogleProvider())
    findings = asyncio.run(check_roster(Roster.from_file(args.roster), registry))

    print(render(findings))
    if args.sync_issue:
        print(sync_issue(findings, GhIssueTracker(), _run_url()))
    return 1 if needs_attention(findings) else 0


def _run_url() -> str | None:
    server, repo, run = (os.environ.get(k) for k in
                         ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"))
    return f"{server}/{repo}/actions/runs/{run}" if server and repo and run else None


if __name__ == "__main__":
    sys.exit(main())
