"""The collector edge, against a faked `gh` runner (no subprocess, no network).

Delivery-edge tests (T-4) — the core criteria are covered by the SC-cited
tests in test_verdict / test_judgment / test_gate.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence

from agent_framework.validator.collector import collect_bundle

_VIEW = {
    "number": 42,
    "title": "fix: T-7 close the gap (SC-3)",
    "body": (
        "Regression fix.\n\n"
        "The test failed before the change (exit 1, AssertionError), passes after.\n\n"
        "Also mentions SC-4."
    ),
    "headRefOid": "abc123",
    "files": [
        {"path": "src/agent_framework/x.py"},
        {"path": "tests/test_x.py"},
        {"path": "tests/data.json"},
    ],
    "statusCheckRollup": [
        {"name": "ci", "status": "COMPLETED", "conclusion": "SUCCESS"},
    ],
}

_TEST_SOURCE = 'def test_sc3_regression() -> None:\n    """SC-3."""\n    assert True\n'


def _fake_runner(
    view: dict[str, object],
) -> tuple[list[Sequence[str]], Callable[[Sequence[str]], str]]:
    calls: list[Sequence[str]] = []

    def run(args: Sequence[str]) -> str:
        calls.append(args)
        if list(args[:3]) == ["gh", "pr", "view"]:
            return json.dumps(view)
        if list(args[:3]) == ["gh", "pr", "diff"]:
            return "+ the diff"
        if list(args[:2]) == ["gh", "api"]:
            return _TEST_SOURCE
        raise AssertionError(f"unexpected command: {args}")

    return calls, run


def test_collector_assembles_bundle_from_pr() -> None:
    calls, run = _fake_runner(_VIEW)

    bundle = collect_bundle(42, run=run)

    assert bundle.task.task_id == "T-7"
    assert bundle.task.criteria == ("SC-3", "SC-4")  # sorted, de-duplicated
    assert bundle.task.is_fix is True
    assert bundle.diff == "+ the diff"
    # Only tests/*.py files are fetched, at the PR head ref.
    assert bundle.tests == {"tests/test_x.py": _TEST_SOURCE}
    fetched = [a for a in calls if list(a[:2]) == ["gh", "api"]]
    assert len(fetched) == 1 and "ref=abc123" in fetched[0][-1]
    assert bundle.ci.green is True
    assert "ci: SUCCESS" in bundle.ci.summary
    # Red evidence: the body paragraph describing the failing-before run.
    assert bundle.red_evidence is not None
    assert "failed before" in bundle.red_evidence


def test_collector_non_fix_without_task_id_defaults() -> None:
    view = dict(_VIEW, title="docs: something (SC-1)", body="no task id here")
    _, run = _fake_runner(view)

    bundle = collect_bundle(99, run=run)

    assert bundle.task.task_id == "PR-99"
    assert bundle.task.is_fix is False
    assert bundle.red_evidence is None


def test_collector_red_ci_and_missing_checks_are_not_green() -> None:
    view = dict(_VIEW, statusCheckRollup=[{"name": "ci", "conclusion": "FAILURE"}])
    _, run = _fake_runner(view)
    assert collect_bundle(1, run=run).ci.green is False

    view = dict(_VIEW, statusCheckRollup=[])
    _, run = _fake_runner(view)
    ci = collect_bundle(1, run=run).ci
    assert ci.green is False and "no status checks" in ci.summary
