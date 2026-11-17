"""Freeze: a merged task pull request becomes a worker eval case.

GitHub is read once, through the `gh` seam, for the pull request's state,
title, body, head commit and merge commit; everything else comes from the
repository's own history, so running the case later needs only the
repository (specs/worker-eval R-3).

- the task: the first `T-n` in the title or body, in the spec the body
  names (`specs/<slug>/`), else the one spec directory the pull request
  changes;
- `start`: the merge base of the head and the commit the merge landed on;
- `reference_tests`: the test files the pull request changed that, at its
  head, cite one of the task's claimed criteria.

A pull request that is not merged, names no task, or whose task is not in
`tasks.md` at its start commit is refused with the reason, and nothing is
written.
"""

from __future__ import annotations

import datetime
import json
import re
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from ...errors import EvalCaseError, UnknownTaskError
from ...proc import Runner, run_command
from ...project import DEFAULTS, ProjectConfig, path_matches
from ...worker.brief import parse_task
from .case import CaseTask, Provenance, Reference, WorkerCase, write_case

FROZEN_BY = "agent-framework-eval worker freeze"

_VIEW_FIELDS = "state,title,body,headRefOid,mergeCommit,url"
_TASK_ID_RE = re.compile(r"\bT-\d+\b")
_SPEC_DIR_RE = re.compile(r"\bspecs/([A-Za-z0-9][A-Za-z0-9._-]*)/")
_REPO_IN_URL_RE = re.compile(r"^https?://[^/]+/([^/]+/[^/]+)/pull/\d+")


def _spec_slug(body: str, changed: list[str]) -> str | None:
    named = _SPEC_DIR_RE.search(body)
    if named:
        return named.group(1)
    specs = sorted({m.group(1) for p in changed if (m := _SPEC_DIR_RE.match(p))})
    return specs[0] if len(specs) == 1 else None


def _claimed_criteria(slug: str, task_id: str, start: str, git: Runner) -> tuple[str, ...]:
    """The task's claimed criteria, read by the worker's own `parse_task`
    from `tasks.md` and `spec.md` at the start commit."""
    with tempfile.TemporaryDirectory() as tmp:
        spec_dir = Path(tmp) / slug
        spec_dir.mkdir()
        for name in ("tasks.md", "spec.md"):
            try:
                text = git(["show", f"{start}:specs/{slug}/{name}"])
            except RuntimeError:
                raise EvalCaseError(
                    f"task {task_id} is not in specs/{slug}/tasks.md at its start commit "
                    f"{start}: specs/{slug}/{name} does not exist there"
                ) from None
            (spec_dir / name).write_text(text, encoding="utf-8")
        try:
            return parse_task(slug, task_id, specs_dir=Path(tmp)).criteria
        except UnknownTaskError as e:
            message = str(e).replace(tmp, "specs")
            raise EvalCaseError(
                f"task {task_id} is not in specs/{slug}/tasks.md at its start commit "
                f"{start}: {message}"
            ) from None


def freeze_worker_case(
    pr: int,
    cases: Path,
    *,
    repo: str | None = None,
    gh: Runner = run_command,
    checkout: Path = Path("."),
    project: ProjectConfig = DEFAULTS,
    today: str | None = None,
) -> Path:
    """Write `<cases>/pr-<n>.json` for a merged task pull request; return its path.

    Raises `EvalCaseError`, having written nothing, when the pull request
    is not merged, names no task, or its task is not in `tasks.md` at its
    start commit — the message says which.
    """

    def git(args: Sequence[str]) -> str:
        return run_command(["git", "-C", str(checkout), *args])

    view_cmd = ["gh", "pr", "view", str(pr), "--json", _VIEW_FIELDS]
    if repo:
        view_cmd += ["--repo", repo]
    try:
        view = cast("dict[str, Any]", json.loads(gh(view_cmd)))
    except (RuntimeError, ValueError) as e:
        raise EvalCaseError(f"pull request #{pr} could not be read: {e}") from None

    state = view.get("state")
    merge = str((view.get("mergeCommit") or {}).get("oid") or "")
    if state != "MERGED" or not merge:
        raise EvalCaseError(
            f"pull request #{pr} is not merged ({state}); only a merged pull request "
            "is a worker eval case"
        )
    title, body = str(view.get("title") or ""), str(view.get("body") or "")
    head = str(view.get("headRefOid") or "")
    task_match = _TASK_ID_RE.search(f"{title}\n{body}")
    if task_match is None:
        raise EvalCaseError(
            f"pull request #{pr} names no task: no T-n in its title or body"
        )
    task_id = task_match.group(0)

    try:
        start = git(["merge-base", head, f"{merge}^1"]).strip()
        changed = git(["diff", "--name-only", "--diff-filter=d", start, head]).split()
    except RuntimeError as e:
        raise EvalCaseError(
            f"pull request #{pr}: its head {head} and merge {merge} cannot be read "
            f"from the repository at {checkout}: {e}"
        ) from None

    slug = _spec_slug(body, changed)
    if slug is None:
        raise EvalCaseError(
            f"pull request #{pr} names no task: {task_id} belongs to no one spec — "
            "its body names no specs/<slug>/ path and it does not change exactly one spec"
        )
    criteria = _claimed_criteria(slug, task_id, start, git)

    cites = re.compile(r"\b(?:" + "|".join(re.escape(sc) for sc in criteria) + r")\b")
    tests = [
        path for path in changed
        if path_matches(path, project.test_paths) and cites.search(git(["show", f"{head}:{path}"]))
    ]
    if not tests:
        raise EvalCaseError(
            f"pull request #{pr} changed no test file that cites {', '.join(criteria)}, "
            f"the criteria {task_id} claims"
        )

    url = _REPO_IN_URL_RE.match(str(view.get("url") or ""))
    case = WorkerCase(
        id=f"pr-{pr}",
        task=CaseTask(spec=slug, task=task_id),
        reference=Reference(
            repo=repo or (url.group(1) if url else ""), pr=pr, start=start, head=head
        ),
        reference_tests=tuple(tests),
        provenance=Provenance(
            frozen=today or datetime.date.today().isoformat(), by=FROZEN_BY
        ),
    )
    cases.mkdir(parents=True, exist_ok=True)
    return write_case(case, cases)
