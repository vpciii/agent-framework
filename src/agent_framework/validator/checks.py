"""The deterministic stage: everything machine-checkable, checked as code.

Citations: when the bundle carries a resolved contract (every bundle the
collector builds), each claimed criterion's tests are the ones the spec's
Traceability table names, each confirmed here — the file is in the bundle,
the project's test pattern finds a test of that name, and that test's own
text contains the criterion's id. Scanning test files for the id is only
how a *named* test is confirmed, never how a test is found: ids repeat
across specs, and a mention is not a citation (specs/citation-from-
traceability). A hand-built bundle with no contract keeps the plain scan.

Runs before any model call (ADR 0005 — a failure here rejects for free).
Pure functions over the evidence bundle: criterion→test citation, CI
status, and red→green evidence for fixes. Also derives the per-criterion
citations a PASS must carry — evidence is *found*, never asserted.
"""

from __future__ import annotations

import re

from ..project import DEFAULTS
from .bundle import EvidenceBundle
from .verdict import Citation, Finding

# The default (Python) pattern comes from project config's defaults — the
# target project may declare its own (ADR 0002: Python is the harness's
# language, not the target's).
_DEFAULT_TEST_RE = re.compile(DEFAULTS.test_pattern, re.MULTILINE)


def _citing_test(
    sc_id: str, path: str, source: str, pattern: re.Pattern[str] = _DEFAULT_TEST_RE
) -> str | None:
    """The first test in `source` whose span cites `sc_id`, as path::name."""
    matches = list(pattern.finditer(source))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(source)
        if re.search(rf"\b{re.escape(sc_id)}\b", source[m.start() : end]):
            return f"{path}::{m.group(1)}"
    return None


def _test_spans(source: str, pattern: re.Pattern[str]) -> dict[str, str]:
    """Each test the pattern finds in `source`: its name → its own text (up
    to the start of the next test). The first test of a name wins."""
    matches = list(pattern.finditer(source))
    spans: dict[str, str] = {}
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(source)
        spans.setdefault(m.group(1), source[m.start() : end])
    return spans


def table_citations(
    bundle: EvidenceBundle, pattern: re.Pattern[str] = _DEFAULT_TEST_RE
) -> tuple[tuple[Citation, ...], tuple[Finding, ...]]:
    """Citations from the spec's Traceability table, each confirmed; and a
    finding for every claimed criterion whose entry is missing or unconfirmed.

    Call only for a bundle whose contract resolved a spec.
    """
    contract = bundle.contract
    assert contract is not None and contract.spec_slug is not None
    where = f"specs/{contract.spec_slug}/spec.md, Traceability table at the PR's head"
    citations: list[Citation] = []
    findings: list[Finding] = []

    def missing(sc: str, what: str, evidence: str) -> None:
        findings.append(Finding(check="criterion-citation", finding=f"{sc}: {what}",
                                evidence=evidence))

    for sc in bundle.task.criteria:
        refs = contract.cited_tests.get(sc, ())
        if not refs:
            missing(sc, "the spec's Traceability table names no test for it",
                    f"{where}: no row, an empty cell, or *(pending)*")
            continue
        for ref in refs:
            path, _, name = ref.partition("::")
            name = name.rsplit("::", 1)[-1].strip()
            path = path.strip()
            if not name:
                missing(sc, f"`{ref}` names a file but no test", where)
            elif path not in bundle.tests:
                missing(sc, f"cited test file {path} does not exist at the PR's head",
                        f"{where} names `{ref}`")
            else:
                span = _test_spans(bundle.tests[path], pattern).get(name)
                if span is None:
                    missing(sc, f"no test named {name} in {path}",
                            f"{where} names `{ref}`; searched with the project's test pattern")
                elif not re.search(rf"\b{re.escape(sc)}\b", span):
                    missing(sc, f"cited test {ref} does not cite {sc}",
                            f"the text of {name} does not contain {sc}")
                else:
                    citations.append(Citation(sc, f"{path}::{name}"))
    return tuple(citations), tuple(findings)


def find_citations(
    bundle: EvidenceBundle, pattern: re.Pattern[str] = _DEFAULT_TEST_RE
) -> dict[str, str]:
    """Map each claimed criterion to a citing test (`path::test_name`), where one exists.

    Citation is at *test* level per the project's pattern: an id mentioned
    only in a module docstring names no test and does not count.
    """
    citations: dict[str, str] = {}
    for sc in bundle.task.criteria:
        for path in sorted(bundle.tests):
            cited = _citing_test(sc, path, bundle.tests[path], pattern)
            if cited is not None:
                citations[sc] = cited
                break
    return citations


def run_checks(
    bundle: EvidenceBundle, pattern: re.Pattern[str] = _DEFAULT_TEST_RE
) -> tuple[Finding, ...]:
    """All deterministic findings for the bundle; empty means the model may judge."""
    findings: list[Finding] = []

    if not bundle.task.criteria:
        # A task PR that claims nothing has nothing to verify — and a PASS
        # with no citations is unconstructible by design. Reject for free
        # rather than crash after a wasted judgment call.
        return (
            Finding(
                check="satisfies-declaration",
                finding="PR claims no success criteria",
                evidence="no SC- ids claimed in the PR title or body",
            ),
        )

    contract = bundle.contract
    if contract is not None and contract.spec_slug is None:
        # Criterion ids are only unique within a spec: a claim tied to no
        # spec cannot be judged against anything (validator-evidence R-4).
        findings.append(
            Finding(
                check="spec-resolution",
                finding=(
                    f"claimed {', '.join(bundle.task.criteria)} cannot be tied to a spec"
                ),
                evidence=contract.problem,
            )
        )
    elif contract is not None:
        for sc in bundle.task.criteria:
            if sc not in contract.criterion_texts:
                findings.append(
                    Finding(
                        check="criterion-defined",
                        finding=f"{sc} is not defined in specs/{contract.spec_slug}/spec.md",
                        evidence=f"spec read at the PR's {contract.read_from} commit {contract.ref}",
                    )
                )
        findings.extend(table_citations(bundle, pattern)[1])
    else:
        # A hand-built bundle with no contract: the plain id scan.
        citations = find_citations(bundle, pattern)
        for sc in bundle.task.criteria:
            if sc not in citations:
                findings.append(
                    Finding(
                        check="criterion-citation",
                        finding=f"{sc} has no test citing it",
                        evidence=(
                            f"searched test functions in: {', '.join(sorted(bundle.tests)) or '(no tests in bundle)'}"
                        ),
                    )
                )

    if not bundle.ci.green:
        findings.append(
            Finding(
                check="ci",
                finding="deterministic CI is not green",
                evidence=bundle.ci.summary,
            )
        )

    if bundle.task.is_fix and not bundle.red_evidence:
        findings.append(
            Finding(
                check="red-evidence",
                finding="fix task without red→green evidence (no failing run before the change)",
                evidence="bundle.red_evidence is empty",
            )
        )

    return tuple(findings)


def citations_for_pass(
    bundle: EvidenceBundle, pattern: re.Pattern[str] = _DEFAULT_TEST_RE
) -> tuple[Citation, ...]:
    """The Citation tuple a PASS carries — call only after run_checks is clean.

    With a resolved contract: every test the Traceability table names for a
    claimed criterion, and no other. Without one: the id scan's first match.
    """
    if bundle.contract is not None and bundle.contract.spec_slug is not None:
        return table_citations(bundle, pattern)[0]
    found = find_citations(bundle, pattern)
    return tuple(Citation(sc, found[sc]) for sc in bundle.task.criteria)
