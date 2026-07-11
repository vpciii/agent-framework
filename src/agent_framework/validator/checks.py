"""The deterministic stage: everything machine-checkable, checked as code.

Runs before any model call (ADR 0005 — a failure here rejects for free).
Pure functions over the evidence bundle: criterion→test citation, CI
status, and red→green evidence for fixes. Also derives the per-criterion
citations a PASS must carry — evidence is *found*, never asserted.
"""

from __future__ import annotations

import re

from .bundle import EvidenceBundle
from .verdict import Citation, Finding

_TEST_DEF_RE = re.compile(r"^(?:async\s+)?def\s+(test_\w+)", re.M)


def _citing_test(sc_id: str, path: str, source: str) -> str | None:
    """The first test function in `source` whose span cites `sc_id`, as path::name."""
    matches = list(_TEST_DEF_RE.finditer(source))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(source)
        if re.search(rf"\b{re.escape(sc_id)}\b", source[m.start() : end]):
            return f"{path}::{m.group(1)}"
    return None


def find_citations(bundle: EvidenceBundle) -> dict[str, str]:
    """Map each claimed criterion to a citing test (`path::test_name`), where one exists.

    Citation is at *test-function* level: an id mentioned only in a module
    docstring names no test and does not count.
    """
    citations: dict[str, str] = {}
    for sc in bundle.task.criteria:
        for path in sorted(bundle.tests):
            cited = _citing_test(sc, path, bundle.tests[path])
            if cited is not None:
                citations[sc] = cited
                break
    return citations


def run_checks(bundle: EvidenceBundle) -> tuple[Finding, ...]:
    """All deterministic findings for the bundle; empty means the model may judge."""
    findings: list[Finding] = []

    citations = find_citations(bundle)
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


def citations_for_pass(bundle: EvidenceBundle) -> tuple[Citation, ...]:
    """The Citation tuple a PASS carries — call only after run_checks is clean."""
    found = find_citations(bundle)
    return tuple(Citation(sc, found[sc]) for sc in bundle.task.criteria)
