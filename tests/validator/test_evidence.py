"""The validator's evidence (specs/validator-evidence).

Verifies, through the real collector against a faked `gh` runner:
- SC-1: the bundle carries the claimed criteria's text and the task block,
  read at the PR's base commit, with the spec found from the PR body or
  from the changed files.
- SC-2: a spec the PR itself introduces is read at the head, and says so.
- SC-3: an unresolved spec or an undefined criterion REJECTs with no model call.
- SC-4: the judgment request carries the contract inside the data region.
- SC-5: `test_paths` decides which changed files are tests, in any language.
- SC-6: the verdict's JSON form and the core's hermeticity are unchanged.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from agent_framework.errors import ProjectConfigError
from agent_framework.project import ProjectConfig
from agent_framework.providers.base import Request, Response, ToolCall
from agent_framework.providers.registry import ProviderRegistry
from agent_framework.roster import Roster
from agent_framework.validator.bundle import CIEvidence, Contract, EvidenceBundle, TaskRef
from agent_framework.validator.collector import collect_bundle
from agent_framework.validator.gate import validate
from agent_framework.validator.judgment import build_request
from agent_framework.validator.verdict import Pass, Reject, verdict_from_json, verdict_to_json

_SPEC = """# Spec: Widget

## Success criteria

- **SC-1** — The widget spins when asked. (R-1)
- **SC-2** — The widget stops within
  one second. (R-2)

## Traceability

| Criterion | Requirement(s) | Verified by (test) |
|---|---|---|
| SC-1 | R-1 | `tests/test_widget.py::test_spins` |
| SC-2 | R-2 | `tests/test_widget.py::test_spins` |
"""
_TASKS = """# Tasks

### [ ] T-3 — Make the widget spin
- **Satisfies:** SC-1, SC-2
- **Brief:** SPIN-BRIEF-SENTINEL

### [ ] T-4 — Something else
- **Satisfies:** SC-9
"""
_PY_TEST = 'def test_spins() -> None:\n    """SC-1, SC-2."""\n    assert True\n'
_JS_TEST = "test('spins', () => { /* SC-1 SC-2 */ expect(1).toBe(1) })\n"


def _view(body: str, files: Sequence[str]) -> dict[str, object]:
    return {
        "number": 7,
        "title": "feat: T-3 make the widget spin (widget)",
        "body": body,
        "baseRefOid": "base111",
        "headRefOid": "head222",
        "files": [{"path": p} for p in files],
        "statusCheckRollup": [{"name": "ci", "status": "COMPLETED", "conclusion": "SUCCESS"}],
    }


def _runner(
    view: dict[str, object], repo_files: dict[tuple[str, str], str]
) -> Callable[[Sequence[str]], str]:
    """A fake `gh`: `repo_files` maps (path, ref) → content; anything else is a 404."""

    def run(args: Sequence[str]) -> str:
        if list(args[:3]) == ["gh", "pr", "view"]:
            return json.dumps(view)
        if list(args[:3]) == ["gh", "pr", "diff"]:
            return "+ the diff"
        if list(args[:2]) == ["gh", "api"]:
            path, ref = args[-1].split("/contents/", 1)[1].split("?ref=")
            if (path, ref) in repo_files:
                return repo_files[(path, ref)]
            raise RuntimeError(f"command failed (1): gh api {path}@{ref}\nHTTP 404")
        raise AssertionError(f"unexpected command: {args}")

    return run


_BODY = "Implements **T-3** from `specs/widget/tasks.md`.\n\nSatisfies: SC-1, SC-2\n"
_AT_BASE = {
    ("specs/widget/spec.md", "base111"): _SPEC,
    # The PR's head: where the gate reads the Traceability table from
    # (specs/citation-from-traceability).
    ("specs/widget/spec.md", "head222"): _SPEC,
    ("specs/widget/tasks.md", "base111"): _TASKS,
    ("tests/test_widget.py", "head222"): _PY_TEST,
}


class _Judge:
    """A validator-role provider that finds no defect and counts its calls."""

    def __init__(self) -> None:
        self.calls: list[Request] = []

    async def invoke(self, request: Request, *, model: str) -> Response:
        self.calls.append(request)
        return Response(
            text="",
            tool_calls=(ToolCall("return_verdict", {"defect_found": False, "findings": []}),),
        )


def _wire() -> tuple[_Judge, ProviderRegistry, Roster]:
    judge, reg = _Judge(), ProviderRegistry()
    reg.register("fake", judge)
    roster = Roster.from_dict({"roles": {"validator": {"provider": "fake", "model": "j"}}})
    return judge, reg, roster


def test_sc1_bundle_carries_criterion_text_and_task_block_from_the_base_commit() -> None:
    """SC-1: the spec named in the PR body, read as it stood before the PR."""
    head_spec = _SPEC.replace("spins when asked", "REWORDED-IN-THE-PR")
    files = dict(_AT_BASE) | {("specs/widget/spec.md", "head222"): head_spec}
    run = _runner(_view(_BODY, ["src/widget.py", "tests/test_widget.py"]), files)

    contract = collect_bundle(7, run=run).contract

    assert contract is not None and contract.spec_slug == "widget"
    assert (contract.read_from, contract.ref) == ("base", "base111")
    assert "The widget spins when asked." in contract.criterion_texts["SC-1"]
    assert "one second" in contract.criterion_texts["SC-2"]  # multi-line criterion, whole
    assert "REWORDED-IN-THE-PR" not in contract.criterion_texts["SC-1"]
    assert contract.task_block is not None
    assert "SPIN-BRIEF-SENTINEL" in contract.task_block
    assert "T-4" not in contract.task_block  # only the named task's block


def test_sc1_spec_is_found_from_the_changed_files_when_the_body_names_none() -> None:
    """SC-1: exactly one spec directory among the changed files resolves it."""
    run = _runner(
        _view("T-3.\n\nSatisfies: SC-1, SC-2\n", ["specs/widget/spec.md", "tests/test_widget.py"]),
        _AT_BASE,
    )

    contract = collect_bundle(7, run=run).contract

    assert contract is not None and contract.spec_slug == "widget"
    assert set(contract.criterion_texts) == {"SC-1", "SC-2"}


def test_sc1_two_changed_spec_directories_and_none_named_resolve_to_neither() -> None:
    """SC-1 says *exactly one* spec directory among the changed files: with
    two, the collector picks neither, and the contract says why."""
    run = _runner(
        _view(
            "T-3.\n\nSatisfies: SC-1, SC-2\n",
            ["specs/widget/spec.md", "specs/zebra/spec.md", "tests/test_widget.py"],
        ),
        _AT_BASE,
    )

    contract = collect_bundle(7, run=run).contract

    assert contract is not None and contract.spec_slug is None
    assert "more than one spec: widget, zebra" in contract.problem


def test_sc2_a_spec_the_pr_introduces_is_read_at_the_head_and_says_so() -> None:
    """SC-2: no spec file at the base → the head's text, recorded as such."""
    files = {
        ("specs/widget/spec.md", "head222"): _SPEC,
        ("tests/test_widget.py", "head222"): _PY_TEST,
    }
    run = _runner(_view(_BODY, ["specs/widget/spec.md", "tests/test_widget.py"]), files)

    contract = collect_bundle(7, run=run).contract

    assert contract is not None and contract.spec_slug == "widget"
    assert (contract.read_from, contract.ref) == ("head", "head222")
    assert "The widget spins when asked." in contract.criterion_texts["SC-1"]
    assert contract.task_block is None  # no tasks.md anywhere


@pytest.mark.parametrize(
    ("body", "files", "check", "names"),
    [
        # No spec named in the body, none among the changed files.
        ("T-3.\n\nSatisfies: SC-1\n", ["src/widget.py", "tests/test_widget.py"],
         "spec-resolution", "SC-1"),
        # Two spec directories changed and none named: ambiguous, so unresolved.
        # The readable spec sorts first, so picking the first would resolve it.
        ("T-3.\n\nSatisfies: SC-1\n",
         ["specs/widget/spec.md", "specs/zebra/spec.md", "tests/test_widget.py"],
         "spec-resolution", "SC-1"),
        # A resolved spec that does not define a claimed id.
        ("From `specs/widget/tasks.md`.\n\nSatisfies: SC-1, SC-7\n",
         ["tests/test_widget.py"], "criterion-defined", "SC-7"),
    ],
)
async def test_sc3_unresolved_spec_or_undefined_criterion_rejects_without_a_model_call(
    body: str, files: list[str], check: str, names: str
) -> None:
    """SC-3: REJECT at the deterministic stage, naming the gap; zero model calls."""
    judge, reg, roster = _wire()
    cited = {("tests/test_widget.py", "head222"): _PY_TEST.replace("SC-2", "SC-2, SC-7")}
    bundle = collect_bundle(7, run=_runner(_view(body, files), _AT_BASE | cited))

    verdict = await validate(bundle, roster, registry=reg)

    assert isinstance(verdict, Reject)
    [finding] = [f for f in verdict.findings if f.check == check]
    assert names in finding.finding or names in finding.evidence
    assert judge.calls == []


async def test_sc4_judgment_request_carries_the_contract_inside_the_data_region() -> None:
    """SC-4: criterion texts, the task block and the commit they were read from."""
    judge, reg, roster = _wire()
    run = _runner(_view(_BODY, ["src/widget.py", "tests/test_widget.py"]), _AT_BASE)

    verdict = await validate(collect_bundle(7, run=run), roster, registry=reg)

    assert isinstance(verdict, Pass)
    [request] = judge.calls
    data = request.prompt.split("===== BEGIN DATA =====")[1].split("===== END DATA =====")[0]
    assert "The widget spins when asked." in data
    assert "one second" in data
    assert "SPIN-BRIEF-SENTINEL" in data
    assert "specs/widget/" in data and "base111" in data and "base" in data


async def test_sc5_test_paths_collects_a_non_python_test_and_the_gate_cites_it() -> None:
    """SC-5: a project in another language is gated through the real collector."""
    _, reg, roster = _wire()
    project = ProjectConfig(
        test_paths=("src/**/*.test.js",), test_pattern=r"^test\('(\w+)'",
    )
    files = dict(_AT_BASE) | {
        ("src/widget/spin.test.js", "head222"): _JS_TEST,
        ("specs/widget/spec.md", "head222"): _SPEC.replace(
            "tests/test_widget.py::test_spins", "src/widget/spin.test.js::spins"
        ),
    }
    run = _runner(_view(_BODY, ["src/widget/spin.js", "src/widget/spin.test.js"]), files)

    bundle = collect_bundle(7, run=run, test_paths=project.test_paths)
    verdict = await validate(bundle, roster, registry=reg, project=project)

    assert set(bundle.tests) == {"src/widget/spin.test.js"}
    assert isinstance(verdict, Pass)
    assert {c.test for c in verdict.citations} == {"src/widget/spin.test.js::spins"}


def test_sc5_without_test_paths_the_files_collected_are_exactly_todays() -> None:
    """SC-5: the default is `tests/`…`.py`, at any depth, and nothing else."""
    changed = ["tests/test_a.py", "tests/deep/er/test_b.py", "tests/data.json",
               "src/tests/test_c.py", "src/x.test.js", "testsuite/test_d.py"]
    files = dict(_AT_BASE) | {(p, "head222"): _PY_TEST for p in changed}
    # The table names one of the changed files, so this stays a test of which
    # *changed* files are selected (a file the table names is fetched regardless).
    files[("specs/widget/spec.md", "head222")] = _SPEC.replace(
        "tests/test_widget.py", "tests/test_a.py"
    )

    bundle = collect_bundle(7, run=_runner(_view(_BODY, changed), files))

    assert set(bundle.tests) == {"tests/test_a.py", "tests/deep/er/test_b.py"}
    assert ProjectConfig().test_paths == ("tests/**/*.py",)


def test_sc5_malformed_test_paths_fails_loudly_naming_the_field(
    tmp_path: Path,
) -> None:
    """SC-5: a string where a list belongs, and an empty pattern, are both errors."""
    from agent_framework.project import load_project_config

    root = tmp_path
    (root / "agent-framework.toml").write_text('[project]\ntest_paths = "tests"\n')
    with pytest.raises(ProjectConfigError, match="test_paths"):
        load_project_config(root)
    with pytest.raises(ProjectConfigError, match="test_paths"):
        ProjectConfig(test_paths=("tests/**/*.py", ""))


async def test_sc6_verdict_json_shape_is_unchanged_and_the_core_needs_no_seam() -> None:
    """SC-6: a hand-built bundle (no runner, no network) → the same JSON keys."""
    _, reg, roster = _wire()
    bundle = EvidenceBundle(
        task=TaskRef(task_id="T-3", criteria=("SC-1",)),
        diff="+ x",
        tests={"tests/test_widget.py": _PY_TEST},
        ci=CIEvidence(green=True, summary="ci: SUCCESS"),
        contract=Contract(
            spec_slug="widget", criterion_texts={"SC-1": "**SC-1** — spins"},
            read_from="base", ref="base111",
            cited_tests={"SC-1": ("tests/test_widget.py::test_spins",)},
        ),
    )

    verdict = await validate(bundle, roster, registry=reg)

    text = verdict_to_json(verdict)
    assert verdict_from_json(text) == verdict
    assert set(json.loads(text)) == {"verdict", "task_id", "citations", "ci"}
    assert "===== BEGIN DATA =====" in build_request(bundle).prompt
