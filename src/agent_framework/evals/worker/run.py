"""Run the worker eval: for each run of each case, a worktree at its start
commit, the brief built there, one session — and nothing after it.

The session is launched through the worker's own parts (`parse_task`,
`build_brief`, `profile_args`, `session_env`, `run_session`) with the
roster's worker model, so the eval measures the worker as a dispatch runs
it (specs/worker-eval R-4). It never calls `work()`: pushing, the pull
request, the escalation file and the alerts are simply not reached (R-5).
A failure of the eval itself on a case — its start commit cannot be checked
out, its task cannot be read there — makes that run `could-not-run`, and
the next one still runs (R-7). Scoring a completed session is T-6's.
"""

from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Callable, Mapping
from pathlib import Path

from ...errors import AgentFrameworkError, SessionTimeoutError, SpendLimitError, WorkerError
from ...models import ModelRef
from ...proc import Runner, run_command
from ...worker.brief import build_brief, parse_task
from ...worker.confinement import profile_args, session_env
from ...worker.orchestrator import RECORDS_DIR, _read_roots
from ...worker.session import SessionRunner, read_end, run_claude, run_session
from ...worker.worktree import WORKTREES_DIR, add_detached, remove_worktree
from .case import CaseSet, Settings, WorkerCase, case_set_fingerprint
from .scorecard import Ending, Kept, Result, RunRecord, classify, result_to_json

EVAL_DIR = WORKTREES_DIR / "eval"


def new_run_id(date: str) -> str:
    """`<date>-<k>`, the first k whose `.worktrees/eval/<run>/` is not taken."""
    k = 1
    while (EVAL_DIR / f"{date}-{k}").exists():
        k += 1
    return f"{date}-{k}"


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def _could_not_run(case: WorkerCase, n: int, detail: str) -> RunRecord:
    return RunRecord(case=case.id, run=n, cls="could-not-run", detail=detail)


def run_case(
    case: WorkerCase,
    n: int,
    run_id: str,
    settings: Settings,
    worker: ModelRef,
    *,
    timeout_s: float,
    spend_limit_usd: float,
    keep: bool = False,
    environ: Mapping[str, str] = os.environ,
    run: Runner = run_command,
    session_run: SessionRunner = run_claude,
) -> tuple[RunRecord, str | None]:
    """One run of one case; returns its record and the brief it was given
    (None when it could not run)."""
    worktree = EVAL_DIR / run_id / f"{case.id}-{n}"
    record = RECORDS_DIR / f"eval-{run_id}-{case.id}-{n}.jsonl"
    try:
        worktree.parent.mkdir(parents=True, exist_ok=True)
        add_detached(worktree, case.reference.start, run=run)
    except (RuntimeError, AgentFrameworkError) as e:
        return _could_not_run(case, n, f"cannot check out {case.reference.start}: {e}"), None
    try:
        try:
            task = parse_task(case.task.spec, case.task.task, specs_dir=worktree / "specs")
        except AgentFrameworkError as e:
            return _could_not_run(case, n, f"cannot build the brief: {e}"), None
        brief = build_brief(task, settings.project)
        profile = profile_args(settings.project, _read_roots(run))
        env = session_env(settings.project, environ)
        detail = ""
        started = time.monotonic()
        ending: Ending
        try:
            result = run_session(
                brief, worktree, model=worker.model, timeout_s=timeout_s,
                spend_limit_usd=spend_limit_usd, record=record, profile=profile,
                env=env, run=session_run,
            )
            ending, detail = result.status, result.detail
        except SpendLimitError as e:
            ending, detail = "spend-limit", str(e)
        except SessionTimeoutError as e:
            ending, detail = "timed-out", str(e)
        except WorkerError as e:
            ending, detail = "error", str(e)
        elapsed = time.monotonic() - started
        end = read_end(record)
        return RunRecord(
            case=case.id, run=n,
            # A completed session's gate, handoff check, reference tests and
            # diff are scored by T-6; until then they are unset.
            cls=classify(ending, (), ()),
            cost_usd=end.cost_usd if end else None,
            turns=end.turns if end else None,
            elapsed_s=round(elapsed, 3),
            kept=Kept(record=str(record)),
            detail=detail,
        ), brief
    finally:
        if not keep:
            remove_worktree(worktree, run=run)


def run_eval(
    case_set: CaseSet,
    worker: ModelRef,
    run_id: str,
    *,
    runs: int,
    timeout_s: float,
    spend_limit_usd: float,
    keep: bool = False,
    environ: Mapping[str, str] = os.environ,
    run: Runner = run_command,
    session_run: SessionRunner = run_claude,
    on_run: Callable[[RunRecord], None] = lambda r: None,
) -> tuple[tuple[RunRecord, ...], dict[str, str]]:
    """Every run of every case, one at a time; the records and, per case,
    the fingerprint of the brief it was given."""
    records: list[RunRecord] = []
    briefs: dict[str, str] = {}
    for case in case_set.cases:
        for n in range(1, runs + 1):
            record, brief = run_case(
                case, n, run_id, case_set.settings, worker,
                timeout_s=timeout_s, spend_limit_usd=spend_limit_usd, keep=keep,
                environ=environ, run=run, session_run=session_run,
            )
            if brief is not None:
                briefs[case.id] = fingerprint(brief)
            records.append(record)
            on_run(record)
    return tuple(records), briefs


def run_and_write(
    case_set: CaseSet,
    worker: ModelRef,
    out: Path,
    *,
    date: str,
    claude_code: str,
    runs: int,
    timeout_s: float,
    spend_limit_usd: float,
    keep: bool = False,
    environ: Mapping[str, str] = os.environ,
    run: Runner = run_command,
    session_run: SessionRunner = run_claude,
    on_run: Callable[[RunRecord], None] = lambda r: None,
) -> Result:
    """Run the eval and write its result file at `out`."""
    records, briefs = run_eval(
        case_set, worker, new_run_id(date), runs=runs, timeout_s=timeout_s,
        spend_limit_usd=spend_limit_usd, keep=keep, environ=environ, run=run,
        session_run=session_run, on_run=on_run,
    )
    result = Result(
        model=f"{worker.provider}:{worker.model}", claude_code=claude_code, date=date,
        runs=runs, time_budget_s=int(timeout_s), spend_limit_usd=spend_limit_usd,
        case_set=case_set_fingerprint(case_set), briefs=briefs, results=records,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result_to_json(result), encoding="utf-8")
    return result


def claude_code_version(run: Runner = run_command) -> str:
    """What `claude --version` reports, or "unknown"."""
    try:
        return run(["claude", "--version"]).strip() or "unknown"
    except (RuntimeError, OSError):
        return "unknown"
