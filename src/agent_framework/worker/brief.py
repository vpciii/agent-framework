"""Brief assembly: the self-contained document a worker session executes from.

Pure — its only inputs are the two artifact files (`tasks.md`, `spec.md`),
by construction: a worker reads its brief, never the chief's (or anyone's)
conversation context. Everything else in the brief is fixed convention text.
"""

from __future__ import annotations

import re
from pathlib import Path

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

{_ESCALATION}"""


def _section(text: str, title: str) -> str:
    """Body of the `## <title>` section of a spec file, or ""."""
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", text, re.M))
    for i, m in enumerate(matches):
        if m.group(1).strip().lower() == title.lower():
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            return text[m.end() : end].strip()
    return ""


def parse_task(spec_slug: str, task_id: str, *, specs_dir: Path = Path("specs")) -> TaskSpec:
    """Extract one task from `specs/<slug>/` artifacts; loud on any gap."""
    tasks_path = specs_dir / spec_slug / "tasks.md"
    spec_path = specs_dir / spec_slug / "spec.md"
    if not tasks_path.is_file() or not spec_path.is_file():
        raise UnknownTaskError(f"no spec artifacts under {specs_dir / spec_slug}")

    tasks_text = tasks_path.read_text(encoding="utf-8")
    section_re = re.compile(
        rf"^### \[.\] {re.escape(task_id)}\b.*?(?=^### |^---|\Z)", re.M | re.S
    )
    m = section_re.search(tasks_text)
    if m is None:
        raise UnknownTaskError(f"task {task_id!r} not found in {tasks_path}")
    section = m.group(0).strip()

    satisfies_m = re.search(r"^- \*\*Satisfies:\*\*(.*)$", section, re.M)
    criteria = tuple(
        sorted(set(_SC_RE.findall(satisfies_m.group(1) if satisfies_m else "")),
               key=lambda s: int(s[3:]))
    )

    spec_text = spec_path.read_text(encoding="utf-8")
    criteria_section = _section(spec_text, "Success criteria")
    criterion_texts: dict[str, str] = {}
    for sc in criteria:
        sc_m = re.search(
            rf"^- \*\*{re.escape(sc)}\*\*(.*?)(?=^- \*\*SC-|\Z)",
            criteria_section,
            re.M | re.S,
        )
        if sc_m is None:
            raise UnknownTaskError(
                f"{task_id} claims {sc}, but {spec_path} defines no such criterion"
            )
        criterion_texts[sc] = f"**{sc}**{sc_m.group(1).rstrip()}"

    return TaskSpec(
        spec_slug=spec_slug,
        task_id=task_id,
        criteria=criteria,
        section=section,
        criterion_texts=criterion_texts,
        requirements=_section(spec_text, "Requirements"),
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
