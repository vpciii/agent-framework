"""The handoff check (specs/worker-confinement, ADR 0007 decision 4).

Verifies SC-5 against real git repositories: each kind of change a session
may not hand back is refused, naming the path; ordinary task work passes.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from agent_framework.proc import run_command
from agent_framework.project import ProjectConfig
from agent_framework.worker.handoff_check import HandoffFinding, check_handoff

_SPEC = """# Spec: Widget

## Requirements

- **R-1 (MUST)** The widget spins when asked.

## Success criteria

- **SC-1** — The widget spins within one second. (R-1)

## Traceability

| Criterion | Requirement(s) | Verified by (test) |
|---|---|---|
| SC-1 | R-1 | *(pending)* |
"""
_TASKS = """# Tasks: Widget

### [ ] T-1 — Make the widget spin
- **Satisfies:** SC-1
- **Brief:** Spin it.

### [ ] T-2 — Make the widget stop
- **Satisfies:** SC-1
"""
_FILES = {
    "specs/widget/spec.md": _SPEC,
    "specs/widget/tasks.md": _TASKS,
    ".github/workflows/ci.yml": "name: CI\n",
    "agent-framework.toml": '[roles]\nworker = { provider = "a", model = "m" }\n',
    "src/widget.py": "def spin() -> bool:\n    return False\n",
    "tests/test_widget.py": "def test_spins() -> None:\n    assert True\n",
    "tests/test_other.py": "def test_other() -> None:\n    assert True\n",
}


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A session's checkout: a clone with a task branch cut from `origin/main`."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(origin), str(clone))
    _write(clone, _FILES)
    _git(clone, "add", "-A")
    _git(clone, "commit", "-q", "-m", "feat: seed")
    _git(clone, "push", "-q", "origin", "HEAD:main")
    _git(clone, "fetch", "-q", "origin")
    _git(clone, "switch", "-q", "-c", "feat/widget-t-1", "--no-track", "origin/main")
    return clone


def _commit(tree: Path, files: dict[str, str], *, delete: tuple[str, ...] = ()) -> None:
    _write(tree, files)
    for rel in delete:
        _git(tree, "rm", "-q", rel)
    _git(tree, "add", "-A")
    _git(tree, "commit", "-q", "-m", "feat: the session's work")


def _check(tree: Path, project: ProjectConfig | None = None) -> tuple[HandoffFinding, ...]:
    return check_handoff(tree, project or ProjectConfig())


@pytest.mark.parametrize(
    ("files", "delete", "rule", "path"),
    [
        # A reworded success criterion.
        ({"specs/widget/spec.md": _SPEC.replace("within one second", "eventually")}, (),
         "contract", "specs/widget/spec.md"),
        # A changed requirement.
        ({"specs/widget/spec.md": _SPEC.replace("(MUST)", "(SHOULD)")}, (),
         "contract", "specs/widget/spec.md"),
        # A tasks.md edit beyond a checkbox.
        ({"specs/widget/tasks.md": _TASKS.replace("Spin it.", "Spin it, or don't.")}, (),
         "contract", "specs/widget/tasks.md"),
        # A change under a protected path — each of the two defaults.
        ({".github/workflows/ci.yml": "name: CI\non: []\n"}, (),
         "protected-path", ".github/workflows/ci.yml"),
        ({"agent-framework.toml": "[roles]\n"}, (), "protected-path", "agent-framework.toml"),
        # A deleted test file.
        ({}, ("tests/test_other.py",), "deleted-test", "tests/test_other.py"),
    ],
)
def test_sc5_each_forbidden_change_is_refused_naming_the_path(
    tree: Path, files: dict[str, str], delete: tuple[str, ...], rule: str, path: str
) -> None:
    """SC-5: a reworded criterion, a changed requirement, a tasks edit beyond
    a checkbox, a protected path and a deleted test file are each a finding."""
    _commit(tree, {"src/widget.py": "def spin() -> bool:\n    return True\n", **files},
            delete=delete)

    findings = _check(tree)

    assert [(f.rule, f.path) for f in findings] == [(rule, path)]
    assert findings[0].detail  # says what was wrong, not just where


def test_sc5_ordinary_task_work_passes(tree: Path) -> None:
    """SC-5: filling a Traceability row, ticking a checkbox and changing
    source and tests is exactly what a session should hand back."""
    _commit(tree, {
        "specs/widget/spec.md": _SPEC.replace(
            "*(pending)*", "`tests/test_widget.py::test_spins`"
        ),
        "specs/widget/tasks.md": _TASKS.replace("### [ ] T-1", "### [x] T-1"),
        "src/widget.py": "def spin() -> bool:\n    return True\n",
        "tests/test_widget.py": 'def test_spins() -> None:\n    """SC-1."""\n    assert True\n',
        "tests/test_new.py": "def test_new() -> None:\n    assert True\n",
    })

    assert _check(tree) == ()


def test_sc5_several_violations_are_all_reported(tree: Path) -> None:
    """SC-5: the human sees every finding at once, not one per attempt."""
    _commit(tree, {
        "specs/widget/spec.md": _SPEC.replace("within one second", "eventually"),
        ".github/workflows/ci.yml": "name: nothing\n",
    }, delete=("tests/test_other.py",))

    assert {(f.rule, f.path) for f in _check(tree)} == {
        ("contract", "specs/widget/spec.md"),
        ("protected-path", ".github/workflows/ci.yml"),
        ("deleted-test", "tests/test_other.py"),
    }


def test_a_session_may_not_add_or_remove_a_spec_or_tasks_file(tree: Path) -> None:
    _commit(tree, {"specs/gadget/spec.md": "# Spec: Gadget\n"},
            delete=("specs/widget/tasks.md",))

    assert {(f.rule, f.path) for f in _check(tree)} == {
        ("contract", "specs/gadget/spec.md"),
        ("contract", "specs/widget/tasks.md"),
    }


def test_a_rename_does_not_carry_a_file_past_a_rule(tree: Path) -> None:
    """Renames are read as a delete plus an add, so moving a test file away
    is a deleted test, and moving a file onto a protected path is a change there."""
    _git(tree, "mv", "tests/test_other.py", "tests_old.py")
    _git(tree, "mv", "src/widget.py", ".github/widget.py")
    _git(tree, "commit", "-q", "-m", "refactor: move things")

    assert {(f.rule, f.path) for f in _check(tree)} == {
        ("deleted-test", "tests/test_other.py"),
        ("protected-path", ".github/widget.py"),
    }


def test_the_projects_own_protected_and_test_paths_are_the_ones_applied(tree: Path) -> None:
    project = ProjectConfig(protected_paths=("src/**",), test_paths=("spec/**/*.js",))
    _commit(tree, {"src/widget.py": "def spin() -> bool:\n    return True\n",
                   ".github/workflows/ci.yml": "name: changed\n"},
            delete=("tests/test_other.py",))

    assert [(f.rule, f.path) for f in _check(tree, project)] == [
        ("protected-path", "src/widget.py"),
    ]


def test_only_commits_are_checked_and_only_since_the_tree_was_cut(tree: Path) -> None:
    """Uncommitted edits are never pushed, so they are not findings; and work
    merged upstream after the tree was cut is not the session's."""
    _commit(tree, {"src/widget.py": "def spin() -> bool:\n    return True\n"})
    (tree / "specs/widget/spec.md").write_text("scribbled, not committed\n")

    other = tree.parent / "other"
    _git(tree.parent, "clone", "-q", str(tree.parent / "origin.git"), str(other))
    _write(other, {".github/workflows/ci.yml": "name: changed upstream\n"})
    _git(other, "commit", "-q", "-am", "ci: upstream change")
    _git(other, "push", "-q", "origin", "HEAD:main")
    _git(tree, "fetch", "-q", "origin")

    assert _check(tree) == ()


def test_the_check_runs_no_repository_hook(tree: Path) -> None:
    """Its own git commands carry no hooks (R-9's half that lives here)."""
    calls: list[list[str]] = []

    def run(args: Sequence[str]) -> str:
        calls.append(list(args))
        return run_command(args)

    check_handoff(tree, ProjectConfig(), run=run)

    assert calls and all(c[:3] == ["git", "-c", "core.hooksPath=/dev/null"] for c in calls)
