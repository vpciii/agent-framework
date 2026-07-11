# ADR 0003: Adopt the methodology's reference spec-coverage checker

- **Status:** Accepted
- **Date:** 2026-07-11
- **Deciders:** vpc

## Context

The methodology's flagship machine-checkable rule (§5; its ADRs 0006 and
0011) requires CI to fail on any success criterion without a citing test and
any `MUST` not covered by a criterion. Its ADR 0017 ships a reference checker
(`templates/ci/check-spec-coverage.py`) as explicitly **adapt-or-replace**,
and requires the project's own tooling ADR to record which. This is that
record.

## Decision

1. **Adopt the reference checker** as `scripts/check_spec_coverage.py`.
   Adapted in *form only* — typed to pass this repo's `mypy --strict` gate,
   f-strings — the checking logic is unchanged from the reference.
2. **Run it with `--include-approved`** in CI, so coverage is enforced from
   spec status `Approved` onward (the gate tightens as implementation
   proceeds), not only at `Implemented`.
3. **One CI job** (`ci`: `uv sync --frozen` → `ruff` → `mypy --strict` →
   `pytest` → the coverage check) is the **required status check** on `main`
   via the `protect-main` ruleset — the branch-protection piece deferred
   until CI existed.
4. Traceability rows cite **full test paths** (`tests/file.py::test_name`);
   no ellipsis/shorthand — the checker resolves every reference literally.

## Alternatives considered

- **Write a project-native checker from scratch** — rejected: the reference
  matches this repo's spec conventions exactly; rewriting it is friction ADR
  0017 exists to remove.
- **Run the reference verbatim (untyped)** — rejected: it would need a
  mypy/ruff carve-out; typing it keeps one quality gate for all Python here.
- **Enforce only at `Implemented`** (reference default) — rejected: this
  project builds spec-first with the table filled in as tasks land, so the
  earlier gate is free and catches drift sooner.

## Consequences

- Uncovered criteria and un-cited tests fail CI, and `main` cannot merge
  without that check passing — traceability is enforced, not aspirational.
- The script is a **project-owned copy**: it may drift from the methodology's
  reference; picking up upstream improvements means re-diffing against the
  template (recorded here so nobody assumes auto-sync).
- Every future spec pays the coverage tax from `Approved` onward — intended.
