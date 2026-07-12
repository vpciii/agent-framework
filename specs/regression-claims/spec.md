# Spec: Regression claims — the gate verifies bug fixes' evidence

- **Status:** Approved
- **Date:** 2026-07-12
- **Author:** vpc
- **Related ADRs:** ADR 0005 (one per-PR gate — this adds a claim *type*,
  not a reviewer; adversarial review of solutions stays at the design
  stage, decision 4)
- **Related specs:** validator-gate (Implemented, frozen — every change
  here is additive to its modules, none contradicts it)

> This spec is editable while `Draft` / `Under review` / `Approved`.
> When it reaches `Implemented` it **freezes** into a historical record.

## Problem

Standalone bug-fix PRs claim no success criteria, so the gate's zero-claim
check REJECTs them *before* the red-evidence check or any judgment runs —
in practice, **fixes get no model review at all** (observed on #12, #22,
#33: an honest but contentless "claims no success criteria"). Yet the
methodology gives fixes a precise, checkable contract: a regression test
that failed before and passes after, cited not asserted. The gate just has
no claim type to hang it on.

**Scope principle (the human's direction):** the gate verifies a fix's
*evidence*, never its *approach*. A weird-but-evidenced fix passes. How a
bug gets fixed is not the gate's business as long as the requirements are
met; challenging designs belongs upstream at the spec/design stage
(ADR 0005 decision 4).

## Goals

1. A fix PR can make a **regression claim** — `Satisfies: regression` —
   giving the gate something checkable instead of the empty short-circuit.
2. The claim is verified the same way criteria are: deterministically
   first (free), one scoped judgment call only when clean, PASS citing the
   regression test by name.
3. Everything existing is untouched: SC claims, no-claim PRs, and
   fix-typed *task* PRs behave exactly as today.

## Non-goals

- **Judging fix approach, method, or quality** — explicitly out, per the
  scope principle. No finding may be "should have fixed it differently."
- A second per-PR reviewer (ADR 0005 stands).
- Inferring a regression claim from a `fix:` title alone — the claim is
  explicit, like every claim (the declaration is the channel); the
  existing `is_fix` red-evidence check for criteria-claiming task PRs is
  unchanged.
- Verifying the bug is truly dead beyond the evidence — the red→green run
  and CI attest that; the gate verifies the evidence discipline.
- Changing verdict JSON shape or the validator-gate spec's semantics.

## Requirements

Use RFC 2119 keywords. Every `MUST` is reflected in a success criterion.

- **R-1 (MUST)** The collector recognizes the token `regression` in a
  `Satisfies:` declaration as a **regression claim** — alone or alongside
  `SC-` ids. A PR with a regression claim is not a zero-claim PR.
- **R-2 (MUST)** Deterministic checks for a regression claim, before any
  model call: the bundle carries **red evidence** (the failing-before
  run), and the PR changes at least one test file containing at least one
  test (per the project's test-citation pattern). Either missing →
  REJECT naming it, zero model calls.
- **R-3 (MUST)** The judgment for a regression claim is **scoped to
  evidence**: the prompt's checklist asks (a) would the regression test
  fail if the bug returned, or is it theatre; (b) does the diff exceed
  the fix's stated scope; and it **must not** solicit or carry findings
  about solution approach or method. The checklist text is versioned in
  code where a test pins it.
- **R-4 (MUST)** A PASS on a regression claim cites the regression test
  (`path::test_name`, located via the project's test-citation pattern);
  a PASS with the claim uncited is impossible by construction (the
  existing `Pass` mechanics).
- **R-5 (MUST)** Behavior without a regression claim is bit-identical to
  today: SC claims verify as before; declaration-less and empty-claim PRs
  still REJECT as zero-claim. All existing gate/collector tests pass
  unmodified.

## Success criteria

Each has a stable id and is verified by ≥1 test that cites it; together
they cover every `MUST`.

- **SC-1** — The collector parses `Satisfies: regression` (alone, and
  mixed with `SC-` ids) into a regression claim; the bundle is not
  zero-claim. (R-1)
- **SC-2** — A regression-claim bundle missing red evidence, or changing
  no tests, is REJECTed deterministically naming the gap; a fake provider
  proves zero model invocations. (R-2)
- **SC-3** — The judgment request for a regression claim carries the
  fix-scoped checklist (presence pinned by test) and none of the
  approach-judging language; a defect reported through `return_verdict`
  arrives verbatim. (R-3)
- **SC-4** — A clean regression claim yields
  `PASS { regression ✓ (path::test), ci }`; constructing that PASS
  without the citation raises. (R-4)
- **SC-5** — The existing suite passes unmodified, plus explicit guards:
  an SC-only declaration behaves as today, and a claim-less PR still
  REJECTs as zero-claim. (R-5)

## Open questions

Resolved before the spec is `Approved` (inline or via an ADR).

- [ ] **Claim representation** — `TaskRef.criteria` carries `SC-n`
  strings; a regression claim is a different kind. A boolean field vs a
  reserved token in the criteria tuple: `plan.md` decides (leaning a
  distinct field — reserved tokens in an id tuple invite grep bugs).
- [ ] **Which test counts as "the" regression test** — first new test in
  the diff's changed test files vs requiring the red-evidence paragraph
  to name it. `plan.md` decides (leaning: first test in changed test
  files whose span matches the project pattern; naming-in-evidence is a
  SHOULD in the conventions, not a gate).
- [ ] **Worker briefs** — should fix-typed *tasks* instruct workers to
  add `regression` to their declaration? Touches brief conventions;
  `plan.md` decides (leaning yes, one line).

## Out of scope (for now)

- CI enforcement that every `fix:`-titled PR carries the claim (a later
  ratchet, once the convention has a track record).
- The spec-stage adversarial design review (its own future slice).

## Glossary addition (proposed with this spec)

- **Regression claim** — the token `regression` in a PR's Satisfies
  declaration: the author's explicit claim that the PR fixes a bug with
  a cited red→green regression test. The gate verifies the evidence
  discipline, never the fix's approach. (Added to `docs/glossary.md` in
  this spec's PR.)

## Traceability

Built up during implementation; complete before the spec is `Implemented`.
Rows may be `*(pending)*` while `Approved` (#12).

| Criterion | Requirement(s) | Verified by (test) |
|---|---|---|
| SC-1 | R-1 | *(pending)* |
| SC-2 | R-2 | *(pending)* |
| SC-3 | R-3 | *(pending)* |
| SC-4 | R-4 | *(pending)* |
| SC-5 | R-5 | *(pending)* |
