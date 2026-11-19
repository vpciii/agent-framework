"""Brief assembly.

Verifies SC-1: the brief is self-contained — the task's section, every
claimed criterion with its text, and the conventions; nothing from outside
the two artifact files; unknown slug/task id fails loudly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_framework.errors import UnknownTaskError
from agent_framework.worker.brief import build_brief, parse_task

_TASKS_MD = """\
# Tasks: Fixture

- **Status:** Approved

### [ ] T-1 — Build the widget
- **Satisfies:** SC-1, SC-2
- **Depends on:** —
- **Brief:** Make the widget spin. WIDGET-DETAIL-SENTINEL.
- **Done when:** tests citing SC-1, SC-2 pass.

### [ ] T-9 — Another task entirely
- **Satisfies:** SC-3
- **Brief:** OTHER-TASK-SENTINEL must never leak into T-1's brief.

---

## Criterion → task map
FOOTER-SENTINEL
"""

_SPEC_MD = """\
# Spec: Fixture

- **Status:** Approved

## Problem

PROBLEM-SENTINEL: background prose the brief must not carry.

## Requirements

- **R-1 (MUST)** The widget spins. REQUIREMENT-TEXT-MARKER.

## Success criteria

- **SC-1** — The widget spins clockwise. CRITERION-ONE-TEXT.
  (R-1)
- **SC-2** — The widget stops on demand. CRITERION-TWO-TEXT. (R-1)
- **SC-3** — Unrelated criterion. CRITERION-THREE-SENTINEL. (R-1)
"""


@pytest.fixture
def specs_dir(tmp_path: Path) -> Path:
    d = tmp_path / "specs" / "fixture"
    d.mkdir(parents=True)
    (d / "tasks.md").write_text(_TASKS_MD, encoding="utf-8")
    (d / "spec.md").write_text(_SPEC_MD, encoding="utf-8")
    return tmp_path / "specs"


def test_sc1_brief_contains_task_criteria_and_conventions(specs_dir: Path) -> None:
    """SC-1: the task's section, each claimed criterion's text, the conventions."""
    task = parse_task("fixture", "T-1", specs_dir=specs_dir)
    brief = build_brief(task)

    assert "WIDGET-DETAIL-SENTINEL" in brief  # the task's own section, verbatim
    assert "CRITERION-ONE-TEXT" in brief and "CRITERION-TWO-TEXT" in brief
    assert "REQUIREMENT-TEXT-MARKER" in brief  # the spec's Requirements ride along
    assert "Satisfies: SC-1, SC-2" in brief  # the declaration the PR will carry
    assert "feat/fixture-t-1" in brief  # the deterministic branch
    assert ".worker-result.json" in brief  # the result contract
    assert "escalat" in brief.lower()  # the escalation contract


def test_sc1_brief_contains_nothing_from_outside_the_artifacts(specs_dir: Path) -> None:
    """SC-1 (self-containment): other tasks' text and non-contract spec prose
    do not leak into the brief."""
    brief = build_brief(parse_task("fixture", "T-1", specs_dir=specs_dir))

    assert "OTHER-TASK-SENTINEL" not in brief  # a different task's section
    assert "CRITERION-THREE-SENTINEL" not in brief  # a criterion T-1 doesn't claim
    assert "PROBLEM-SENTINEL" not in brief  # spec prose outside the contract
    assert "FOOTER-SENTINEL" not in brief  # tasks.md content past the section


def test_sc1_unknown_task_or_slug_fails_loudly(specs_dir: Path) -> None:
    """SC-1: no silent empty briefs."""
    with pytest.raises(UnknownTaskError, match="T-99"):
        parse_task("fixture", "T-99", specs_dir=specs_dir)
    with pytest.raises(UnknownTaskError, match="nonexistent"):
        parse_task("nonexistent", "T-1", specs_dir=specs_dir)


def test_task_claiming_undefined_criterion_fails_loudly(specs_dir: Path) -> None:
    """A tasks.md/spec.md contradiction (claimed SC not defined) is loud."""
    tasks = specs_dir / "fixture" / "tasks.md"
    tasks.write_text(
        tasks.read_text(encoding="utf-8").replace("SC-1, SC-2", "SC-1, SC-77"),
        encoding="utf-8",
    )
    with pytest.raises(UnknownTaskError, match="SC-77"):
        parse_task("fixture", "T-1", specs_dir=specs_dir)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("- **Satisfies:** SC-1, SC-2\n", ""),  # no Satisfies line at all
        ("- **Satisfies:** SC-1, SC-2\n", "- **Satisfies:** —\n"),  # a line naming nothing
    ],
)
def test_task_claiming_no_criterion_is_refused(specs_dir: Path, old: str, new: str) -> None:
    """A task that claims no criterion has no end point anything can check —
    the validator would have nothing to cite — so it is never dispatched."""
    tasks = specs_dir / "fixture" / "tasks.md"
    text = tasks.read_text(encoding="utf-8")
    assert old in text
    tasks.write_text(text.replace(old, new, 1), encoding="utf-8")

    with pytest.raises(UnknownTaskError, match="T-1 claims no success criterion"):
        parse_task("fixture", "T-1", specs_dir=specs_dir)


def test_sc2_brief_renders_the_configured_gate_not_the_framework_one(
    specs_dir: Path,
) -> None:
    """SC-2: a custom gate appears verbatim, with the conventions note, and
    none of the framework's own toolchain names."""
    from agent_framework.project import ProjectConfig

    project = ProjectConfig(
        gate_commands=("uv run pytest", "docker build -t opn-mcp-ci ."),
        conventions_note="Read CLAUDE.md; NOTE-SENTINEL applies.",
    )
    brief = build_brief(parse_task("fixture", "T-1", specs_dir=specs_dir), project)

    assert "uv run pytest" in brief
    assert "docker build -t opn-mcp-ci ." in brief
    assert "NOTE-SENTINEL" in brief
    assert "ruff" not in brief and "mypy" not in brief  # no framework toolchain leakage


def test_sc2_default_brief_carries_the_framework_gate(specs_dir: Path) -> None:
    """SC-2 (no-config half): absent config, the brief is today's — the
    framework's own gate, from DEFAULTS rather than fixed text."""
    brief = build_brief(parse_task("fixture", "T-1", specs_dir=specs_dir))
    assert "uv run mypy --strict" in brief
    assert "check_spec_coverage" in brief


def test_sc9_brief_states_the_limits_and_says_to_escalate(specs_dir: Path) -> None:
    """SC-9 (worker-confinement): the session is told what it cannot do, and
    that a task needing it is an escalation, not something to work around."""
    from agent_framework.project import ProjectConfig

    project = ProjectConfig(
        session_network=("pypi.org",), protected_paths=(".github/**", "infra/**"),
    )
    brief = build_brief(parse_task("fixture", "T-1", specs_dir=specs_dir), project)
    limits = brief[brief.index("LIMITS") :]

    assert "cannot push" in limits
    assert "outside this worktree" in limits
    assert "pypi.org" in limits  # the hosts it may reach, and so the ones it may not
    assert "requirements or success criteria" in limits  # the contract
    assert ".github/**" in limits and "infra/**" in limits  # protected paths
    assert "do not work around" in limits.lower()
    assert 'status "escalated"' in limits

    no_network = build_brief(parse_task("fixture", "T-1", specs_dir=specs_dir))
    assert "no network host" in no_network


def test_brief_says_how_to_write_files_and_commit_so_no_command_shape_is_refused(
    specs_dir: Path,
) -> None:
    """Regression (dispatch-from-issue T-5, issue 155): a session whose commit
    commands were refused for their shape — a result file written by heredoc,
    a message passed with `-m` — concluded it could not commit and escalated
    finished work. The brief names the one shape that holds for any message,
    and says a refusal is of the command, not of the commit."""
    brief = build_brief(parse_task("fixture", "T-1", specs_dir=specs_dir))

    commands = brief[brief.index("HOW TO WRITE FILES AND COMMIT"):]
    assert "git commit -q -F .worker-commit-msg" in commands
    assert "write the message with the Write tool" in commands
    assert "`.worker-commit-msg`" in commands and "git ignores it" in commands
    assert "Do\n  not pass the message with `-m` or a heredoc" in commands
    # The result file too: a heredoc holding its JSON is a refused shape.
    assert "Write and Edit tools" in commands and "`.worker-result.json`" in commands
    # What stopped the T-5 session was reading a refusal as final.
    assert "does not mean you cannot commit" in commands
    assert "nobody\n  can approve one for you" in commands
    # It comes before the result contract's last statement, after the conventions.
    assert brief.index("CONVENTIONS") < brief.index("HOW TO WRITE FILES AND COMMIT")
    assert brief.rindex("RESULT CONTRACT") > brief.index("HOW TO WRITE FILES AND COMMIT")
