"""Brief assembly: the self-contained document a worker session executes from.

Pure — its only inputs are the two artifact files (`tasks.md`, `spec.md`),
by construction: a worker reads its brief, never the chief's (or anyone's)
conversation context. Everything else in the brief is fixed convention text.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..artifacts import criterion_text, section, task_block
from ..errors import UnknownTaskError
from ..project import DEFAULTS, ProjectConfig
from .types import TaskSpec

_SC_RE = re.compile(r"\bSC-\d+\b")

_RESULT_CONTRACT = """\
RESULT CONTRACT (mandatory): before you finish, write `.worker-result.json`
in the repository root of your working tree:
  {"status": "completed", "detail": "<one-line summary>"}
or, if you are escalating (see ESCALATION below):
  {"status": "escalated", "detail": "<the blocking question>",
   "spec_location": "<file and section you are challenging>"}
A missing or malformed file means your work cannot be accepted."""

_ESCALATION = """\
ESCALATION: if you believe the spec or task is wrong, contradictory, or
underspecified, STOP. Do not code around it, do not reword criteria, do not
edit spec/tasks files. Report status "escalated" with the blocking question
and the spec location — a contract change is a human decision."""


def _limits(project: ProjectConfig) -> str:
    """What the session cannot do (ADR 0007) — stated so it escalates
    instead of spending its budget on commands that will be refused."""
    hosts = ", ".join(project.session_network) or "no network host"
    writable = "".join(f" (or {p})" for p in project.session_write_paths)
    protected = ", ".join(project.protected_paths) or "(none)"
    return f"""\
LIMITS (enforced by a sandbox and by a check on your commits — not requests):
- You cannot push, open a PR, or merge.
- Your commands cannot write outside this worktree{writable}.
- Your commands cannot read the rest of the home directory.
- Your commands can reach only: {hosts}.
- Your commits may not change a spec's requirements or success criteria
  (only its Traceability table), nor a tasks file beyond a task's checkbox.
- Your commits may not change these protected paths: {protected}
- Your commits may not delete a test file.
- A diff that breaks one of the three rules above is refused: nothing is pushed.
- If the task needs any of this, or a gate command is refused,
  do not work around it: report status "escalated" and name what was refused."""


def _conventions(project: ProjectConfig) -> str:
    """The conventions block, with the gate rendered from project config —
    the framework's own toolchain names never appear in fixed text (R-2)."""
    gate = "\n".join(f"    {i}. {cmd}" for i, cmd in enumerate(project.gate_commands, 1))
    note = (
        f"\n- Project note: {project.conventions_note}"
        if project.conventions_note
        else ""
    )
    return f"""\
CONVENTIONS (the gate your PR must pass):
- Work only on this task. Its criteria are the contract; do not rework them.
- Commit with Conventional Commits (`feat:`, `fix:`, ...); keep the diff
  PR-sized (~<300 lines).
- Every claimed criterion needs a test citing its SC- id; the validator
  REJECTs any claimed id with no citing test, and a PASS without citations
  is impossible by construction.
- This project's gate — run every command and make it green before you
  commit:
{gate}
- Commit everything you want reviewed; the orchestrator pushes your branch
  and opens the PR with the `Satisfies:` declaration for you. Never merge,
  never push, never open a PR yourself.{note}

{_limits(project)}

{_ESCALATION}"""


def parse_task(spec_slug: str, task_id: str, *, specs_dir: Path = Path("specs")) -> TaskSpec:
    """Extract one task from `specs/<slug>/` artifacts; loud on any gap."""
    tasks_path = specs_dir / spec_slug / "tasks.md"
    spec_path = specs_dir / spec_slug / "spec.md"
    if not tasks_path.is_file() or not spec_path.is_file():
        raise UnknownTaskError(f"no spec artifacts under {specs_dir / spec_slug}")

    block = task_block(tasks_path.read_text(encoding="utf-8"), task_id)
    if block is None:
        raise UnknownTaskError(f"task {task_id!r} not found in {tasks_path}")
    section_text = block

    satisfies_m = re.search(r"^- \*\*Satisfies:\*\*(.*)$", section_text, re.MULTILINE)
    criteria = tuple(
        sorted(set(_SC_RE.findall(satisfies_m.group(1) if satisfies_m else "")),
               key=lambda s: int(s[3:]))
    )

    spec_text = spec_path.read_text(encoding="utf-8")
    criterion_texts: dict[str, str] = {}
    for sc in criteria:
        text = criterion_text(spec_text, sc)
        if text is None:
            raise UnknownTaskError(
                f"{task_id} claims {sc}, but {spec_path} defines no such criterion"
            )
        criterion_texts[sc] = text

    return TaskSpec(
        spec_slug=spec_slug,
        task_id=task_id,
        criteria=criteria,
        section=section_text,
        criterion_texts=criterion_texts,
        requirements=section(spec_text, "Requirements"),
    )


def branch_name(task: TaskSpec) -> str:
    """The deterministic branch a worker's PR ships on."""
    return f"feat/{task.spec_slug}-{task.task_id.lower()}"


def build_brief(task: TaskSpec, project: ProjectConfig = DEFAULTS) -> str:
    """Render the self-contained brief the session executes from."""
    criteria_block = "\n\n".join(task.criterion_texts[sc] for sc in task.criteria)
    return f"""\
You are a worker agent. Execute exactly one task and nothing else.

{_RESULT_CONTRACT}

== YOUR TASK ({task.task_id}, spec: {task.spec_slug}) ==
{task.section}

== THE CRITERIA YOUR TESTS MUST CITE ==
{criteria_block or "(this task satisfies no criteria directly — see its brief)"}

== THE SPEC'S REQUIREMENTS (context; RFC 2119 keywords) ==
{task.requirements}

== HOW YOUR WORK SHIPS ==
Your branch: {branch_name(task)} (already checked out in this worktree).
Your PR body will declare: Satisfies: {", ".join(task.criteria) or "—"}

{_conventions(project)}

{_RESULT_CONTRACT}"""
