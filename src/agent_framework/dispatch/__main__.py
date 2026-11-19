"""The dispatch tick: one pass over the open `dispatch` issues, then exit.

    agent-framework-dispatch [--roster FILE] [--timeout SECONDS] [--spend-limit USD]
    python -m agent_framework.dispatch ...

Exit 0 when the pass completed (whatever it found), 1 when it failed, 2 when
it refused its checkout. The limits default to the worker's own. Run from the
checkout's root. When the pass moved the checkout, the command starts itself
again once — the lock released first — so the pass runs the code it fetched.
A completed pass sends a heartbeat to `AF_HA_HEARTBEAT_URL`, when it is set;
whether it arrives changes neither the outcome nor the exit status.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

from ..alerts import IssueTracker
from ..worker.session import DEFAULT_SPEND_LIMIT_USD
from .report import send_heartbeat
from .tick import DispatchTracker, GhDispatchTracker, Limits, PassResult, run_pass

# Set in the environment of the command started again: it never starts again.
RESTARTED_ENV = "AF_DISPATCH_RESTARTED"

_EXIT = {PassResult.COMPLETED: 0, PassResult.FAILED: 1, PassResult.REFUSED: 2}


def _restart(argv: list[str]) -> int:
    """Replace this process with the command again, marked as restarted."""
    os.execve(sys.executable, [sys.executable, "-m", "agent_framework.dispatch", *argv],
              {**os.environ, RESTARTED_ENV: "1"})
    return 1  # pragma: no cover — execve does not return


def main(
    argv: list[str] | None = None,
    *,
    tracker: DispatchTracker | None = None,
    alert_tracker: IssueTracker | None = None,
    environ: Mapping[str, str] = os.environ,
    restart: Callable[[list[str]], int] = _restart,
) -> int:
    argv = sys.argv[1:] if argv is None else argv
    ap = argparse.ArgumentParser(description="Make one dispatch pass and exit")
    ap.add_argument("--roster", type=Path, default=Path("agent-framework.toml"))
    ap.add_argument("--timeout", type=float, default=1800, metavar="SECONDS")
    ap.add_argument("--spend-limit", type=float, default=DEFAULT_SPEND_LIMIT_USD,
                    metavar="USD", help="a run's spend limit, at list price")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    limits = Limits(roster=args.roster, timeout_s=args.timeout,
                    spend_limit_usd=args.spend_limit)
    result = run_pass(tracker if tracker is not None else GhDispatchTracker(), limits=limits,
                      alert_tracker=alert_tracker, heartbeat=lambda: send_heartbeat(environ),
                      restarted=bool(environ.get(RESTARTED_ENV)))
    if result is PassResult.RESTART:  # the lock was released when run_pass returned
        return restart(argv)
    return _EXIT[result]


if __name__ == "__main__":
    sys.exit(main())
