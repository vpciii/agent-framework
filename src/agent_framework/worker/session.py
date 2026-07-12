"""The headless session seam: run `claude -p`, read the result contract.

The one place the worker invokes a coding session (ADR 0004: headless
Claude Code; auth — Max subscription or ANTHROPIC_API_KEY — is entirely
the session's own config, never this code's). The outcome is read from
`.worker-result.json` in the worktree, never inferred from output: the
contract binds to the worktree, not the tool.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

from ..errors import SessionResultError, SessionTimeoutError
from .types import SessionResult

RESULT_FILE = ".worker-result.json"

# The session seam: (argv, cwd, timeout_s) -> None. Raises
# SessionTimeoutError on budget expiry. Injectable for tests.
SessionRunner = Callable[[Sequence[str], Path, float], None]


def run_claude(args: Sequence[str], cwd: Path, timeout_s: float) -> None:
    """Default seam: run the CLI in the worktree, kill on budget expiry."""
    try:
        result = subprocess.run(
            list(args), cwd=cwd, capture_output=True, text=True, timeout=timeout_s
        )
    except FileNotFoundError:
        raise SessionResultError(
            "the `claude` CLI is not installed or not on PATH — the worker "
            "needs headless Claude Code (ADR 0004)"
        ) from None
    except subprocess.TimeoutExpired:
        raise SessionTimeoutError(
            f"session exceeded its {timeout_s:.0f}s budget and was killed"
        ) from None
    if result.returncode != 0:
        raise SessionResultError(
            f"session exited {result.returncode}: {result.stderr.strip()[-500:]}"
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
    session_args: Sequence[str] = (),
    run: SessionRunner = run_claude,
) -> SessionResult:
    """One headless session over the brief, then the result contract."""
    cmd = ["claude", "-p", brief, "--model", model, *session_args]
    run(cmd, worktree, timeout_s)
    return read_result(worktree)
