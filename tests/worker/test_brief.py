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
