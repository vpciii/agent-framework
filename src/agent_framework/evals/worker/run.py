"""Run the worker eval: for each run of each case, a worktree at its start
commit, the brief built there, one session — and nothing after it.

The session is launched through the worker's own parts (`parse_task`,
`build_brief`, `profile_args`, `session_env`, `run_session`) with the
roster's worker model, so the eval measures the worker as a dispatch runs
it (specs/worker-eval R-4). It never calls `work()`: pushing, the pull
request, the escalation file and the alerts are simply not reached (R-5).
A failure of the eval itself on a case — its start commit cannot be checked
out, its task cannot be read there, the gate cannot be set up — makes that
run `could-not-run`, and the next one still runs (R-7).

A completed session is scored by code, with no model call (R-6): each gate
command at its last commit, the handoff check since the start commit, the
reference tests on a copy of its tree, and its diff. What the session left
uncommitted is set aside first. The gate and the reference tests run with
the session's allowlisted environment, never the caller's, and each command
is stopped at the session's time budget. The patch, the logs and the session record are kept under
`.worktrees/eval/<run>/`.
"""

from __future__ import annotations

import hashlib
import os
import shlex
import shutil
import signal
import subprocess
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from ...errors import AgentFrameworkError, SessionTimeoutError, SpendLimitError, WorkerError
from ...models import ModelRef
from ...proc import Runner, run_command
from ...project import ProjectConfig
from ...worker.brief import build_brief, parse_task
from ...worker.confinement import profile_args, session_env
from ...worker.handoff_check import check_handoff
from ...worker.orchestrator import _read_roots
from ...worker.session import SessionRunner, read_end, run_claude, run_session
from ...worker.worktree import NO_HOOKS, WORKTREES_DIR, add_detached, remove_worktree
from .case import CaseSet, Settings, WorkerCase, case_set_fingerprint
from .scorecard import (
    Ending,
    GateCommand,
    Kept,
    ReferenceTests,
    Result,
    RunRecord,
    classify,
    result_to_json,
)

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


# A shell command run in a directory with an environment and a time limit
# in seconds: passed, and its output.
Shell = Callable[[str, Path, Mapping[str, str], float], tuple[bool, str]]


def run_shell(
    command: str, cwd: Path, env: Mapping[str, str], timeout_s: float,
) -> tuple[bool, str]:
    """A command that outlives `timeout_s` is stopped, with everything it
    started, and has failed: it runs the session's code, which may hang."""
    proc = subprocess.Popen(
        ["/bin/sh", "-c", command], cwd=cwd, env=dict(env), text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True,
    )
    try:
        output, _ = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)  # its own group: the shell and its children
        except ProcessLookupError:
            pass
        output, _ = proc.communicate()
        return False, f"{output}\n[timed out after {timeout_s:g} s]"
    return proc.returncode == 0, output


# What scoring leaves behind that the session's tree does not need.
_NOT_COPIED = shutil.ignore_patterns(
    ".git", ".worker-result.json", ".venv", "__pycache__",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
)


@dataclass(frozen=True)
class Score:
    gate: tuple[GateCommand, ...]
    handoff: tuple[str, ...]
    reference_tests: ReferenceTests
    diff_lines: int
    diff: Path
    gate_log: Path


def score(
    case: WorkerCase, worktree: Path, project: ProjectConfig, reference_test_command: str,
    env: Mapping[str, str], timeout_s: float, *, run: Runner = run_command,
    shell: Shell = run_shell,
) -> Score:
    """Score a completed session in `worktree`, at its last commit: what it
    left uncommitted is named in the gate log and set aside first, since a
    dispatch would not ship it. Each command gets `timeout_s`. The files are
    kept beside the worktree as `<case>-<n>.patch`, `-gate.log` and
    `-reference.log`. Raises (OSError, RuntimeError, AgentFrameworkError)
    when the scoring itself cannot be set up."""
    kept = worktree.parent

    def git(*args: str) -> str:
        return run(["git", *NO_HOOKS, "-C", str(worktree), *args])

    gate: list[GateCommand] = []
    log: list[str] = []
    uncommitted = git("status", "--porcelain", "--untracked-files=all").rstrip()
    if uncommitted:
        log.append(f"Not committed by the session, set aside before scoring:\n{uncommitted}\n")
        git("reset", "-q", "--hard", "HEAD")
        git("clean", "-q", "-fd")  # ignored files stay: the result file, caches
    for command in project.gate_commands:
        passed, output = shell(command, worktree, env, timeout_s)
        gate.append(GateCommand(command, passed))
        log.append(f"$ {command}\n{output}\n[{'passed' if passed else 'failed'}]\n")
    gate_log = kept / f"{worktree.name}-gate.log"
    gate_log.write_text("\n".join(log), encoding="utf-8")

    findings = check_handoff(worktree, project, run=run, base=case.reference.start)
    handoff = tuple(f"{f.rule}: {f.path}: {f.detail}" for f in findings)

    copy = kept / f"{worktree.name}-reference"
    shutil.rmtree(copy, ignore_errors=True)
    try:
        shutil.copytree(worktree, copy, ignore=_NOT_COPIED)
        for path in case.reference_tests:
            target = copy / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(git("show", f"{case.reference.head}:{path}"), encoding="utf-8")
        files = " ".join(shlex.quote(p) for p in case.reference_tests)
        command = reference_test_command.replace("{files}", files)
        passed, output = shell(command, copy, env, timeout_s)
    finally:
        shutil.rmtree(copy, ignore_errors=True)
    (kept / f"{worktree.name}-reference.log").write_text(
        f"$ {command}\n{output}\n[{'passed' if passed else 'failed'}]\n", encoding="utf-8"
    )

    diff = kept / f"{worktree.name}.patch"
    diff.write_text(git("diff", "--no-renames", case.reference.start, "HEAD"), encoding="utf-8")
    numstat = git("diff", "--numstat", "--no-renames", case.reference.start, "HEAD")
    size = sum(
        int(n) for line in numstat.splitlines() for n in line.split("\t")[:2] if n.isdigit()
    )
    return Score(tuple(gate), handoff, "passed" if passed else "failed", size, diff, gate_log)


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
    shell: Shell = run_shell,
) -> tuple[RunRecord, str | None]:
    """One run of one case; returns its record and the brief it was given
    (None when it could not run)."""
    worktree = EVAL_DIR / run_id / f"{case.id}-{n}"
    record = EVAL_DIR / run_id / f"{case.id}-{n}.jsonl"
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
        measured = RunRecord(
            case=case.id, run=n, cls=classify(ending, (), ()),
            cost_usd=end.cost_usd if end else None,
            turns=end.turns if end else None,
            elapsed_s=round(elapsed, 3),
            kept=Kept(record=str(record)),
            detail=detail,
        )
        if ending != "completed":
            return measured, brief
        try:
            s = score(case, worktree, settings.project, settings.reference_test_command,
                      env, timeout_s, run=run, shell=shell)
        except (OSError, RuntimeError, AgentFrameworkError) as e:
            return replace(
                measured, cls="could-not-run", detail=f"cannot score the session: {e}"
            ), brief
        return replace(
            measured, cls=classify(ending, s.gate, s.handoff),
            reference_tests=s.reference_tests, gate=s.gate, handoff=s.handoff,
            diff_lines=s.diff_lines,
            kept=Kept(record=str(record), diff=str(s.diff), gate=str(s.gate_log)),
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
    shell: Shell = run_shell,
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
                environ=environ, run=run, session_run=session_run, shell=shell,
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

