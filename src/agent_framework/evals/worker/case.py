"""Worker eval cases and the settings every case in the set runs under.

A **worker eval case** is one JSON file naming a past task, its
**reference pull request** (with the commit it started from and its head)
and that pull request's test files for the task's criteria. The set is a
directory of them beside one `settings.toml`, whose `[project]` table is
read by the same loader as `agent-framework.toml` (specs/worker-eval R-1,
R-4; plan.md *Data model changes*).

Loading is strict: a file missing a field is an `EvalCaseError` naming the
file and the field. `brief_at_start` builds a case's brief from its start
commit's own artifacts, read with `git show` — no checkout, no session.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ...errors import EvalCaseError, ProjectConfigError, UnknownTaskError
from ...proc import Runner, run_command
from ...project import CONFIG_FILE, ProjectConfig, load_project_config
from ...worker.brief import ArtifactUnreadableError, build_brief, parse_task_at


@dataclass(frozen=True)
class CaseTask:
    """The task a case measures: a spec slug and a task id."""

    spec: str
    task: str


@dataclass(frozen=True)
class Reference:
    """The reference pull request: the merged pull request that completed
    the task, the commit it started from and its head commit."""

    repo: str
    pr: int
    start: str
    head: str


@dataclass(frozen=True)
class Provenance:
    """When a case was frozen, and by what."""

    frozen: str
    by: str


@dataclass(frozen=True)
class WorkerCase:
    id: str
    task: CaseTask
    reference: Reference
    reference_tests: tuple[str, ...]
    provenance: Provenance


@dataclass(frozen=True)
class Settings:
    """What every case in the set runs under, declared once."""

    project: ProjectConfig
    reference_test_command: str


@dataclass(frozen=True)
class CaseSet:
    cases: tuple[WorkerCase, ...]  # by id
    settings: Settings


# ---- one case ---------------------------------------------------------------


def _get(data: dict[str, Any], name: str, kind: type, where: str, field: str) -> Any:
    if name not in data:
        raise EvalCaseError(f"{where}: missing field {field!r}")
    value = data[name]
    if not isinstance(value, kind) or isinstance(value, bool) or value in ("", [], {}):
        raise EvalCaseError(f"{where}: field {field!r} must be a non-empty {kind.__name__}")
    return value


def _table(data: dict[str, Any], name: str, where: str) -> dict[str, Any]:
    table: dict[str, Any] = _get(data, name, dict, where, name)
    return table


def load_case(path: Path) -> WorkerCase:
    """Read one case file; a missing or malformed field names the file and the field."""
    where = str(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise EvalCaseError(f"{where}: cannot be read as JSON ({e})") from None
    if not isinstance(data, dict):
        raise EvalCaseError(f"{where}: a worker eval case is a JSON object")

    case_id = _get(data, "id", str, where, "id")
    if case_id != path.stem:
        raise EvalCaseError(f"{where}: field 'id' is {case_id!r}; it must be the file's name")
    task = _table(data, "task", where)
    ref = _table(data, "reference", where)
    tests = _get(data, "reference_tests", list, where, "reference_tests")
    if not all(isinstance(t, str) and t for t in tests):
        raise EvalCaseError(f"{where}: field 'reference_tests' must be a list of paths")
    prov = _table(data, "provenance", where)
    return WorkerCase(
        id=case_id,
        task=CaseTask(
            spec=_get(task, "spec", str, where, "task.spec"),
            task=_get(task, "task", str, where, "task.task"),
        ),
        reference=Reference(
            repo=_get(ref, "repo", str, where, "reference.repo"),
            pr=_get(ref, "pr", int, where, "reference.pr"),
            start=_get(ref, "start", str, where, "reference.start"),
            head=_get(ref, "head", str, where, "reference.head"),
        ),
        reference_tests=tuple(tests),
        provenance=Provenance(
            frozen=_get(prov, "frozen", str, where, "provenance.frozen"),
            by=_get(prov, "by", str, where, "provenance.by"),
        ),
    )


def dump_case(case: WorkerCase) -> str:
    """The case as the text of its file."""
    data = asdict(case)
    data["reference_tests"] = list(case.reference_tests)
    return json.dumps(data, indent=2) + "\n"


def write_case(case: WorkerCase, directory: Path) -> Path:
    """Write the case as `<directory>/<id>.json`; return its path."""
    path = directory / f"{case.id}.json"
    path.write_text(dump_case(case), encoding="utf-8")
    return path


# ---- the settings and the set -------------------------------------------------


def load_settings(path: Path) -> Settings:
    """Read `settings.toml`: its `[project]` table through `load_project_config`,
    and `[eval] reference_test_command`."""
    try:
        text = path.read_text(encoding="utf-8")
        data = tomllib.loads(text)
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise EvalCaseError(f"{path}: cannot be read as TOML ({e})") from None
    if not isinstance(data.get("project"), dict):
        raise EvalCaseError(f"{path}: missing table [project]")
    table = data.get("eval")
    if not isinstance(table, dict):
        raise EvalCaseError(f"{path}: missing table [eval]")
    command = table.get("reference_test_command")
    if not isinstance(command, str) or "{files}" not in command:
        raise EvalCaseError(
            f"{path}: [eval] reference_test_command must be a string holding {{files}}"
        )
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / CONFIG_FILE).write_text(text, encoding="utf-8")
        try:
            project = load_project_config(Path(tmp))
        except ProjectConfigError as e:
            message = str(e).replace(str(Path(tmp) / CONFIG_FILE), str(path))
            raise EvalCaseError(message) from None
    return Settings(project=project, reference_test_command=command)


def load_cases(directory: Path) -> tuple[WorkerCase, ...]:
    """Every case file in the directory, by id."""
    return tuple(load_case(p) for p in sorted(directory.glob("*.json"), key=lambda p: p.stem))


def load_case_set(cases_dir: Path, settings_path: Path | None = None) -> CaseSet:
    """The cases in `cases_dir` and the settings beside it (`../settings.toml`)."""
    settings = load_settings(settings_path or cases_dir.parent / "settings.toml")
    return CaseSet(cases=load_cases(cases_dir), settings=settings)


def case_set_fingerprint(case_set: CaseSet) -> str:
    """12 hex characters over every case and the settings, whatever the
    order the cases were read in."""
    digest = hashlib.sha256()
    for case in sorted(case_set.cases, key=lambda c: c.id):
        digest.update(dump_case(case).encode())
        digest.update(b"\0")
    settings = asdict(case_set.settings)
    digest.update(json.dumps(settings, sort_keys=True, default=list).encode())
    return digest.hexdigest()[:12]


# ---- the brief at the start commit -------------------------------------------


def brief_at_start(
    case: WorkerCase, settings: Settings, *, repo: Path = Path("."), run: Runner = run_command
) -> str:
    """The brief the worker would be given for this case, built by the
    worker's own `parse_task` and `build_brief` from the task's `tasks.md`
    and `spec.md` as they were at the case's start commit."""
    slug, start = case.task.spec, case.reference.start
    try:
        task = parse_task_at(slug, case.task.task, start, repo=repo, run=run)
    except ArtifactUnreadableError as e:
        raise EvalCaseError(
            f"case {case.id}: cannot read {e.source} at its start commit {start}: {e.reason}"
        ) from None
    except UnknownTaskError as e:
        raise EvalCaseError(f"case {case.id}: at its start commit {start}: {e}") from None
    return build_brief(task, settings.project)
