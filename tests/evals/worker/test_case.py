"""Worker eval cases, the settings file and the brief at the start commit
(specs/worker-eval SC-1, SC-2). No session is started."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agent_framework.errors import EvalCaseError
from agent_framework.evals.worker.case import (
    CaseSet,
    CaseTask,
    Provenance,
    Reference,
    WorkerCase,
    brief_at_start,
    case_set_fingerprint,
    dump_case,
    load_case,
    load_case_set,
    load_cases,
    load_settings,
    write_case,
)

REPO = Path(__file__).resolve().parents[3]


def _case(case_id: str = "pr-31", start: str = "a" * 40, task: str = "T-1") -> WorkerCase:
    return WorkerCase(
        id=case_id,
        task=CaseTask(spec="fixture", task=task),
        reference=Reference(repo="vpciii/agent-framework", pr=31, start=start, head="b" * 40),
        reference_tests=("tests/test_fixture.py",),
        provenance=Provenance(frozen="2026-11-16", by="agent-framework-eval worker freeze"),
    )


def test_sc1_a_case_round_trips_through_its_file(tmp_path: Path) -> None:
    """SC-1: frozen, written, read back with every field."""
    case = _case()
    path = write_case(case, tmp_path)
    assert path == tmp_path / "pr-31.json"
    back = load_case(path)
    assert back == case
    assert back.task == CaseTask("fixture", "T-1")
    assert (back.reference.pr, back.reference.start, back.reference.head) == (
        31, "a" * 40, "b" * 40,
    )
    assert back.reference_tests == ("tests/test_fixture.py",)
    assert back.provenance.frozen == "2026-11-16"
    assert dump_case(back) == path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "field",
    [
        "task", "task.spec", "task.task", "reference", "reference.repo", "reference.pr",
        "reference.start", "reference.head", "reference_tests",
        "provenance", "provenance.frozen", "provenance.by",
    ],
)
def test_sc1_a_file_missing_a_field_fails_naming_the_file_and_the_field(
    tmp_path: Path, field: str
) -> None:
    """SC-1: each missing field is an error naming the file and the field."""
    data = json.loads(dump_case(_case()))
    *parents, leaf = field.split(".")
    table = data
    for name in parents:
        table = table[name]
    del table[leaf]
    path = tmp_path / "pr-31.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(EvalCaseError) as e:
        load_case(path)
    assert str(path) in str(e.value)
    assert repr(field) in str(e.value)


def test_sc1_empty_reference_tests_are_missing(tmp_path: Path) -> None:
    data = json.loads(dump_case(_case()))
    data["reference_tests"] = []
    path = tmp_path / "pr-31.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(EvalCaseError, match="'reference_tests'"):
        load_case(path)


def test_the_committed_settings_load() -> None:
    settings = load_settings(REPO / "evals/worker/settings.toml")
    assert "uv run pytest" in settings.project.gate_commands
    assert settings.project.session_network == ("pypi.org", "files.pythonhosted.org")
    assert settings.reference_test_command == "uv run pytest {files}"


def test_settings_errors_name_the_settings_file(tmp_path: Path) -> None:
    path = tmp_path / "settings.toml"
    path.write_text('[project]\nnope = 1\n[eval]\nreference_test_command = "x {files}"\n')
    with pytest.raises(EvalCaseError, match=str(path)):
        load_settings(path)
    path.write_text("[project]\n")
    with pytest.raises(EvalCaseError, match=r"\[eval\]"):
        load_settings(path)


def test_the_fingerprint_is_over_the_cases_and_settings_not_their_order() -> None:
    settings = load_settings(REPO / "evals/worker/settings.toml")
    a, b = _case("pr-31"), _case("pr-38")
    fp = case_set_fingerprint(CaseSet((a, b), settings))
    assert len(fp) == 12 and int(fp, 16) >= 0
    assert case_set_fingerprint(CaseSet((b, a), settings)) == fp
    assert case_set_fingerprint(CaseSet((a,), settings)) != fp
    other = CaseSet((a, b), type(settings)(settings.project, "pytest -q {files}"))
    assert case_set_fingerprint(other) != fp


# ---- SC-2: the brief at the start commit ---------------------------------------

_TASKS = """# Tasks

### [ ] T-1 — Do the thing
- **Satisfies:** SC-1
- **Brief:** {marker}
"""

_SPEC = """# Spec

## Requirements

- **R-1 (MUST)** The thing is done.

## Success criteria

- **SC-1** — The thing is done. (R-1)
"""


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, str]:
    """A repository whose `specs/fixture/` changed after the start commit."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    specs = root / "specs" / "fixture"
    specs.mkdir(parents=True)
    (specs / "tasks.md").write_text(_TASKS.format(marker="AS IT WAS AT THE START"))
    (specs / "spec.md").write_text(_SPEC)
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "start")
    start = _git(root, "rev-parse", "HEAD")
    (specs / "tasks.md").write_text(_TASKS.format(marker="REWRITTEN LATER"))
    _git(root, "commit", "-q", "-am", "later")
    (specs / "tasks.md").write_text(_TASKS.format(marker="UNCOMMITTED"))
    return root, start


def test_sc2_the_brief_is_built_from_the_start_commits_artifacts(
    repo: tuple[Path, str],
) -> None:
    """SC-2: the brief is the start commit's task, not the working tree's."""
    root, start = repo
    settings = load_settings(REPO / "evals/worker/settings.toml")
    brief = brief_at_start(_case(start=start), settings, repo=root)
    assert "AS IT WAS AT THE START" in brief
    assert "REWRITTEN LATER" not in brief and "UNCOMMITTED" not in brief
    assert "The thing is done." in brief
    assert "uv run mypy --strict" in brief  # the set's settings, not a default


def test_sc2_a_case_whose_task_is_absent_at_its_start_fails_naming_the_case(
    repo: tuple[Path, str],
) -> None:
    """SC-2: a task not found at the start commit fails, naming the case."""
    root, start = repo
    settings = load_settings(REPO / "evals/worker/settings.toml")
    with pytest.raises(EvalCaseError, match="case pr-99:.*T-9"):
        brief_at_start(_case("pr-99", start=start, task="T-9"), settings, repo=root)
    first = _git(root, "rev-list", "--max-parents=0", "HEAD")
    missing = _case("pr-98", start=first)
    missing = WorkerCase(
        missing.id, CaseTask("absent", "T-1"), missing.reference,
        missing.reference_tests, missing.provenance,
    )
    with pytest.raises(EvalCaseError, match="case pr-98:.*specs/absent/tasks.md"):
        brief_at_start(missing, settings, repo=root)


def test_sc2_every_committed_case_builds_its_brief_at_its_start_commit() -> None:
    """SC-2: the CI check over the committed set — no session is run. It
    passes while the set is empty."""
    case_set = load_case_set(REPO / "evals/worker/cases")
    assert case_set.cases == load_cases(REPO / "evals/worker/cases")
    for case in case_set.cases:
        brief = brief_at_start(case, case_set.settings, repo=REPO)
        assert case.task.task in brief
