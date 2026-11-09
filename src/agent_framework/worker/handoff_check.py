"""The handoff check: what a session may not hand back, checked by code.

ADR 0007 decision 4: before the orchestrator pushes anything, the session's
commits are checked against the commit its worktree was cut from. A session
may not change the contract (a spec's text outside its Traceability table; a
tasks file beyond a checkbox), touch a protected path, or delete a test file.

Tool-independent (ADR 0007 decision 5): it reads only git, through the
runner seam, and applies to any session whatever launched it. It pushes
nothing and decides nothing — it returns findings; the orchestrator refuses
the handoff on any.
"""

from __future__ import annotations

from pathlib import Path

from ..artifacts import normalize_checkboxes, without_section
from ..proc import Runner, run_command
from ..project import ProjectConfig, path_matches
from .types import HandoffFinding
from .worktree import BASE_REF, NO_HOOKS

__all__ = ["HandoffFinding", "check_handoff"]

def _first_difference(before: str, after: str) -> str:
    """The first line that differs, for a finding a human can act on."""
    old, new = before.splitlines(), after.splitlines()
    for i in range(max(len(old), len(new))):
        a = old[i] if i < len(old) else None
        b = new[i] if i < len(new) else None
        if a != b:
            return f"first difference: {(b if b is not None else a or '').strip()[:120]!r}"
    return "differs in whitespace"


def check_handoff(
    worktree: Path,
    project: ProjectConfig,
    *,
    specs_root: str = "specs",
    run: Runner = run_command,
) -> tuple[HandoffFinding, ...]:
    """Every finding in the session's commits; empty means it may be pushed.

    `specs_root` is the specs directory relative to the repository root.
    Only commits are checked — an uncommitted edit is never pushed — and only
    those since the tree was cut (the merge base with the remote's main).
    """

    def git(*args: str) -> str:
        # Never a repository hook: the session could have written one (R-9).
        return run(["git", *NO_HOOKS, "-C", str(worktree), *args])

    base = git("merge-base", BASE_REF, "HEAD").strip()
    # --no-renames: a rename is a delete plus an add, so neither side of it
    # escapes a rule. -z: paths arrive unquoted, NUL-separated.
    fields = git("diff", "--name-status", "--no-renames", "-z", base, "HEAD").split("\0")
    changes = list(zip(fields[0::2], fields[1::2], strict=False))

    contract_files = {
        f"{specs_root}/*/spec.md": lambda text: without_section(text, "Traceability"),
        f"{specs_root}/*/tasks.md": normalize_checkboxes,
    }
    allowed = {"spec.md": "its Traceability section", "tasks.md": "a task's checkbox"}

    findings: list[HandoffFinding] = []
    for status, path in changes:
        for pattern, comparable in contract_files.items():
            if not path_matches(path, (pattern,)):
                continue
            name = path.rsplit("/", 1)[-1]
            if status != "M":
                verb = "added" if status == "A" else "removed"
                detail = f"a session may not have {verb} a {name}"
            else:
                before = comparable(git("show", f"{base}:{path}"))
                after = comparable(git("show", f"HEAD:{path}"))
                if before == after:
                    continue
                detail = (
                    f"changed outside {allowed[name]} — {_first_difference(before, after)}"
                )
            findings.append(HandoffFinding("contract", path, detail))
        if path_matches(path, project.protected_paths):
            findings.append(
                HandoffFinding("protected-path", path, "matches the project's protected_paths")
            )
        if status == "D" and path_matches(path, project.test_paths):
            findings.append(HandoffFinding("deleted-test", path, "a test file was deleted"))
    return tuple(findings)
