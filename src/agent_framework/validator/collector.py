"""The collector edge: assemble an EvidenceBundle from a real PR.

The only place the validator touches the world. All `gh` access goes
through one injectable runner seam so tests fake it with canned output —
the core (checks, judgment, gate) stays hermetic.

Conventions the collector reads from a PR (the worker/task contract):
- task id: the first `T-n` in the PR title or body (else `PR-<number>`);
- claimed criteria: every distinct `SC-n` in the title + body;
- fix: a Conventional-Commits `fix` type in the title;
- red evidence (fixes): the body paragraph describing the failing-before
  run (contains both "fail" and "before").
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable, Sequence
from typing import Any, cast

from .bundle import CIEvidence, EvidenceBundle, TaskRef

Runner = Callable[[Sequence[str]], str]

_TASK_ID_RE = re.compile(r"\bT-\d+\b")
_SC_RE = re.compile(r"\bSC-\d+\b")
_FIX_TITLE_RE = re.compile(r"^fix[(!:]")


def run_command(args: Sequence[str]) -> str:
    """The single subprocess seam. A failing command raises with its stderr —
    fail loudly means the evidence rides along, not just the exit status."""
    result = subprocess.run(list(args), capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(args)}\n{result.stderr.strip()}"
        )
    return result.stdout


def _pr_view(pr: int, repo: str | None, run: Runner) -> dict[str, Any]:
    cmd = [
        "gh", "pr", "view", str(pr),
        "--json", "number,title,body,headRefOid,files,statusCheckRollup",
    ]
    if repo:
        cmd += ["--repo", repo]
    return cast("dict[str, Any]", json.loads(run(cmd)))


def _file_at_ref(path: str, ref: str, repo: str | None, run: Runner) -> str:
    target = (
        f"repos/{repo}/contents/{path}" if repo
        else f"repos/{{owner}}/{{repo}}/contents/{path}"
    )
    return run(
        ["gh", "api", "-H", "Accept: application/vnd.github.raw", f"{target}?ref={ref}"]
    )


def _ci_evidence(rollup: list[dict[str, Any]]) -> CIEvidence:
    if not rollup:
        return CIEvidence(green=False, summary="no status checks reported")
    lines = [
        f"{c.get('name', '?')}: {c.get('conclusion') or c.get('status', '?')}"
        for c in rollup
    ]
    green = all(c.get("conclusion") == "SUCCESS" for c in rollup)
    return CIEvidence(green=green, summary="; ".join(lines))


def _red_evidence(body: str, is_fix: bool) -> str | None:
    if not is_fix:
        return None
    for paragraph in body.split("\n\n"):
        low = paragraph.lower()
        if "fail" in low and "before" in low:
            return paragraph.strip()
    return None


def collect_bundle(
    pr: int, *, repo: str | None = None, run: Runner = run_command
) -> EvidenceBundle:
    """Assemble the evidence bundle for one PR via `gh` (diff, metadata, files)."""
    view = _pr_view(pr, repo, run)
    title = str(view.get("title", ""))
    body = str(view.get("body", ""))
    text = f"{title}\n{body}"

    task_match = _TASK_ID_RE.search(text)
    task_id = task_match.group(0) if task_match else f"PR-{pr}"
    criteria = tuple(sorted(set(_SC_RE.findall(text)), key=lambda s: int(s[3:])))
    is_fix = _FIX_TITLE_RE.match(title) is not None

    diff_cmd = ["gh", "pr", "diff", str(pr)]
    if repo:
        diff_cmd += ["--repo", repo]
    diff = run(diff_cmd)

    head = str(view.get("headRefOid", ""))
    files = cast("list[dict[str, Any]]", view.get("files") or [])
    tests: dict[str, str] = {}
    for f in files:
        path = str(f.get("path", ""))
        if path.startswith("tests/") and path.endswith(".py"):
            tests[path] = _file_at_ref(path, head, repo, run)

    rollup = cast("list[dict[str, Any]]", view.get("statusCheckRollup") or [])
    return EvidenceBundle(
        task=TaskRef(task_id=task_id, criteria=criteria, is_fix=is_fix),
        diff=diff,
        tests=tests,
        ci=_ci_evidence(rollup),
        red_evidence=_red_evidence(body, is_fix),
    )
