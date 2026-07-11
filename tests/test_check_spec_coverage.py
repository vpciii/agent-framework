"""Spec-coverage checker: pending-row semantics.

Regression tests for the drift found drafting the validator-gate spec: an
`Approved`-but-not-yet-implemented spec necessarily has pending Traceability
rows, and the checker (run with --include-approved, ADR 0003) failed it. The
refined semantics: `Approved` may carry explicitly-marked `*(pending)*` rows
(anything actually cited is still validated); `Implemented` requires zero
pending. Infrastructure tests — the checker satisfies no product criterion.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_SCRIPT = Path(__file__).parent.parent / "scripts" / "check_spec_coverage.py"

_SPEC_TEMPLATE = """\
# Spec: Fixture

- **Status:** {status}

## Requirements

- **R-1 (MUST)** Something normative.

## Success criteria

- **SC-1** — A verified thing. (R-1)
- **SC-2** — A not-yet-verified thing. (R-1)

## Traceability

| Criterion | Requirement(s) | Verified by (test) |
|---|---|---|
| SC-1 | R-1 | `tests/test_fixture.py::test_sc1` |
| SC-2 | R-1 | {sc2_cell} |
"""


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        cwd=root,
        capture_output=True,
        text=True,
    )


def _write_fixture(root: Path, status: str, sc2_cell: str) -> None:
    spec_dir = root / "specs" / "fixture"
    spec_dir.mkdir(parents=True)
    (spec_dir / "spec.md").write_text(
        _SPEC_TEMPLATE.format(status=status, sc2_cell=sc2_cell), encoding="utf-8"
    )
    tests_dir = root / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_fixture.py").write_text(
        '"""Cites SC-1."""\n\ndef test_sc1() -> None: ...\n', encoding="utf-8"
    )


def test_approved_spec_may_carry_pending_rows(tmp_path: Path) -> None:
    """Approved + *(pending)* rows → PASS; cited rows still validated."""
    _write_fixture(tmp_path, "Approved", "*(pending)*")
    result = _run(tmp_path, "--include-approved")
    assert result.returncode == 0, result.stdout
    assert "PASS" in result.stdout


def test_implemented_spec_rejects_pending_rows(tmp_path: Path) -> None:
    """Implemented requires zero pending — a pending row is a failure."""
    _write_fixture(tmp_path, "Implemented", "*(pending)*")
    result = _run(tmp_path)
    assert result.returncode == 1, result.stdout
    assert "pending" in result.stdout
    assert "SC-2" in result.stdout


def test_approved_spec_still_validates_cited_rows(tmp_path: Path) -> None:
    """Pending leniency must not weaken validation of rows that DO cite."""
    _write_fixture(tmp_path, "Approved", "`tests/test_missing.py::test_nope`")
    result = _run(tmp_path, "--include-approved")
    assert result.returncode == 1, result.stdout
    assert "not found" in result.stdout
