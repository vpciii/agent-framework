"""Freezing a merged task pull request into a worker eval case
(specs/worker-eval SC-3). GitHub is a fake seam; the repository is real,
in `tmp_path`. Nothing here reaches the network."""

from __future__ import annotations

import functools
import json
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from agent_framework.errors import EvalCaseError
from agent_framework.evals import __main__ as cli
from agent_framework.evals.worker.case import load_case
from agent_framework.evals.worker.freeze import FROZEN_BY, freeze_worker_case

TASKS = "# Tasks\n\n### [ ] T-1 — Do the thing\n- **Satisfies:** SC-1\n"
SPEC = (
    "# Spec\n\n## Requirements\n\n- **R-1 (MUST)** It does the thing.\n\n"
    "## Success criteria\n\n- **SC-1** — The thing is done. (R-1)\n"
    "- **SC-2** — Another thing. (R-1)\n"
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _commit(repo: Path, files: dict[str, str], message: str) -> str:
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def history(tmp_path: Path) -> dict[str, str | Path]:
    """main: the spec; a task branch adds code and tests; main moves on;
    the branch is merged with a merge commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "t")
    start = _commit(
        repo, {"specs/demo/tasks.md": TASKS, "specs/demo/spec.md": SPEC}, "spec"
    )
    _git(repo, "checkout", "-q", "-b", "task")
    head = _commit(
        repo,
        {
            "src/thing.py": "X = 1\n",
            "tests/test_thing.py": 'def test_sc1_done() -> None:\n    """SC-1"""\n',
            "tests/test_other.py": "def test_unrelated() -> None:\n    pass\n",
            "tests/test_sc10.py": 'def test_x() -> None:\n    """SC-10"""\n',
        },
        "feat: T-1",
    )
    _git(repo, "checkout", "-q", "main")
    _commit(repo, {"README.md": "later\n"}, "unrelated work on main")
    _git(repo, "merge", "-q", "--no-ff", "-m", "Merge pull request #7", "task")
    merge = _git(repo, "rev-parse", "HEAD")
    return {"repo": repo, "start": start, "head": head, "merge": merge}


def _gh(view: dict[str, object]) -> tuple[list[list[str]], functools.partial[str]]:
    calls: list[list[str]] = []

    def fake(args: Sequence[str], view: dict[str, object]) -> str:
        calls.append(list(args))
        assert args[:3] == ["gh", "pr", "view"]
        return json.dumps(view)

    return calls, functools.partial(fake, view=view)


def _view(history: dict[str, str | Path], **over: object) -> dict[str, object]:
    view: dict[str, object] = {
        "state": "MERGED",
        "title": "feat: T-1 Do the thing (demo)",
        "body": "Implements **T-1** from `specs/demo/tasks.md`.\n\nSatisfies: SC-1\n",
        "headRefOid": history["head"],
        "mergeCommit": {"oid": history["merge"]},
        "url": "https://github.com/owner/name/pull/7",
    }
    view.update(over)
    return view


def test_sc3_a_frozen_case_loads_with_its_start_head_and_reference_tests(
    tmp_path: Path, history: dict[str, str | Path]
) -> None:
    """SC-3: a merged task pull request becomes a case T-2's loader reads, with
    the merge base as start, the head, and only the test files citing SC-1."""
    calls, gh = _gh(_view(history))
    cases = tmp_path / "cases"
    path = freeze_worker_case(
        7, cases, gh=gh, checkout=Path(history["repo"]), today="2026-11-17"
    )
    assert path == cases / "pr-7.json"
    case = load_case(path)
    assert (case.task.spec, case.task.task) == ("demo", "T-1")
    assert case.reference.repo == "owner/name"
    assert case.reference.pr == 7
    assert case.reference.start == history["start"]
    assert case.reference.head == history["head"]
    assert case.reference_tests == ("tests/test_thing.py",)
    assert (case.provenance.frozen, case.provenance.by) == ("2026-11-17", FROZEN_BY)
    assert len(calls) == 1  # GitHub is read once


@pytest.mark.parametrize(
    ("over", "reason"),
    [
        ({"state": "OPEN", "mergeCommit": None}, "is not merged (OPEN)"),
        ({"state": "CLOSED", "mergeCommit": None}, "is not merged (CLOSED)"),
        ({"title": "feat: a thing", "body": "Satisfies: SC-1\n"}, "names no task"),
        ({"title": "feat: T-9 a thing (demo)"}, "task T-9 is not in specs/demo/tasks.md"),
    ],
)
def test_sc3_a_refused_pull_request_writes_nothing_and_says_why(
    tmp_path: Path, history: dict[str, str | Path], over: dict[str, object], reason: str
) -> None:
    """SC-3: not merged, no task named, or a task not in tasks.md at its start
    commit — nothing is written and the error names the reason."""
    _, gh = _gh(_view(history, **over))
    cases = tmp_path / "cases"
    with pytest.raises(EvalCaseError, match=reason.replace("(", r"\(").replace(")", r"\)")):
        freeze_worker_case(7, cases, gh=gh, checkout=Path(history["repo"]))
    assert not cases.exists()


@pytest.mark.parametrize(
    ("over", "reason"),
    [
        ({"state": "OPEN", "mergeCommit": None}, "is not merged"),
        ({"title": "chore: tidy", "body": "No task here.\n"}, "names no task"),
        ({"title": "feat: T-9 (demo)"}, "is not in specs/demo/tasks.md at its start commit"),
    ],
)
def test_sc3_the_worker_freeze_command_refuses_with_exit_2_writing_nothing(
    tmp_path: Path,
    history: dict[str, str | Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    over: dict[str, object],
    reason: str,
) -> None:
    """SC-3: `agent-framework-eval worker freeze` exits 2 for each refusal,
    naming it, and writes no file; a merged task pull request exits 0."""
    _, gh = _gh(_view(history, **over))
    monkeypatch.setattr(
        cli, "freeze_worker_case",
        functools.partial(freeze_worker_case, gh=gh, checkout=Path(history["repo"])),
    )
    cases = tmp_path / "cases"
    assert cli.main(["worker", "freeze", "7", "--cases", str(cases)]) == 2
    assert reason in capsys.readouterr().err
    assert not cases.exists()

    _, gh = _gh(_view(history))
    monkeypatch.setattr(
        cli, "freeze_worker_case",
        functools.partial(freeze_worker_case, gh=gh, checkout=Path(history["repo"])),
    )
    assert cli.main(["worker", "freeze", "7", "--cases", str(cases)]) == 0
    assert load_case(cases / "pr-7.json").reference.head == history["head"]


def test_sc3_a_pull_request_with_no_test_citing_its_criteria_is_refused(
    tmp_path: Path, history: dict[str, str | Path]
) -> None:
    """SC-3: with no reference test there is no case to write."""
    repo = Path(history["repo"])
    _git(repo, "checkout", "-q", "-b", "untested", str(history["start"]))
    head = _commit(repo, {"src/more.py": "Y = 2\n"}, "feat: T-1 untested")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "-q", "--no-ff", "-m", "Merge", "untested")
    merge = _git(repo, "rev-parse", "HEAD")
    _, gh = _gh(_view(history, headRefOid=head, mergeCommit={"oid": merge}))
    cases = tmp_path / "cases"
    with pytest.raises(EvalCaseError, match="changed no test file that cites SC-1"):
        freeze_worker_case(7, cases, gh=gh, checkout=repo)
    assert not cases.exists()
