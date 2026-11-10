"""The eval's command: measure the validator's judgment on the eval set.

    agent-framework-eval run [--cases DIR] [--roster FILE] [--runs N]
                             [--only ID ...] [--pause SECONDS] [--out FILE]
    agent-framework-eval compare <result> <result>
    agent-framework-eval freeze <pr> [--repo OWNER/NAME] [--cases DIR]

`run` judges every case exactly as the gate does, prints the scorecard on
stdout and writes the result file; it exits 0 when the run completed,
whatever the score, and 2 when it could not start. `compare` prints the
cases whose class changed between two results, and exits 2 when their case
sets differ. `freeze` writes a merged pull request into the set as an
accepted case, reading GitHub through `gh`; it exits 2, writing nothing,
for one that is not merged or that the deterministic stage rejects. `run`
is run by a human with a provider key in their shell — never by CI
(specs/validator-eval-set).
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import logging
import re
import sys
from pathlib import Path

from ..errors import AgentFrameworkError, EvalResultError
from ..project import load_project_config
from ..providers.anthropic import AnthropicProvider
from ..providers.google import GoogleProvider
from ..providers.registry import register_provider
from ..roster import Roster
from .case import load_set, set_fingerprint
from .freeze import freeze
from .run import run_eval
from .scorecard import (
    JudgmentRecord,
    Result,
    compare,
    instructions_fingerprint,
    render,
    render_comparison,
    result_from_json,
    result_to_json,
)

DEFAULT_CASES = Path("evals/validator/cases")
CANNOT_START = 2


def _today() -> str:
    return datetime.date.today().isoformat()


def _refuse(message: str) -> int:
    print(f"agent-framework-eval: {message}", file=sys.stderr)
    return CANNOT_START


def _progress(item: JudgmentRecord) -> None:
    why = f" ({item.reason})" if item.reason else ""
    tokens = (
        f"in={item.input_tokens} out={item.output_tokens}"
        if item.input_tokens is not None else "no usage reported"
    )
    print(f"{item.case:<32} run {item.run}  {item.cls}{why}  {tokens}", file=sys.stderr)


def _run(args: argparse.Namespace) -> int:
    if args.runs < 1:
        return _refuse("--runs must be at least 1")
    try:
        cases = load_set(args.cases)
        roster = Roster.from_file(args.roster)
        validator = roster.resolve("validator")
    except AgentFrameworkError as e:
        return _refuse(str(e))
    if not cases:
        return _refuse(f"no eval cases in {args.cases}")
    if args.only:
        unknown = sorted(set(args.only) - {c.id for c in cases})
        if unknown:
            return _refuse(f"--only names no case in {args.cases}: {', '.join(unknown)}")
        cases = tuple(c for c in cases if c.id in args.only)

    date = _today()
    out: Path = args.out or (
        args.cases.parent / "results"
        / f"{date}-{re.sub(r'[^A-Za-z0-9._-]+', '-', validator.model)}.json"
    )
    if out.exists():
        # Checked before a single model call: a recorded run is never replaced.
        return _refuse(f"{out} already holds a result; name another file with --out")

    register_provider("anthropic", AnthropicProvider())
    register_provider("google", GoogleProvider())

    # Show the gate's own log lines (model, stop reason, each dropped
    # finding) and one line per judgment on stderr; stdout is the scorecard.
    log = logging.getLogger("agent_framework")
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    previous_level = log.level
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    try:
        judgments = asyncio.run(
            run_eval(cases, roster, runs=args.runs, pause=args.pause, on_judgment=_progress)
        )
    except AgentFrameworkError as e:
        return _refuse(str(e))
    finally:
        log.removeHandler(handler)
        log.setLevel(previous_level)

    result = Result(
        model=f"{validator.provider}:{validator.model}", date=date, runs=args.runs,
        instructions=instructions_fingerprint(), case_set=set_fingerprint(args.cases),
        judgments=judgments,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result_to_json(result), encoding="utf-8")
    print(render(result), end="")
    print(f"result written to {out}", file=sys.stderr)
    return 0


def _read(path: Path) -> Result:
    try:
        return result_from_json(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise EvalResultError(f"{path}: {e}") from None
    except EvalResultError as e:
        raise EvalResultError(f"{path}: {e}") from None


def _compare(args: argparse.Namespace) -> int:
    try:
        before, after = _read(args.before), _read(args.after)
    except EvalResultError as e:
        return _refuse(str(e))
    print(render_comparison(before, after), end="")
    return 0 if compare(before, after).comparable else CANNOT_START


def _freeze(args: argparse.Namespace) -> int:
    try:
        written = freeze(
            args.pr, args.cases, repo=args.repo,
            project=load_project_config(), today=_today(),
        )
    except AgentFrameworkError as e:
        return _refuse(str(e))
    print(f"wrote {written}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="agent-framework-eval",
        description="Measure the validator's judgment on the eval set",
    )
    commands = ap.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="judge every case and write a result")
    run.add_argument("--cases", type=Path, default=DEFAULT_CASES, metavar="DIR")
    run.add_argument("--roster", type=Path, default=Path("agent-framework.toml"), metavar="FILE")
    run.add_argument("--runs", type=int, default=1, metavar="N",
                     help="judgments per case (default 1)")
    run.add_argument("--only", nargs="+", default=[], metavar="ID",
                     help="judge only these cases")
    run.add_argument("--pause", type=float, default=0.0, metavar="SECONDS",
                     help="wait between judgments, to stay under a rate limit")
    run.add_argument("--out", type=Path, default=None, metavar="FILE",
                     help="result file (default: results/<date>-<model>.json beside the cases)")
    run.set_defaults(handler=_run)

    cmp_ = commands.add_parser("compare", help="show which cases changed between two results")
    cmp_.add_argument("before", type=Path)
    cmp_.add_argument("after", type=Path)
    cmp_.set_defaults(handler=_compare)

    frz = commands.add_parser("freeze", help="write a merged pull request as an accepted case")
    frz.add_argument("pr", type=int, help="pull request number")
    frz.add_argument("--repo", default=None, metavar="OWNER/NAME",
                     help="the repository (default: the current one)")
    frz.add_argument("--cases", type=Path, default=DEFAULT_CASES, metavar="DIR")
    frz.set_defaults(handler=_freeze)

    args = ap.parse_args(argv)
    handler = args.handler
    code: int = handler(args)
    return code


if __name__ == "__main__":
    sys.exit(main())
