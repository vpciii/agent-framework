"""The shared subprocess seam: one injectable runner, loud failures.

Both edges of the framework (the validator's collector, the worker's
worktree/session orchestration) shell out through this seam so tests fake
it with canned output and failures always carry their stderr.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence

Runner = Callable[[Sequence[str]], str]


def run_command(args: Sequence[str]) -> str:
    """Run a command; a failure raises with its stderr — fail loudly means
    the evidence rides along, not just the exit status."""
    result = subprocess.run(list(args), capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(args)}\n{result.stderr.strip()}"
        )
    return result.stdout
