"""Freezing a merged pull request into an accepted case (specs/validator-eval-set).

Each test's docstring names the one criterion it verifies. GitHub is a
faked `gh` runner: no subprocess, no network.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest

from agent_framework.errors import EvalCaseError
from agent_framework.evals import __main__ as eval_cli
from agent_framework.evals import freeze as freeze_module
from agent_framework.evals.case import dump_case, load_case
from agent_framework.evals.freeze import freeze
from agent_framework.project import ProjectConfig
from agent_framework.validator.checks import run_checks
from agent_framework.validator.collector import collect_bundle

SPEC = """# Demo

## Success criteria

- **SC-1** — The collector returns one. (R-1)

## Traceability

| Criterion | Requirement | Test |
|---|---|---|
| SC-1 | R-1 | `tests/test_x.py::test_sc1_collects_one` |
"""
TASKS = "### [ ] T-2 — Collect\n- **Satisfies:** SC-1\n- **Brief:** Return one.\n"
TEST_SOURCE = 'def test_sc1_collects_one() -> None:\n    """SC-1."""\n    assert collect() == 1\n'
DIFF = "+def collect() -> int:\n+    return 1\n"

_VIEW: dict[str, Any] = {
    "number": 7,
    "title": "feat: T-2 collect",
    "body": "Implements T-2 of specs/demo/.\n\nSatisfies: SC-1\n",
    "state": "MERGED",
    "mergedAt": "2026-11-09T14:03:11Z",
    "mergedBy": {"login": "vpc"},
    "url": "https://github.com/acme/widgets/pull/7",
    "baseRefOid": "base000",
    "headRefOid": "head111",
    "files": [{"path": "src/x.py"}, {"path": "tests/test_x.py"}],
    "statusCheckRollup": [
        {"name": "ci", "status": "COMPLETED", "conclusion": "SUCCESS"},
        {"name": "validator", "status": "COMPLETED", "conclusion": "FAILURE"},
    ],
}
_FILES = {
    "specs/demo/spec.md": SPEC,
    "specs/demo/tasks.md": TASKS,
    "tests/test_x.py": TEST_SOURCE,
}

Run = Callable[[Sequence[str]], str]


def _gh(**changed: Any) -> tuple[list[Sequence[str]], Run]:
    """A `gh` that knows one pull request, #7 — as `_VIEW`, with `changed`."""
    view = {**_VIEW, **changed}
    calls: list[Sequence[str]] = []

    def run(args: Sequence[str]) -> str:
        calls.append(args)
        if list(args[:3]) == ["gh", "pr", "view"]:
            return json.dumps(view)
        if list(args[:3]) == ["gh", "pr", "diff"]:
            return DIFF
        if list(args[:2]) == ["gh", "api"]:
            path = args[-1].split("/contents/")[1].split("?ref=")[0]
            if path in _FILES:
                return _FILES[path]
            raise RuntimeError(f"command failed (1): {' '.join(args)}\nHTTP 404")
        raise AssertionError(f"unexpected command: {args}")

    return calls, run


# ---- SC-4: a merged pull request becomes an accepted case that loads -------


def test_sc4_freeze_writes_an_accepted_case_that_loads_as_the_collected_bundle(
    tmp_path: Path,
) -> None:
    """SC-4: given a merged pull request through a faked `gh`, freeze writes
    an accepted case, and what loads back is the bundle the collector builds."""
    _, run = _gh()

    written = freeze(7, tmp_path / "cases", run=run, today="2026-11-10")

    assert written == tmp_path / "cases" / "pr-7.json"
    case = load_case(written)
    assert (case.id, case.kind, case.expected, case.check) == ("pr-7", "accepted", "pass", None)
    assert case.reason == "Merged 2026-11-09; accepted by vpc."
    assert (case.provenance.repo, case.provenance.pr) == ("acme/widgets", 7)
    assert (case.provenance.head, case.provenance.frozen) == ("head111", "2026-11-10")
    assert case.bundle == collect_bundle(7, run=run, ignore_checks=frozenset({"validator"}))
    # The frozen bundle is one the judgment would really be asked about.
    assert run_checks(case.bundle) == ()
    assert case.bundle.contract is not None
    assert case.bundle.contract.task_block == TASKS.strip()


def test_sc4_freeze_collects_with_the_projects_own_config(tmp_path: Path) -> None:
    """SC-4 here: which checks are ignored, which files are tests and what a
    test looks like come from the project's config, as at the gate."""
    _, run = _gh()
    project = ProjectConfig(ignore_checks=("validator", "ci"))

    with pytest.raises(EvalCaseError, match=r"ci\b.*no status checks reported"):
        freeze(7, tmp_path, run=run, project=project)

    project = ProjectConfig(test_pattern=r"^it\('(\w+)'")
    with pytest.raises(EvalCaseError, match="criterion-citation"):
        freeze(7, tmp_path, run=run, project=project)


def test_sc4_repo_is_passed_to_gh_and_recorded(tmp_path: Path) -> None:
    """SC-4 here: `--repo` reaches every `gh` call and is the provenance."""
    calls, run = _gh()

    case = load_case(freeze(7, tmp_path, repo="other/place", run=run, today="2026-11-10"))

    assert case.provenance.repo == "other/place"
    views = [c for c in calls if list(c[:3]) == ["gh", "pr", "view"]]
    assert views and all("other/place" in c for c in views)


@pytest.mark.parametrize(
    ("changed", "says"),
    [
        ({"state": "OPEN", "mergedAt": None, "mergedBy": None}, "is not merged (OPEN)"),
        ({"state": "CLOSED", "mergedAt": None, "mergedBy": None}, "is not merged (CLOSED)"),
        ({"body": "Docs only."}, "satisfies-declaration"),
        ({"statusCheckRollup": [{"name": "ci", "conclusion": "FAILURE"}]}, "ci: "),
        ({"body": "Implements T-2 of specs/demo/.\n\nSatisfies: SC-9\n"}, "criterion-defined"),
    ],
)
def test_sc4_freeze_refuses_what_is_not_an_accepted_case_and_writes_nothing(
    tmp_path: Path, changed: dict[str, Any], says: str
) -> None:
    """SC-4: a pull request that is not merged, claims no criteria, or that
    the deterministic stage rejects is refused, naming the check — no file."""
    _, run = _gh(**changed)

    with pytest.raises(EvalCaseError) as refused:
        freeze(7, tmp_path / "cases", run=run)

    assert "pull request #7" in str(refused.value) and says in str(refused.value)
    assert not (tmp_path / "cases").exists()


def test_sc4_an_unmerged_pull_request_is_refused_before_it_is_collected(
    tmp_path: Path,
) -> None:
    """SC-4 here: the state is read first; nothing else is fetched."""
    calls, run = _gh(state="OPEN")

    with pytest.raises(EvalCaseError):
        freeze(7, tmp_path, run=run)

    assert len(calls) == 1


def test_sc4_freezing_again_keeps_a_corrected_answer(tmp_path: Path) -> None:
    """SC-4 here: rebuilding a case refreshes its bundle and provenance and
    keeps the expected answer a human gave it (spec R-8) — freeze never
    resets the answer key."""
    _, run = _gh()
    path = freeze(7, tmp_path, run=run, today="2026-11-10")
    first = load_case(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(expected="reject", check="spec-conformance",
                reason="Changes a file the brief put out of bounds.")
    path.write_text(json.dumps(data), encoding="utf-8")

    again = load_case(freeze(7, tmp_path, run=run, today="2026-12-01"))

    assert (again.expected, again.check) == ("reject", "spec-conformance")
    assert again.reason == "Changes a file the brief put out of bounds."
    assert again.bundle == first.bundle and again.provenance.frozen == "2026-12-01"


def test_sc4_freeze_does_not_write_over_a_file_it_cannot_read(tmp_path: Path) -> None:
    """SC-4 here: an existing file that is not a case is left as it is."""
    _, run = _gh()
    (tmp_path / "pr-7.json").write_text("{ not json", encoding="utf-8")

    with pytest.raises(EvalCaseError, match=r"pr-7\.json"):
        freeze(7, tmp_path, run=run)

    assert (tmp_path / "pr-7.json").read_text(encoding="utf-8") == "{ not json"


# ---- SC-4: the command -----------------------------------------------------


def test_sc4_the_freeze_command_writes_the_case_and_says_where(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SC-4: `agent-framework-eval freeze <pr>` writes `<DIR>/pr-<n>.json`
    and exits 0."""
    _, run = _gh()
    monkeypatch.setattr(freeze_module, "run_command", run)
    monkeypatch.setattr(eval_cli, "_today", lambda: "2026-11-10")
    monkeypatch.chdir(tmp_path)  # no agent-framework.toml here: the defaults

    code = eval_cli.main(["freeze", "7", "--cases", "cases"])

    out, _ = capsys.readouterr()
    assert code == 0 and "cases/pr-7.json" in out
    case = load_case(tmp_path / "cases" / "pr-7.json")
    assert case.provenance.frozen == "2026-11-10"
    assert dump_case(case) == (tmp_path / "cases" / "pr-7.json").read_text(encoding="utf-8")


def test_sc4_the_freeze_command_exits_2_when_it_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SC-4: a refusal is exit 2 with the reason on stderr; so is a `gh`
    that fails."""
    _, run = _gh(state="OPEN")
    monkeypatch.setattr(freeze_module, "run_command", run)
    monkeypatch.chdir(tmp_path)

    assert eval_cli.main(["freeze", "7", "--cases", "cases"]) == 2
    assert "is not merged (OPEN)" in capsys.readouterr().err

    def broken(args: Sequence[str]) -> str:
        raise RuntimeError("command failed (1): gh pr view 7\nno such pull request")

    monkeypatch.setattr(freeze_module, "run_command", broken)
    assert eval_cli.main(["freeze", "7", "--cases", "cases"]) == 2
    assert "no such pull request" in capsys.readouterr().err
    assert not (tmp_path / "cases").exists()
