"""Dispatch one task to a worker session from the command line.

    python -m agent_framework.worker <spec-slug> <task-id>
        [--timeout SECONDS] [--roster PATH] [--session-arg ARG ...]

Prints the outcome JSON on stdout. Exit codes compose with the validator's
(0/1) for a future chief: 0 = PR opened, 2 = escalated, 3 = timeout or
worker error.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections.abc import Callable
from pathlib import Path

from ..errors import WorkerError
from ..project import load_project_config
from ..roster import Roster
from .orchestrator import work
from .types import Escalated, PrOpened, WorkerOutcome

WorkFn = Callable[..., WorkerOutcome]


def _outcome_json(outcome: WorkerOutcome) -> str:
    kind = {PrOpened: "pr_opened", Escalated: "escalated"}.get(type(outcome), "timed_out")
    return json.dumps({"outcome": kind, **dataclasses.asdict(outcome)}, indent=2)


def main(argv: list[str] | None = None, *, work_fn: WorkFn = work) -> int:
    ap = argparse.ArgumentParser(description="Dispatch one task to a worker session")
    ap.add_argument("spec_slug", help="spec folder under specs/")
    ap.add_argument("task_id", help="task id from that spec's tasks.md (e.g. T-2)")
    ap.add_argument("--timeout", type=float, default=1800, metavar="SECONDS")
    ap.add_argument("--roster", type=Path, default=Path("agent-framework.toml"))
    ap.add_argument(
        "--session-arg",
        action="append",
        default=[],
        metavar="ARG",
        help="extra argument passed to the claude session (repeatable)",
    )
    args = ap.parse_args(argv)

    roster = Roster.from_file(args.roster)
    project = load_project_config()
    try:
        outcome = work_fn(
            args.spec_slug,
            args.task_id,
            roster,
            timeout_s=args.timeout,
            session_args=tuple(args.session_arg),
            project=project,
        )
    except WorkerError as e:
        print(json.dumps({"outcome": "error", "detail": str(e)}, indent=2))
        return 3

    print(_outcome_json(outcome))
    if isinstance(outcome, PrOpened):
        return 0
    if isinstance(outcome, Escalated):
        return 2
    return 3


if __name__ == "__main__":
    sys.exit(main())
