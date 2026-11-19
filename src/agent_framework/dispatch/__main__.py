"""The dispatch tick: one pass over the open `dispatch` issues, then exit.

    agent-framework-dispatch [--roster FILE] [--timeout SECONDS] [--spend-limit USD]
    python -m agent_framework.dispatch ...

Exit 0 when the pass completed (whatever it found), 1 when it failed. The
limits default to the worker's own. Run from the checkout's root.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from ..worker.session import DEFAULT_SPEND_LIMIT_USD
from .tick import DispatchTracker, GhDispatchTracker, Limits, PassResult, run_pass


def main(argv: list[str] | None = None, *, tracker: DispatchTracker | None = None) -> int:
    ap = argparse.ArgumentParser(description="Make one dispatch pass and exit")
    ap.add_argument("--roster", type=Path, default=Path("agent-framework.toml"))
    ap.add_argument("--timeout", type=float, default=1800, metavar="SECONDS")
    ap.add_argument("--spend-limit", type=float, default=DEFAULT_SPEND_LIMIT_USD,
                    metavar="USD", help="a run's spend limit, at list price")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    limits = Limits(roster=args.roster, timeout_s=args.timeout,
                    spend_limit_usd=args.spend_limit)
    result = run_pass(tracker if tracker is not None else GhDispatchTracker(), limits=limits)
    return 0 if result is PassResult.COMPLETED else 1


if __name__ == "__main__":
    sys.exit(main())
