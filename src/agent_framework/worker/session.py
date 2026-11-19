"""The headless session seam: run `claude -p`, read the result contract.

The one place the worker invokes a coding session (ADR 0004: headless
Claude Code; auth — Max subscription or ANTHROPIC_API_KEY — is entirely
the session's own config, never this code's). Every session is launched
under the confinement profile and with an allowlisted environment
(ADR 0007, `confinement.py`); a caller supplies neither. The outcome is read from
`.worker-result.json` in the worktree, never inferred from output: the
contract binds to the worktree, not the tool.

Every session also runs under a spend limit, and its output is streamed to
a session record outside the worktree (specs/worker-spend-and-record). The
record's final entry is read for two things only: whether a failed exit was
the spend limit, and what the session reported it cost.
"""

from __future__ import annotations

import json
import math
import os
import signal
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from ..errors import SessionResultError, SessionTimeoutError, SpendLimitError, WorkerError
from .types import SessionResult

RESULT_FILE = ".worker-result.json"

# The spend limit a session gets when the dispatch names none: US dollars at
# list price, measured by Claude Code after each turn (vpc, 2026-11-15).
DEFAULT_SPEND_LIMIT_USD = 10.0
# The final entry Claude Code writes when a session reached its spend limit.
_SPEND_LIMIT_SUBTYPE = "error_max_budget_usd"
# How much of a record's end is read for its final entry.
_TAIL_BYTES = 256 * 1024

# The session seam: (argv, cwd, timeout_s, env, record) -> None. Writes the
# session's output to `record`; raises SessionTimeoutError on budget expiry.
# Injectable for tests.
SessionRunner = Callable[[Sequence[str], Path, float, Mapping[str, str], Path], None]


@dataclass(frozen=True)
class SessionEnd:
    """What a session record's final entry reports."""

    subtype: str
    cost_usd: float | None
    turns: int | None

    @property
    def spend_limit_reached(self) -> bool:
        return self.subtype == _SPEND_LIMIT_SUBTYPE


def check_spend_limit(limit_usd: float) -> float:
    """A spend limit is a finite amount of at least one cent; anything else
    is refused, so no dispatch can launch a session without a real limit."""
    if not (math.isfinite(limit_usd) and limit_usd >= 0.01):
        raise WorkerError(
            f"spend limit must be at least $0.01 a session, got {limit_usd!r}"
        )
    return limit_usd


def run_claude(
    args: Sequence[str], cwd: Path, timeout_s: float, env: Mapping[str, str], record: Path,
    *, on_start: Callable[[int], None] | None = None,
) -> None:
    """Default seam: run the CLI in the worktree, kill on budget expiry.

    The process gets exactly `env` — never this process's environment — and
    a closed standard input. Its standard output goes straight to `record`,
    so whatever it wrote is on disk even if it is killed. The session leads
    its own process group, so a budget expiry stops it and every child it
    started (test runs, shells) — none outlive it. `on_start`, when given, is
    told that group as soon as the session has started (the dispatch tick
    records it, so a later pass can stop what a dead run left).
    """
    record.parent.mkdir(parents=True, exist_ok=True)
    with record.open("w", encoding="utf-8") as out:
        try:
            proc = subprocess.Popen(
                list(args), cwd=cwd, env=dict(env), stdin=subprocess.DEVNULL,
                stdout=out, stderr=subprocess.PIPE,
                text=True, start_new_session=True,
            )
        except FileNotFoundError:
            raise SessionResultError(
                "the `claude` CLI is not installed or not on PATH — the worker "
                "needs headless Claude Code (ADR 0004)"
            ) from None
        if on_start is not None:
            try:
                on_start(proc.pid)  # the session leads its group: pgid == pid
            except BaseException:
                _kill_group(proc)  # a session nobody can account for does not run
                raise
        try:
            _, stderr = proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            _kill_group(proc)
            raise SessionTimeoutError(
                f"session exceeded its {timeout_s:.0f}s budget and was killed"
            ) from None
    if proc.returncode != 0:
        raise SessionResultError(
            f"session exited {proc.returncode}: {stderr.strip()[-500:]}"
        )


def _kill_group(proc: subprocess.Popen[str], grace_s: float = 5.0) -> None:
    """SIGTERM the session's whole process group; SIGKILL what ignores it."""
    for sig, wait_s in ((signal.SIGTERM, grace_s), (signal.SIGKILL, None)):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            pass  # the whole group is already gone
        try:
            proc.communicate(timeout=wait_s)
            return
        except subprocess.TimeoutExpired:
            continue


def stop_group(pgid: int, grace_s: float = 5.0) -> None:
    """SIGTERM a process group this process did not start, then SIGKILL
    whatever of it is left after `grace_s`. A group already gone is fine."""
    if pgid <= 1:
        return  # never "every process" or init: only a real session's group
    deadline = time.monotonic() + grace_s
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError):
            return  # gone (or no longer ours to signal)
        while sig == signal.SIGTERM and time.monotonic() < deadline:
            try:
                os.killpg(pgid, 0)
            except (ProcessLookupError, PermissionError):
                return
            time.sleep(0.05)


def read_end(record: Path) -> SessionEnd | None:
    """The record's final entry, when it is a readable `result` entry; else None."""
    try:
        with record.open("rb") as f:
            f.seek(max(0, record.stat().st_size - _TAIL_BYTES))
            tail = f.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    lines = [line for line in tail.splitlines() if line.strip()]
    if not lines:
        return None
    try:
        entry = json.loads(lines[-1])
    except json.JSONDecodeError:
        return None
    if not isinstance(entry, dict) or entry.get("type") != "result":
        return None
    cost, turns = entry.get("total_cost_usd"), entry.get("num_turns")
    return SessionEnd(
        subtype=str(entry.get("subtype", "")),
        cost_usd=float(cost) if isinstance(cost, int | float) else None,
        turns=turns if isinstance(turns, int) else None,
    )


def read_result(worktree: Path) -> SessionResult:
    """Read and validate the result contract; loud on any deviation."""
    path = worktree / RESULT_FILE
    if not path.is_file():
        raise SessionResultError(
            f"session wrote no {RESULT_FILE} — the result contract was not honored"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SessionResultError(f"{RESULT_FILE} is not valid JSON: {e}") from None
    if not isinstance(data, dict):
        raise SessionResultError(
            f"{RESULT_FILE} must be a JSON object, got {type(data).__name__}"
        )
    status = data.get("status")
    if status not in ("completed", "escalated"):
        raise SessionResultError(f"{RESULT_FILE} has invalid status: {status!r}")
    detail = data.get("detail")
    if not isinstance(detail, str) or not detail.strip():
        raise SessionResultError(f"{RESULT_FILE} must carry a non-empty detail string")
    spec_location = data.get("spec_location")
    if spec_location is not None and not isinstance(spec_location, str):
        raise SessionResultError(f"{RESULT_FILE} spec_location must be a string")
    return SessionResult(status=status, detail=detail, spec_location=spec_location)


def run_session(
    brief: str,
    worktree: Path,
    *,
    model: str,
    timeout_s: float,
    spend_limit_usd: float,
    record: Path,
    profile: Sequence[str],
    env: Mapping[str, str],
    run: SessionRunner = run_claude,
) -> SessionResult:
    """One headless session over the brief, then the result contract.

    `profile` is the confinement profile's argument list and `env` the
    allowlisted environment — both computed by `confinement.py`, required,
    and the only arguments besides the brief, the model, the spend limit and
    the record. A failed exit whose record ends at the spend limit is a
    `SpendLimitError`; any other failed exit is raised as it is. A clean
    exit is judged by `.worker-result.json` alone.
    """
    limit = check_spend_limit(spend_limit_usd)
    cmd = [
        "claude", "-p", brief, "--model", model, *profile,
        "--max-budget-usd", f"{limit:.2f}",
        # The stream, not one final result: a session killed at its time
        # budget never writes a final result, and the record must hold it.
        "--output-format", "stream-json", "--verbose",
    ]
    try:
        run(cmd, worktree, timeout_s, env, record)
    except SessionResultError:
        end = read_end(record)
        if end is not None and end.spend_limit_reached:
            raise SpendLimitError(limit, end.cost_usd) from None
        raise
    return read_result(worktree)
