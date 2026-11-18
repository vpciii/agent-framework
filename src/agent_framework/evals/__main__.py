"""The eval's command: measure the validator's judgment on the eval set.

    agent-framework-eval run [--cases DIR] [--roster FILE] [--runs N]
                             [--only ID ...] [--pause SECONDS] [--out FILE]
    agent-framework-eval show <result> [--cases DIR]
    agent-framework-eval compare <result> <result> [--cases DIR]
    agent-framework-eval freeze <pr> [--repo OWNER/NAME] [--cases DIR]
    agent-framework-eval worker freeze <pr> [--repo OWNER/NAME] [--cases DIR]
    agent-framework-eval worker run [--cases DIR] [--roster FILE] [--runs N] [--only ID ...]
                                    [--timeout SECONDS] [--spend-limit USD] [--keep]
                                    [--out FILE]
    agent-framework-eval worker show <result>
    agent-framework-eval worker compare <result> <result>

`run` judges every case exactly as the gate does, prints the scorecard on
stdout and writes the result file; it exits 0 when the run completed,
whatever the score, and 2 when it could not start. `show` prints the
scorecard of a stored result and `compare` the cases whose class changed
between two; both class every judgment against the answers in the case set
as it is now, write nothing, and exit 2 when the cases no longer send what
the result judged (specs/eval-rescore). `freeze` writes a merged pull request into the set as an
accepted case, reading GitHub through `gh`; it exits 2, writing nothing,
for one that is not merged or that the deterministic stage rejects. `run`
is run by a human with a provider key in their shell — never by CI
(specs/validator-eval-set). `worker freeze` writes a merged task pull
request into the worker's case set; it exits 2, writing nothing, for one
that is not merged, names no task, or whose task is not in `tasks.md` at its
start commit (specs/worker-eval). `worker run` runs each case's task, one
session at a time, in a detached worktree at its start commit, launched as a
dispatch launches the worker but with nothing after the session — no push, no
pull request, no alert; it prints one line per run, then the scorecard, writes
the result file and exits 0 when the run completed, whatever the score. Like
`run`, it is run by a human — never by CI. `worker show` prints a worker result's
scorecard and every run not ready for review or failing its reference tests,
with where its files are kept; `worker compare` the cases whose class or
reference-test result changed, exiting 2 for results over different case sets.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import logging
import re
import sys
from dataclasses import replace
from pathlib import Path

from ..errors import AgentFrameworkError, EvalResultError
from ..project import load_project_config
from ..providers.anthropic import AnthropicProvider
from ..providers.google import GoogleProvider
from ..providers.registry import register_provider
from ..roster import Roster
from ..worker.session import DEFAULT_SPEND_LIMIT_USD, check_spend_limit
from .case import EvalCase, inputs_fingerprint, load_set, set_fingerprint
from .freeze import freeze
from .run import run_eval
from .scorecard import (
    JudgmentRecord,
    Result,
    compare,
    instructions_fingerprint,
    render,
    render_comparison,
    rescore,
    result_from_json,
    result_to_json,
)
from .worker import run as worker_run
from .worker import scorecard as worker_scorecard
from .worker.case import load_case_set
from .worker.freeze import freeze_worker_case

DEFAULT_CASES = Path("evals/validator/cases")
DEFAULT_WORKER_CASES = Path("evals/worker/cases")
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
        judgments=judgments, inputs=inputs_fingerprint(args.cases),
        effort=validator.effort,
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


def _against_todays_answers(
    paths: list[Path], directory: Path
) -> tuple[list[Result], tuple[EvalCase, ...]]:
    """The stored results and the case set they are to be read against.

    Raises when a result cannot be read against it: it records no inputs
    fingerprint, or the cases no longer send what it judged."""
    results = [_read(path) for path in paths]
    cases = load_set(directory)
    for path, result in zip(paths, results, strict=True):
        if result.inputs is None:
            raise EvalResultError(
                f"{path}: records no inputs fingerprint, so it cannot be shown to have "
                f"judged the cases in {directory}"
            )
    return results, cases


def _changed_since(path: Path, result: Result, directory: Path, now: str) -> str | None:
    if result.inputs == now:
        return None
    return (
        f"{path}: the cases have changed since the run (inputs {result.inputs} then, "
        f"{now} in {directory}); its judgments are of something else"
    )


def _show(args: argparse.Namespace) -> int:
    try:
        [result], cases = _against_todays_answers([args.result], args.cases)
        problem = _changed_since(
            args.result, result, args.cases, inputs_fingerprint(args.cases)
        )
        if problem:
            return _refuse(problem)
        rescored, changed = rescore(result, cases)
    except AgentFrameworkError as e:
        return _refuse(str(e))
    print(render(rescored, changed), end="")
    return 0


def _compare(args: argparse.Namespace) -> int:
    try:
        [before, after], cases = _against_todays_answers(
            [args.before, args.after], args.cases
        )
        if not compare(before, after).comparable:
            print(render_comparison(before, after), end="")
            return CANNOT_START
        problem = _changed_since(
            args.before, before, args.cases, inputs_fingerprint(args.cases)
        )
        if problem:
            return _refuse(problem)
        (was, was_changed), (now, now_changed) = rescore(before, cases), rescore(after, cases)
    except AgentFrameworkError as e:
        return _refuse(str(e))
    print(render_comparison(was, now, (was_changed, now_changed)), end="")
    return 0


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


def _worker_freeze(args: argparse.Namespace) -> int:
    try:
        written = freeze_worker_case(
            args.pr, args.cases, repo=args.repo,
            project=load_project_config(), today=_today(),
        )
    except AgentFrameworkError as e:
        return _refuse(str(e))
    print(f"wrote {written}")
    return 0


def _worker_progress(r: worker_scorecard.RunRecord) -> None:
    cost = "cost unknown" if r.cost_usd is None else f"${r.cost_usd:.2f}"
    elapsed = "" if r.elapsed_s is None else f"  {r.elapsed_s:.0f} s"
    why = f"  ({r.detail})" if r.detail else ""
    print(f"{r.case:<16} run {r.run}  {r.cls}  reference tests {r.reference_tests}  "
          f"{cost}{elapsed}{why}", file=sys.stderr)


def _worker_run(args: argparse.Namespace) -> int:
    if args.runs < 1:
        return _refuse("--runs must be at least 1")
    try:
        check_spend_limit(args.spend_limit)
        case_set = load_case_set(args.cases)
        worker = Roster.from_file(args.roster).resolve("worker")
    except AgentFrameworkError as e:
        return _refuse(str(e))
    if worker.effort is not None:
        return _refuse(f"the worker's roster binding sets effort = {worker.effort!r}, "
                       "which the worker session does not take")
    if not case_set.cases:
        return _refuse(f"no worker eval cases in {args.cases}")
    if args.only:
        unknown = sorted(set(args.only) - {c.id for c in case_set.cases})
        if unknown:
            return _refuse(f"--only names no case in {args.cases}: {', '.join(unknown)}")
        case_set = replace(case_set, cases=tuple(c for c in case_set.cases if c.id in args.only))
    date = _today()
    out: Path = args.out or (
        args.cases.parent / "results"
        / f"{date}-{re.sub(r'[^A-Za-z0-9._-]+', '-', worker.model)}.json"
    )
    if out.exists():
        # Checked before a single session: a recorded run is never replaced.
        return _refuse(f"{out} already holds a result; name another file with --out")
    result = worker_run.run_and_write(
        case_set, worker, out, date=date, claude_code=worker_run.claude_code_version(),
        runs=args.runs, timeout_s=args.timeout, spend_limit_usd=args.spend_limit,
        keep=args.keep, on_run=_worker_progress,
    )
    print(worker_scorecard.render(result), end="")
    print(f"result written to {out}", file=sys.stderr)
    return 0


def _read_worker(path: Path) -> worker_scorecard.Result:
    try:
        return worker_scorecard.result_from_json(path.read_text(encoding="utf-8"))
    except (OSError, EvalResultError) as e:
        raise EvalResultError(f"{path}: {e}") from None


def _worker_show(args: argparse.Namespace) -> int:
    try:
        result = _read_worker(args.result)
    except AgentFrameworkError as e:
        return _refuse(str(e))
    print(worker_scorecard.render(result), end="")
    return 0


def _worker_compare(args: argparse.Namespace) -> int:
    try:
        before, after = _read_worker(args.before), _read_worker(args.after)
    except AgentFrameworkError as e:
        return _refuse(str(e))
    print(worker_scorecard.render_comparison(before, after), end="")
    return 0 if worker_scorecard.comparable(before, after) else CANNOT_START


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

    show = commands.add_parser("show", help="print a stored result against today's answers")
    show.add_argument("result", type=Path)
    show.add_argument("--cases", type=Path, default=DEFAULT_CASES, metavar="DIR",
                      help="the case set whose answers the result is read against")
    show.set_defaults(handler=_show)

    cmp_ = commands.add_parser("compare", help="show which cases changed between two results")
    cmp_.add_argument("before", type=Path)
    cmp_.add_argument("after", type=Path)
    cmp_.add_argument("--cases", type=Path, default=DEFAULT_CASES, metavar="DIR",
                      help="the case set whose answers both results are read against")
    cmp_.set_defaults(handler=_compare)

    frz = commands.add_parser("freeze", help="write a merged pull request as an accepted case")
    frz.add_argument("pr", type=int, help="pull request number")
    frz.add_argument("--repo", default=None, metavar="OWNER/NAME",
                     help="the repository (default: the current one)")
    frz.add_argument("--cases", type=Path, default=DEFAULT_CASES, metavar="DIR")
    frz.set_defaults(handler=_freeze)

    worker = commands.add_parser("worker", help="measure the worker on past tasks")
    worker_commands = worker.add_subparsers(dest="worker_command", required=True)
    wfrz = worker_commands.add_parser(
        "freeze", help="write a merged task pull request as a worker eval case"
    )
    wfrz.add_argument("pr", type=int, help="pull request number")
    wfrz.add_argument("--repo", default=None, metavar="OWNER/NAME",
                      help="the repository (default: the current one)")
    wfrz.add_argument("--cases", type=Path, default=DEFAULT_WORKER_CASES, metavar="DIR")
    wfrz.set_defaults(handler=_worker_freeze)
    wrun = worker_commands.add_parser(
        "run", help="run the worker on every case and write a result"
    )
    wrun.add_argument("--cases", type=Path, default=DEFAULT_WORKER_CASES, metavar="DIR")
    wrun.add_argument("--roster", type=Path, default=Path("agent-framework.toml"),
                      metavar="FILE")
    wrun.add_argument("--runs", type=int, default=1, metavar="N",
                      help="sessions per case (default 1)")
    wrun.add_argument("--only", nargs="+", default=[], metavar="ID",
                      help="run only these cases")
    wrun.add_argument("--timeout", type=float, default=1800, metavar="SECONDS",
                      help="each session's time budget (default 1800)")
    wrun.add_argument("--spend-limit", type=float, default=DEFAULT_SPEND_LIMIT_USD,
                      metavar="USD", help="each session's spend limit (default 10)")
    wrun.add_argument("--keep", action="store_true",
                      help="keep each run's worktree instead of removing it")
    wrun.add_argument("--out", type=Path, default=None, metavar="FILE",
                      help="result file (default: results/<date>-<model>.json beside the cases)")
    wrun.set_defaults(handler=_worker_run)
    wshow = worker_commands.add_parser("show", help="print a stored worker result")
    wshow.add_argument("result", type=Path)
    wshow.set_defaults(handler=_worker_show)
    wcmp = worker_commands.add_parser(
        "compare", help="show which cases changed between two worker results"
    )
    wcmp.add_argument("before", type=Path)
    wcmp.add_argument("after", type=Path)
    wcmp.set_defaults(handler=_worker_compare)

    args = ap.parse_args(argv)
    handler = args.handler
    code: int = handler(args)
    return code


if __name__ == "__main__":
    sys.exit(main())
