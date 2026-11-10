"""Freeze: a merged pull request becomes an accepted eval case.

The bundle is collected exactly as the gate collects it — `collect_bundle`
through the `gh` seam, with the project's own config — and stored whole,
with where it came from. A pull request the human did not merge, or one the
gate would reject before any model is asked, is not a case: it is refused
and nothing is written (specs/validator-eval-set, R-3 and R-4).

Freezing a pull request again rebuilds its bundle and provenance and keeps
the expected answer, check and reason already in its file: the answer key
is a human's, changed only as its own reviewed change (R-8).
"""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from typing import Any, cast

from ..errors import EvalCaseError
from ..proc import Runner, run_command
from ..project import DEFAULTS, ProjectConfig
from ..validator.checks import run_checks
from ..validator.collector import collect_bundle
from .case import EvalCase, Provenance, dump_case, load_case

_VIEW_FIELDS = "state,mergedAt,mergedBy,headRefOid,url"
_REPO_IN_URL_RE = re.compile(r"^https?://[^/]+/([^/]+/[^/]+)/pull/\d+")


def freeze(
    pr: int,
    cases: Path,
    *,
    repo: str | None = None,
    run: Runner | None = None,
    project: ProjectConfig = DEFAULTS,
    today: str | None = None,
) -> Path:
    """Write `<cases>/pr-<n>.json` for a merged pull request; return its path.

    Raises `EvalCaseError`, having written nothing, when the pull request is
    not merged, cannot be read, or does not pass the deterministic stage —
    the message names each check that rejected it.
    """
    run = run if run is not None else run_command
    path = cases / f"pr-{pr}.json"
    kept = load_case(path) if path.exists() else None
    if kept is not None and kept.kind != "accepted":
        raise EvalCaseError(f"{path}: holds a seeded-defect case, not an accepted one")

    view_cmd = ["gh", "pr", "view", str(pr), "--json", _VIEW_FIELDS]
    if repo:
        view_cmd += ["--repo", repo]
    try:
        view = cast("dict[str, Any]", json.loads(run(view_cmd)))
        state = view.get("state")
        if state != "MERGED":
            raise EvalCaseError(
                f"pull request #{pr} is not merged ({state}); only a merged pull "
                "request is an accepted case"
            )
        bundle = collect_bundle(
            pr, repo=repo, run=run,
            ignore_checks=frozenset(project.ignore_checks),
            test_paths=project.test_paths,
        )
    except RuntimeError as e:
        raise EvalCaseError(f"pull request #{pr} could not be read: {e}") from None

    findings = run_checks(bundle, re.compile(project.test_pattern, re.MULTILINE))
    if findings:
        raise EvalCaseError(
            f"pull request #{pr} does not pass the deterministic stage — "
            + "; ".join(f"{f.check}: {f.finding} ({f.evidence})" for f in findings)
        )

    url = _REPO_IN_URL_RE.match(str(view.get("url") or ""))
    merged_by = (view.get("mergedBy") or {}).get("login")
    merged = f"Merged {str(view.get('mergedAt') or '')[:10]}".rstrip()
    case = EvalCase(
        id=path.stem,
        kind="accepted",
        expected=kept.expected if kept else "pass",
        check=kept.check if kept else None,
        reason=kept.reason if kept else (
            f"{merged}; accepted by {merged_by}." if merged_by else f"{merged}."
        ),
        provenance=Provenance(
            repo=repo or (url.group(1) if url else ""),
            pr=pr,
            head=str(view.get("headRefOid") or ""),
            frozen=today or datetime.date.today().isoformat(),
        ),
        bundle=bundle,
    )
    cases.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_case(case), encoding="utf-8")
    return path
