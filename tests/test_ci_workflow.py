"""The CI workflow's trust boundary.

Regression (found 2026-11-09): the advisory `validator` job checked out the
pull request's head and ran the validator from it with `GEMINI_API_KEY` in
its environment — so a PR that changed the validator, a module it imports,
or a locked dependency ran that changed code with the key. A worker
session's commits reach CI exactly this way.

The rule these tests pin: **code from a pull request never runs in a job
that holds a secret.** The `ci` job runs the PR's code and holds none; the
`validator` job holds the key and runs only the default branch's code,
reading the PR as data through the API.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

_WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
_DEFAULT_BRANCH = "${{ github.event.repository.default_branch }}"


def _workflow() -> dict[Any, Any]:
    data = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _steps(job: str) -> list[dict[str, Any]]:
    steps = _workflow()["jobs"][job]["steps"]
    assert isinstance(steps, list)
    return steps


def test_the_job_holding_the_key_runs_only_the_default_branchs_code() -> None:
    """Regression: the validator job checks out the default branch — once —
    and nothing in it refers to the pull request's head."""
    steps = _steps("validator")
    checkouts = [s for s in steps if str(s.get("uses", "")).startswith("actions/checkout@")]

    assert len(checkouts) == 1
    assert checkouts[0].get("with", {}).get("ref") == _DEFAULT_BRANCH
    # The job's token is not left behind in the checkout for later steps.
    assert checkouts[0]["with"].get("persist-credentials") is False

    text = yaml.safe_dump(_workflow()["jobs"]["validator"])
    for head_ref in ("pull_request.head", "github.head_ref", "refs/pull/", "github.sha"):
        assert head_ref not in text, f"the validator job refers to the PR's head: {head_ref}"


def test_the_key_is_given_to_one_step_in_one_job() -> None:
    """Regression: `GEMINI_API_KEY` appears only in the gate step's
    environment — never at job or workflow level, never in the `ci` job."""
    wf = _workflow()
    assert "secrets." not in yaml.safe_dump(wf.get("env", {}))
    for name, job in wf["jobs"].items():
        assert "secrets." not in yaml.safe_dump(job.get("env", {})), name

    holders = [
        (job, step.get("name"))
        for job in wf["jobs"]
        for step in _steps(job)
        if "secrets." in yaml.safe_dump(step.get("env", {}))
    ]
    assert holders == [("validator", "Cite-the-test gate (advisory)")]


def test_the_job_that_runs_pull_request_code_holds_no_secret_and_a_read_only_token() -> None:
    """The `ci` job runs whatever the PR contains: it gets no secret, and the
    workflow's token is read-only whatever the repository's default is."""
    wf = _workflow()
    assert wf["permissions"] == {"contents": "read"}
    assert "permissions" not in wf["jobs"]["ci"]  # inherits the read-only default
    assert "secrets." not in yaml.safe_dump(wf["jobs"]["ci"])
    for step in _steps("ci"):
        if str(step.get("uses", "")).startswith("actions/checkout@"):
            assert step.get("with", {}).get("persist-credentials") is False


def test_no_pull_request_text_is_interpolated_into_a_script() -> None:
    """Script injection: the only expression expanded inside a `run:` script
    is the pull request's number."""
    for job in _workflow()["jobs"]:
        for step in _steps(job):
            for expr in re.findall(r"\$\{\{\s*(.+?)\s*\}\}", str(step.get("run", ""))):
                assert expr == "github.event.pull_request.number", (job, expr)


def test_sc10_no_workflow_runs_the_eval() -> None:
    """SC-10 (specs/validator-eval-set): the eval needs a provider key and
    is run by a human — no job in any workflow invokes it."""
    workflows = sorted(_WORKFLOW.parent.glob("*.yml")) + sorted(_WORKFLOW.parent.glob("*.yaml"))
    assert _WORKFLOW in workflows

    for workflow in workflows:
        text = workflow.read_text(encoding="utf-8")
        assert "agent-framework-eval" not in text, workflow.name
        assert "agent_framework.evals" not in text, workflow.name
