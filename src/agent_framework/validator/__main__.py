"""The human consumer's entry point: gate one PR from the command line.

    python -m agent_framework.validator <pr-number> [--roster PATH] [--repo OWNER/NAME]

Prints the verdict JSON on stdout; exits 0 on PASS, 1 on REJECT. The
production adapters are registered here — the only place outside tests
that wires providers to the registry (ADR 0004: validator on Gemini via
the roster; keys from the environment).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from ..providers.anthropic import AnthropicProvider
from ..providers.google import GoogleProvider
from ..providers.registry import register_provider
from ..roster import Roster
from .collector import collect_bundle
from .gate import validate
from .verdict import Pass, verdict_to_json


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Gate one PR through the cite-the-test validator")
    ap.add_argument("pr", type=int, help="PR number to validate")
    ap.add_argument("--roster", type=Path, default=Path("examples/roster.toml"))
    ap.add_argument("--repo", default=None, help="owner/name (default: current repo)")
    args = ap.parse_args(argv)

    register_provider("anthropic", AnthropicProvider())
    register_provider("google", GoogleProvider())

    roster = Roster.from_file(args.roster)
    bundle = collect_bundle(args.pr, repo=args.repo)
    verdict = asyncio.run(validate(bundle, roster))

    print(verdict_to_json(verdict))
    return 0 if isinstance(verdict, Pass) else 1


if __name__ == "__main__":
    sys.exit(main())
