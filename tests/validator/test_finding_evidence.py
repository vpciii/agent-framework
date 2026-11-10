"""A finding's evidence is checked against what was sent (specs/finding-evidence).

Each test's docstring names the one criterion it verifies.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from agent_framework.errors import JudgmentFormatError, NoVerdictError
from agent_framework.providers.base import Request, Response, ToolCall
from agent_framework.providers.registry import ProviderRegistry, register_provider
from agent_framework.roster import Roster
from agent_framework.validator import __main__ as gate_cli
from agent_framework.validator.bundle import CIEvidence, Contract, EvidenceBundle, TaskRef
from agent_framework.validator.gate import validate
from agent_framework.validator.judgment import (
    CHECK_NAMES,
    VERDICT_TOOL,
    SentData,
    build_request,
    judge,
)
from agent_framework.validator.verdict import Citation, Finding, Pass, Reject

# Two hunks of the merged PR #77, verbatim: the diff the model was sent on
# 2026-11-09. In the second, removed lines sit among the added ones.
PR77_DIFF = """\
diff --git a/src/agent_framework/validator/checks.py b/src/agent_framework/validator/checks.py
@@ -32,6 +41,63 @@ def _citing_test(
+    Call only for a bundle whose contract resolved a spec.
+
+    contract = bundle.contract
+    assert contract is not None and contract.spec_slug is not None
+    where = f"specs/{contract.spec_slug}/spec.md, Traceability table at the PR's head"
diff --git a/src/agent_framework/validator/collector.py b/src/agent_framework/validator/collector.py
@@ -182,21 +195,32 @@ def collect_bundle(
-        path = str(f.get("path", ""))
-        if path_matches(path, test_paths):
-            tests[path] = _file_at_ref(path, head, repo, run)
+    changed = [str(f.get("path", "")) for f in files]

     task = TaskRef(task_id=task_id, criteria=criteria, is_fix=is_fix)
     # A PR that claims nothing is rejected before any contract matters.
     contract = (
-        _contract(task, body, [str(f.get("path", "")) for f in files],
-                  str(view.get("baseRefOid", "")), head, repo, run)
+        _contract(task, body, changed, str(view.get("baseRefOid", "")), head, repo, run)
         if criteria
         else Contract(spec_slug=None, problem="the PR claims no success criteria")
     )
"""

# The three excerpts that judgment quoted. The first and third are real.
REAL_COLLECTOR = """\
contract = (
    _contract(task, body, changed, str(view.get("baseRefOid", "")), head, repo, run)
    if criteria
    else Contract(spec_slug=None, problem="the PR claims no success criteria")
)"""
INVENTED_RUN_CHECKS = """\
if bundle.contract is not None:
    if bundle.contract.problem:
        findings.append(...)
    else:
        ...
    findings.extend(table_citations(bundle, pattern)[1])"""
REAL_TABLE_CITATIONS = """\
contract = bundle.contract
assert contract is not None and contract.spec_slug is not None"""

TEST_SOURCE = 'def test_a() -> None:\n    """SC-1."""\n    assert collect() == expected\n'


class _Fake:
    def __init__(self, response: Response) -> None:
        self.response = response
        self.requests: list[Request] = []

    async def invoke(self, request: Request, *, model: str) -> Response:
        self.requests.append(request)
        return self.response


def _answer(defect_found: bool, *findings: dict[str, Any]) -> Response:
    arguments = {"defect_found": defect_found, "findings": list(findings)}
    return Response(text="", tool_calls=(ToolCall(VERDICT_TOOL.name, arguments),))


def _wire(response: Response) -> tuple[ProviderRegistry, Roster]:
    registry = ProviderRegistry()
    registry.register("fake", _Fake(response))
    roster = Roster.from_dict({"roles": {"validator": {"provider": "fake", "model": "judge-9"}}})
    return registry, roster


def _bundle(contract: Contract | None = None) -> EvidenceBundle:
    return EvidenceBundle(
        task=TaskRef(task_id="PR-77", criteria=("SC-1",)),
        diff=PR77_DIFF,
        tests={"tests/test_x.py": TEST_SOURCE},
        ci=CIEvidence(green=True, summary="ci: SUCCESS"),
        contract=contract,
    )


def _finding(*quotes: str, check: str = "edge-case", finding: str = "it crashes") -> dict[str, Any]:
    return {"check": check, "finding": finding, "evidence": "see the quotes",
            "quotes": list(quotes)}


# The 2026-11-09 finding: two real quotes and the invented one it rests on.
THE_FALSE_FINDING = _finding(
    REAL_COLLECTOR, INVENTED_RUN_CHECKS, REAL_TABLE_CITATIONS,
    finding="run_checks calls table_citations when no spec was resolved",
)
A_SUPPORTED_FINDING = _finding(
    REAL_TABLE_CITATIONS, check="test-honesty", finding="an assert stands in for a check",
)


# ---- SC-1: the schema asks for quotes and fixes the check names ------------


def test_sc1_the_schema_requires_quotes_and_fixes_the_check_names() -> None:
    """SC-1: per finding, a non-empty list of quotes is required and `check`
    is one of the four names — in a schema that is still closed."""
    item = VERDICT_TOOL.parameters["properties"]["findings"]["items"]

    assert "quotes" in item["required"]
    quotes = item["properties"]["quotes"]
    assert quotes["type"] == "array" and quotes["items"] == {"type": "string"}
    assert quotes["minItems"] == 1
    assert item["properties"]["check"]["enum"] == list(CHECK_NAMES) == [
        "test-honesty", "spec-conformance", "criteria-integrity", "edge-case",
    ]
    assert item["additionalProperties"] is False


@pytest.mark.parametrize(
    "broken",
    [
        {"check": "edge-case", "finding": "it crashes", "evidence": "trust me"},
        {"check": "edge-case", "finding": "it crashes", "evidence": "trust me", "quotes": []},
        {"check": "edge-case", "finding": "it crashes", "evidence": "trust me",
         "quotes": "contract = bundle.contract"},
        {"check": "edge-case", "finding": "it crashes", "evidence": "trust me", "quotes": [7]},
    ],
    ids=["no quotes field", "empty list", "not a list", "not a string"],
)
async def test_sc1_a_finding_without_quotes_is_malformed(broken: dict[str, Any]) -> None:
    """SC-1: the existing malformed-judgment error — and not "could not
    judge for want of evidence", which is a different thing."""
    registry, roster = _wire(_answer(True, broken))

    with pytest.raises(JudgmentFormatError, match="quotes") as raised:
        await judge(_bundle(), roster, registry=registry)

    assert not isinstance(raised.value, NoVerdictError)


async def test_sc1_a_check_outside_the_four_names_is_malformed() -> None:
    """SC-1: what the live run did — a checklist sentence in `check` — is
    refused by the parser too, for a provider that does not enforce the schema."""
    wordy = _finding(REAL_TABLE_CITATIONS, check="4. Construct one plausible unstated edge case")
    registry, roster = _wire(_answer(True, wordy))

    with pytest.raises(JudgmentFormatError, match="check"):
        await judge(_bundle(), roster, registry=registry)


# ---- SC-2: quote matching --------------------------------------------------

CONTRACT = Contract(
    spec_slug="citation-from-traceability",
    criterion_texts={"SC-1": "- **SC-1** — A citation comes from the Traceability table."},
    task_block="### T-1 — Read citations from the table",
    cited_tests={"SC-1": ("tests/test_x.py::test_a",)},
    ref="84a707e",
)


def _sent(contract: Contract | None = None) -> SentData:
    return SentData.of(build_request(_bundle(contract)))


@pytest.mark.parametrize(
    "quote",
    [
        REAL_COLLECTOR,
        (
            '_contract(task, body, [str(f.get("path", "")) for f in files],\n'
            '          str(view.get("baseRefOid", "")), head, repo, run)\nif criteria'
        ),
        'path = str(f.get("path", ""))\nif path_matches(path, test_paths):',
        "assert collect() == expected",
        "A citation comes from the Traceability table.",
        "### T-1 — Read citations from the table",
        "contract = bundle.contract assert contract is not None",
        "\t\tcontract   =   bundle.contract\n\n\nassert contract is not None",
        "+    contract = bundle.contract\n+    assert contract is not None",
    ],
    ids=[
        "added code, removed lines interleaved", "removed code spanning unchanged",
        "removed code", "a test file", "the contract's criterion", "the task block",
        "line breaks dropped", "indentation and spacing changed", "copied with diff markers",
    ],
)
def test_sc2_an_excerpt_of_what_was_sent_is_found(quote: str) -> None:
    """SC-2: found in the diff read as its new side or its old side, in
    the tests and in the contract, whatever the whitespace."""
    assert _sent(CONTRACT).problem_with(quote) is None


@pytest.mark.parametrize(
    "quote",
    [
        INVENTED_RUN_CHECKS,
        "findings.extend(table_citations(bundle, pattern)[1])",
        # The two sides never mix: this line pair exists in neither file.
        (
            '_contract(task, body, [str(f.get("path", "")) for f in files],\n'
            '_contract(task, body, changed, str(view.get("baseRefOid", "")), head, repo, run)'
        ),
        # The instructions are not data: only the data region is searched.
        "Judge with a refutation mindset",
    ],
    ids=["the invented excerpt", "one invented line", "old and new side mixed", "the checklist"],
)
def test_sc2_an_excerpt_that_was_not_sent_is_not_found(quote: str) -> None:
    """SC-2: an excerpt that appears nowhere in the data is not found."""
    assert _sent(CONTRACT).problem_with(quote) == "not found"


@pytest.mark.parametrize("quote", ["if criteria", "contract", ")", "   \n  "])
def test_sc2_an_excerpt_below_the_minimum_length_is_not_accepted(quote: str) -> None:
    """SC-2: too short to be evidence, even though it is in the data."""
    assert _sent().problem_with(quote) == "too short"


def test_sc2_the_data_searched_is_exactly_the_data_sent() -> None:
    """SC-2: the search is over the request's own data region."""
    request = build_request(_bundle())

    sent = SentData.of(request)

    assert f"===== BEGIN DATA =====\n{sent.as_written}\n===== END DATA =====" in request.prompt
    assert PR77_DIFF in sent.as_written and TEST_SOURCE in sent.as_written


# ---- SC-3: the 2026-11-09 case --------------------------------------------


async def test_sc3_the_false_finding_is_unsupported_and_there_is_no_verdict() -> None:
    """SC-3: two real quotes and one invented one — the judgment that
    carries only that finding is "could not judge", reason unsupported-finding."""
    registry, roster = _wire(_answer(True, THE_FALSE_FINDING))

    with pytest.raises(NoVerdictError) as raised:
        await judge(_bundle(), roster, registry=registry)

    assert raised.value.reason == "unsupported-finding"
    assert "PR-77" in str(raised.value)


def _run_cli(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str, response: Response
) -> int:
    """The gate's real CLI over a canned bundle and a canned model answer."""
    (tmp_path / "agent-framework.toml").write_text(
        f'[roles]\nvalidator = {{ provider = "{name}", model = "judge-9" }}\n', encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(gate_cli, "collect_bundle", lambda *a, **k: _bundle())
    register_provider(name, _Fake(response))
    return gate_cli.main(["77"])


def test_sc3_the_cli_reports_could_not_judge_and_exits_three(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """SC-3: from the command line it is exit 3 with the reason — not the
    REJECT (exit 1) it was on 2026-11-09, and not a PASS."""
    code = _run_cli(monkeypatch, tmp_path, "fake-false-finding", _answer(True, THE_FALSE_FINDING))

    out, err = capsys.readouterr()
    assert code == 3
    printed = json.loads(out)
    assert printed["verdict"] == "none" and printed["reason"] == "unsupported-finding"
    assert "Traceback" not in err


# ---- SC-4: a REJECT carries only supported findings ------------------------


async def test_sc4_a_reject_carries_only_the_supported_finding() -> None:
    """SC-4: one supported and one unsupported finding — REJECT, with one."""
    registry, roster = _wire(_answer(True, THE_FALSE_FINDING, A_SUPPORTED_FINDING))

    verdict = await validate(_bundle(), roster, registry=registry)

    assert verdict == Reject(
        task_id="PR-77",
        findings=(Finding(check="test-honesty", finding="an assert stands in for a check",
                          evidence="see the quotes"),),
    )


async def test_sc4_a_finding_with_one_short_quote_is_unsupported() -> None:
    """SC-4 here: every quote must count — a real quote beside one too
    short to be evidence does not carry the finding."""
    padded = _finding(REAL_TABLE_CITATIONS, "if criteria")
    registry, roster = _wire(_answer(True, padded))

    with pytest.raises(NoVerdictError, match="unsupported-finding"):
        await judge(_bundle(), roster, registry=registry)


# ---- SC-5: what was dropped is logged --------------------------------------


async def test_sc5_an_unsupported_finding_is_logged_with_the_quote_not_found(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SC-5: the dropped finding and the quote that was not found, in the
    log — whether or not a REJECT still stands on the other findings."""
    registry, roster = _wire(_answer(True, THE_FALSE_FINDING, A_SUPPORTED_FINDING))

    with caplog.at_level(logging.INFO, logger="agent_framework.validator"):
        await validate(_bundle(), roster, registry=registry)

    [line] = [r.getMessage() for r in caplog.records if "unsupported finding" in r.getMessage()]
    assert "PR-77" in line and "edge-case" in line
    assert "run_checks calls table_citations when no spec was resolved" in line
    assert "not found" in line and "if bundle.contract.problem:" in line
    # The quotes that were found are not reported as missing.
    assert "the PR claims no success criteria" not in line


async def test_sc5_it_is_logged_before_could_not_judge_is_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SC-5 here: also when no finding is left and there is no verdict."""
    short = _finding("if criteria", finding="criteria are not checked")
    registry, roster = _wire(_answer(True, short))

    with caplog.at_level(logging.INFO, logger="agent_framework.validator"), \
            pytest.raises(NoVerdictError):
        await judge(_bundle(), roster, registry=registry)

    [line] = [r.getMessage() for r in caplog.records if "unsupported finding" in r.getMessage()]
    assert "criteria are not checked" in line and "too short" in line and "if criteria" in line


# ---- SC-6: the model is told the rule --------------------------------------


def test_sc6_the_instructions_state_the_quote_rule() -> None:
    """SC-6: quotes are checked; only part of each changed file is shown;
    unseen code must not be quoted — said in the instructions, not the data."""
    prompt = build_request(_bundle()).prompt
    instructions = " ".join(prompt.split("===== BEGIN DATA =====")[0].split())

    assert (
        "Every quote in a finding is checked against that data by code, and a "
        "finding with a quote that is not found there, word for word, is discarded."
    ) in instructions
    assert (
        "The diff shows only part of each changed file, so do not quote or "
        "describe code you were not shown"
    ) in instructions
    # ...and the model is told what to do instead of guessing.
    assert "say so in the finding instead of guessing at that code" in instructions


# ---- SC-7: nothing else changes --------------------------------------------


async def test_sc7_a_no_defect_judgment_is_the_same_pass() -> None:
    """SC-7: no defect — the PASS, its citation and its CI line, as before."""
    registry, roster = _wire(_answer(False))

    verdict = await validate(_bundle(), roster, registry=registry)

    assert verdict == Pass(
        task_id="PR-77", citations=(Citation("SC-1", "tests/test_x.py::test_a"),),
        ci="ci: SUCCESS",
    )


def test_sc7_pass_and_reject_keep_their_codes_and_a_reject_its_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """SC-7: PASS exits 0, REJECT exits 1, and a REJECT's JSON has the keys
    it had — the quotes admit a finding, they are not part of the verdict."""
    assert _run_cli(monkeypatch, tmp_path, "fake-clean", _answer(False)) == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "pass"

    code = _run_cli(monkeypatch, tmp_path, "fake-defect", _answer(True, A_SUPPORTED_FINDING))

    printed = json.loads(capsys.readouterr().out)
    assert code == 1
    assert set(printed) == {"verdict", "task_id", "findings"}
    [finding] = printed["findings"]
    assert set(finding) == {"check", "finding", "evidence"}
