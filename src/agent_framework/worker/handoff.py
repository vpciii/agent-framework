"""The handoff: a completed session becomes a PR; an escalation becomes
a durable artifact. The orchestrator never merges — the PR faces the
validator and the human (ADR 0005; the human is author of record).
"""

from __future__ import annotations

import re
from pathlib import Path

from ..errors import SessionResultError
from ..proc import Runner, run_command
from .types import SessionResult, TaskSpec
from .worktree import BASE_REF, NO_HOOKS

_TITLE_RE = re.compile(r"^### \[.\] \S+ — (.+?)\s*(?:\((?:this PR|#\d+)\))?\s*$", re.MULTILINE)


def _pr_title(task: TaskSpec) -> str:
    m = _TITLE_RE.search(task.section)
    summary = m.group(1) if m else task.spec_slug
    return f"feat: {task.task_id} {summary} ({task.spec_slug})"


def _pr_body(task: TaskSpec, result: SessionResult) -> str:
    return (
        f"Implements **{task.task_id}** from `specs/{task.spec_slug}/tasks.md` "
        "— authored by a worker agent session (ADR 0004).\n\n"
        f"Satisfies: {', '.join(task.criteria) or '—'}\n\n"
        f"Session summary: {result.detail}\n\n"
        "🤖 Worker agent PR — gated by the cite-the-test validator (ADR 0005); "
        "the human is author of record."
    )


def open_pr(
    task: TaskSpec,
    result: SessionResult,
    worktree: Path,
    branch: str,
    *,
    run: Runner = run_command,
) -> str:
    """Push the session's commits and open the declared PR; returns its URL."""
    commits = run(
        ["git", *NO_HOOKS, "-C", str(worktree), "rev-list", "--count", f"{BASE_REF}..HEAD"]
    ).strip()
    if commits == "0":
        raise SessionResultError(
            "session reported completed but committed nothing on its branch"
        )
    run(["git", *NO_HOOKS, "-C", str(worktree), "push", "-u", "origin", branch])
    url = run(
        [
            "gh", "pr", "create",
            "--head", branch,
            "--title", _pr_title(task),
            "--body", _pr_body(task, result),
        ]
    ).strip()
    return url


def write_escalation(
    task: TaskSpec, result: SessionResult, *, specs_dir: Path = Path("specs")
) -> Path:
    """Persist the worker's challenge to the contract as a durable artifact."""
    esc_dir = specs_dir / task.spec_slug / "escalations"
    esc_dir.mkdir(parents=True, exist_ok=True)
    n = 1
    while (esc_dir / f"{task.task_id.lower()}-{n}.md").exists():
        n += 1
    path = esc_dir / f"{task.task_id.lower()}-{n}.md"
    path.write_text(
        f"""# Escalation: {task.task_id} ({task.spec_slug})

- **Status:** Open
- **Task:** {task.task_id} — claimed criteria: {", ".join(task.criteria) or "—"}
- **Spec location challenged:** {result.spec_location or "(not named)"}

## Blocking question

{result.detail}

> Raised by a worker agent session. A contract change is its own diff for
> human sign-off — never folded into an implementation PR (methodology
> guardrail; design-doc escalation rules).
""",
        encoding="utf-8",
    )
    return path


HANDOFF_FILE = "HANDOFF.md"
# Notes a session may leave about its own progress, read into the handoff note.
PROGRESS_FILES = (".worker-progress", "PROGRESS.md", "claude-progress.txt")


def write_handoff_note(
    task: TaskSpec,
    worktree: Path,
    *,
    budget_s: float,
    elapsed_s: float,
    run: Runner = run_command,
    spend_limit_usd: float | None = None,
    cost_usd: float | None = None,
    record: Path | None = None,
    base: str = BASE_REF,
) -> Path:
    """After a budget expiry, record what the killed session left behind (R-6).

    Written by the orchestrator, not the session — a killed process can't.
    With `spend_limit_usd`, the session stopped at its spend limit instead
    (specs/worker-spend-and-record R-2). The note stays in the worktree and
    is never pushed, so it may name the session record. Its commit list is
    the commits since `base` — by default, the remote's main.
    """

    def git(*args: str) -> str:
        try:
            return run(["git", *NO_HOOKS, "-C", str(worktree), *args]).strip() or "(none)"
        except Exception as e:  # noqa: BLE001 — a partial note beats no note
            return f"(unavailable: {e})"

    progress = []
    for name in PROGRESS_FILES:
        f = worktree / name
        if f.is_file():
            progress.append(f"### `{name}`\n\n{f.read_text(encoding='utf-8')[:2000].strip()}")
    path = worktree / HANDOFF_FILE
    worktree.mkdir(parents=True, exist_ok=True)  # never let the note itself fail the timeout path
    if spend_limit_usd is None:
        stopped, why = "timed out", "at its budget"
        limit = ""
    else:
        stopped, why = "reached its spend limit", "at its spend limit"
        cost = "not reported" if cost_usd is None else f"${cost_usd:.2f}"
        limit = f"- **Spend limit:** ${spend_limit_usd:.2f} — **reported cost:** {cost}\n"
    session_record = f"- **Session record:** `{record}`\n" if record is not None else ""
    path.write_text(
        f"""# Handoff: {task.task_id} ({task.spec_slug}) {stopped}

- **Budget:** {budget_s:.0f}s — **elapsed:** {elapsed_s:.0f}s
{limit}- **Claimed criteria:** {", ".join(task.criteria) or "—"}
{session_record}
The session was stopped {why}; nothing was pushed and no PR was
opened. This worktree is preserved as it was left.

## Commits on the branch

```
{git("log", "--oneline", f"{base}..HEAD")}
```

## Uncommitted changes (`git status --short`)

```
{git("status", "--short")}
```

## Diff summary (`git diff --stat HEAD`)

```
{git("diff", "--stat", "HEAD")}
```

## Progress notes left by the session

{chr(10).join(progress) or "(none)"}
""",
        encoding="utf-8",
    )
    return path
