"""The collector edge: assemble an EvidenceBundle from a real PR.

The only place the validator touches the world. All `gh` access goes
through one injectable runner seam so tests fake it with canned output —
the core (checks, judgment, gate) stays hermetic.

Conventions the collector reads from a PR (the worker/task contract):
- task id: the first `T-n` in the PR title or body (else `PR-<number>`);
- claimed criteria: the **Satisfies declaration** (`Satisfies: SC-…`, first
  matching body line) exclusively when present — prose mentions of `SC-`
  ids are not claims; only when no declaration exists does the collector
  fall back to scraping every distinct `SC-n` from the title + body;
- the spec the claims belong to: the first `specs/<slug>/` path in the body,
  else the one spec directory among the changed files; its criterion texts
  and the task's block are read at the PR's base commit (head if new);
- citations: the spec's Traceability table at the PR's head names each
  claimed criterion's tests (`path::test_name`);
- test files: the changed files matching the project's `test_paths` (a
  file the PR deletes has no content at its head and is left out), plus
  every file the table names for a claimed criterion;
- fix: a Conventional-Commits `fix` type in the title;
- red evidence (fixes): the body paragraph describing the failing-before
  run (contains both "fail" and "before").
"""

from __future__ import annotations

import json
import re
from typing import Any, cast

from ..artifacts import criterion_text, task_block, traceability
from ..proc import Runner, run_command
from ..project import DEFAULTS, path_matches
from .bundle import CIEvidence, Contract, Description, EvidenceBundle, TaskRef

__all__ = ["DESCRIPTION_LIMIT", "Runner", "collect_bundle", "run_command"]

# The most of a PR's description the judgment is shown, in characters
# (specs/pr-description-in-judgment R-1). GitHub allows 65,536.
DESCRIPTION_LIMIT = 20_000

_TASK_ID_RE = re.compile(r"\bT-\d+\b")
_SC_RE = re.compile(r"\bSC-\d+\b")
_SATISFIES_RE = re.compile(r"^Satisfies:(.*)$", re.MULTILINE)
_FIX_TITLE_RE = re.compile(r"^fix[(!:]")
_SPEC_DIR_RE = re.compile(r"\bspecs/([A-Za-z0-9][A-Za-z0-9._-]*)/")


def _pr_view(pr: int, repo: str | None, run: Runner) -> dict[str, Any]:
    cmd = [
        "gh", "pr", "view", str(pr),
        "--json", "number,title,body,baseRefOid,headRefOid,files,statusCheckRollup",
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


# Conclusions that must not block: a conditional job that didn't run is
# absent evidence, not failing evidence (e.g. an advisory reviewer job).
_NON_BLOCKING_CONCLUSIONS = frozenset({"SKIPPED", "NEUTRAL"})


def _ci_evidence(
    rollup: list[dict[str, Any]], ignore_checks: frozenset[str] = frozenset()
) -> CIEvidence:
    rollup = [c for c in rollup if c.get("name") not in ignore_checks]
    if not rollup:
        return CIEvidence(green=False, summary="no status checks reported")
    lines = [
        f"{c.get('name', '?')}: {c.get('conclusion') or c.get('status', '?')}"
        for c in rollup
    ]
    conclusions = [c.get("conclusion") for c in rollup]
    green = any(x == "SUCCESS" for x in conclusions) and all(
        x == "SUCCESS" or x in _NON_BLOCKING_CONCLUSIONS for x in conclusions
    )
    return CIEvidence(green=green, summary="; ".join(lines))


def _red_evidence(body: str, is_fix: bool) -> str | None:
    if not is_fix:
        return None
    for paragraph in body.split("\n\n"):
        low = paragraph.lower()
        if "fail" in low and "before" in low:
            return paragraph.strip()
    return None


def _resolve_slug(body: str, paths: list[str]) -> tuple[str | None, str]:
    """The spec a PR's claims belong to (validator-evidence R-1), or why not."""
    named = _SPEC_DIR_RE.search(body)
    if named:
        return named.group(1), ""
    changed = sorted({m.group(1) for p in paths if (m := _SPEC_DIR_RE.match(p))})
    if len(changed) == 1:
        return changed[0], ""
    if changed:
        return None, (
            "the PR body names no specs/<slug>/ path and the PR changes more than "
            f"one spec: {', '.join(changed)}"
        )
    return None, "the PR body names no specs/<slug>/ path and the PR changes no spec"


def _contract(
    task: TaskRef, body: str, paths: list[str], base: str, head: str,
    repo: str | None, run: Runner,
) -> Contract:
    """Read the claimed criteria's text and the task block from the artifacts."""
    slug, problem = _resolve_slug(body, paths)
    if slug is None:
        return Contract(spec_slug=None, problem=problem)

    def read(name: str) -> tuple[str, str] | None:
        # The contract as it stood before the PR; the head only when the PR
        # itself introduces the file (R-2).
        for where, ref in (("base", base), ("head", head)):
            try:
                return _file_at_ref(f"specs/{slug}/{name}", ref, repo, run), where
            except RuntimeError:
                continue
        return None

    spec = read("spec.md")
    if spec is None:
        return Contract(
            spec_slug=None,
            problem=f"specs/{slug}/spec.md not found at the PR's base or head commit",
        )
    spec_text, where = spec
    texts = {
        sc: text for sc in task.criteria if (text := criterion_text(spec_text, sc)) is not None
    }
    tasks = read("tasks.md") if _TASK_ID_RE.fullmatch(task.task_id) else None
    # Citations come from the Traceability table as the PR leaves it (its
    # head): the table is the one part of a spec a task PR is meant to change.
    if where == "head":
        table = traceability(spec_text)
    else:
        try:
            table = traceability(_file_at_ref(f"specs/{slug}/spec.md", head, repo, run))
        except RuntimeError:
            table = {}  # the PR removed the spec: nothing is cited
    return Contract(
        spec_slug=slug,
        criterion_texts=texts,
        task_block=task_block(tasks[0], task.task_id) if tasks else None,
        cited_tests={sc: table[sc] for sc in task.criteria if sc in table},
        read_from="base" if where == "base" else "head",
        ref=base if where == "base" else head,
    )


def collect_bundle(
    pr: int,
    *,
    repo: str | None = None,
    run: Runner = run_command,
    ignore_checks: frozenset[str] = frozenset(),
    test_paths: tuple[str, ...] = DEFAULTS.test_paths,
) -> EvidenceBundle:
    """Assemble the evidence bundle for one PR via `gh` (diff, metadata, files).

    `ignore_checks` names status checks excluded from the CI evidence — for
    the in-CI advisory run, which must not count its own (necessarily
    in-progress) check as red CI. `test_paths` is the project's declaration
    of which changed files are tests (validator-evidence R-6).
    """
    view = _pr_view(pr, repo, run)
    title = str(view.get("title", ""))
    body = str(view.get("body", ""))
    text = f"{title}\n{body}"

    task_match = _TASK_ID_RE.search(text)
    task_id = task_match.group(0) if task_match else f"PR-{pr}"
    declaration = _SATISFIES_RE.search(body)
    claim_source = declaration.group(1) if declaration else text
    criteria = tuple(
        sorted(set(_SC_RE.findall(claim_source)), key=lambda s: int(s[3:]))
    )
    is_fix = _FIX_TITLE_RE.match(title) is not None

    diff_cmd = ["gh", "pr", "diff", str(pr)]
    if repo:
        diff_cmd += ["--repo", repo]
    diff = run(diff_cmd)

    head = str(view.get("headRefOid", ""))
    files = cast("list[dict[str, Any]]", view.get("files") or [])
    changed = [str(f.get("path", "")) for f in files]

    task = TaskRef(task_id=task_id, criteria=criteria, is_fix=is_fix)
    # A PR that claims nothing is rejected before any contract matters.
    contract = (
        _contract(task, body, changed, str(view.get("baseRefOid", "")), head, repo, run)
        if criteria
        else Contract(spec_slug=None, problem="the PR claims no success criteria")
    )

    # A file the PR deletes is among its changed files but does not exist at
    # the head: it is absent from the tests, not fetched. `gh` marks it, so
    # any other failure to read a changed test file still raises.
    deleted = {str(f.get("path", "")) for f in files if f.get("changeType") == "DELETED"}
    tests: dict[str, str] = {}
    for path in changed:
        if path_matches(path, test_paths) and path not in deleted:
            tests[path] = _file_at_ref(path, head, repo, run)
    # A test file the Traceability table names is evidence whether or not the
    # PR changed it. One that cannot be read is simply absent — the
    # deterministic stage reports it against the criterion.
    for refs in contract.cited_tests.values():
        for ref in refs:
            path = ref.split("::")[0].strip()
            if path and path not in tests:
                try:
                    tests[path] = _file_at_ref(path, head, repo, run)
                except RuntimeError:
                    continue

    rollup = cast("list[dict[str, Any]]", view.get("statusCheckRollup") or [])
    return EvidenceBundle(
        task=task,
        diff=diff,
        tests=tests,
        ci=_ci_evidence(rollup, ignore_checks),
        red_evidence=_red_evidence(body, is_fix),
        contract=contract,
        description=Description(
            title=title,
            text=body[:DESCRIPTION_LIMIT],
            cut=len(body) > DESCRIPTION_LIMIT,
        ),
    )
