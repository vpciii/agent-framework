# Spec: Citations come from the spec's Traceability table

- **Status:** Approved
- **Date:** 2026-11-09
- **Author:** Claude (draft) — vpc is author of record
- **Related ADRs:** ADR 0005 (one per-PR gate — its deterministic-before-
  model order is kept), ADR 0003 (the spec-coverage checker, whose table
  format this reads)

> This spec is editable while `Draft` / `Under review` / `Approved`.
> When the PR that marks it `Implemented` merges it **freezes** into a
> historical record (methodology ADR 0027);
> a contradiction found later goes to a test, a new spec, or an ADR —
> not back into this file (methodology §2, §8).

## Problem

The cite-the-test gate finds each claimed criterion's test by scanning the
PR's changed test files for the criterion's id and taking the first test
whose text contains it. Two things make that wrong.

- **Criterion ids are only unique within a spec.** `SC-1` exists in every
  spec, and test files hold tests for several specs.
- **Any mention counts.** The id inside an assertion string, a dictionary
  key, or a comment above the next test is taken as that test citing it.

On 2026-11-09 the advisory verdict cited the wrong test on four pull
requests (#65, #68, #69, #73). On #73 — the first PR from a confined
worker session — all three citations were wrong:

```
gate cites SC-1 -> tests/worker/test_orchestrator.py::test_sc3_completed_session_becomes_declared_pr_and_never_merges
gate cites SC-2 -> tests/worker/test_orchestrator.py::test_sc2_session_runs_in_worktree_with_roster_model_and_brief
gate cites SC-3 -> tests/worker/test_orchestrator.py::test_sc3_completed_session_becomes_declared_pr_and_never_merges
```

Those are worker-agent tests; `SC-1` matched because one of them asserts
on the string `"Satisfies: SC-1, SC-2"`. The PR's real tests were in
another file and were named, correctly, in the spec's Traceability table.

This is more than a wrong label. The deterministic check "every claimed
criterion has a test citing it" is satisfied by any changed test file that
mentions the ids anywhere. That PR touched `test_orchestrator.py` only to
update a fake; had it added no tests at all, the check would still have
passed. A PASS says each criterion is cited to its passing test, and today
it can say so about a test that has nothing to do with the criterion.

The correct mapping is already written down. The methodology has each
spec carry a Traceability table — criterion → `path::test_name` — filled
in by the same PR that adds the tests, and CI-checked.

## Goals

1. A PASS cites, for each claimed criterion, the tests the spec's
   Traceability table names for it — and only those.
2. A claimed criterion whose table entry is missing, pending, or names a
   test that is not there or does not cite the criterion is REJECTed by
   code, for free.
3. A criterion verified by a test the PR did not change can be cited.

## Non-goals

- Changing the Traceability table's format, or the spec-coverage checker.
- Per-test pass/fail evidence: "passing" still means the PR's CI is green.
- Deciding whether a cited test is *honest* — that stays the judgment's
  job; this spec only makes sure the judgment is looking at the right test.
- The verdict's JSON shape.

## Requirements

- **R-1 (MUST)** For a resolved spec, the collector reads the spec's
  Traceability table at the PR's **head** commit (the PR is what fills it
  in), and the evidence bundle carries, for each claimed criterion, the
  tests that table names for it, as `path::test_name`.
- **R-2 (MUST)** The collector fetches, at the PR's head, every test file
  the table names for a claimed criterion — whether or not the PR changed
  that file — in addition to the changed test files it fetches today.
- **R-3 (MUST)** Before any model call, the gate REJECTs — naming the
  criterion and, where there is one, the test — when, for a claimed
  criterion: (a) the table names no test for it (no row, an empty cell, or
  `*(pending)*`); (b) a named test's file does not exist at the PR's head;
  (c) no test of that name is found in the file by the project's
  test-citation pattern; or (d) the named test's own text does not contain
  the criterion's id.
- **R-4 (MUST)** A PASS cites, for each claimed criterion, every test the
  table names for it, and no test the table does not name.
- **R-5 (MUST)** The judgment request lists, for each claimed criterion,
  the tests cited for it, inside the delimited data region.
- **R-6 (MUST NOT)** The verdict JSON shape MUST NOT change. A criterion
  with several tests appears as several citation entries.
- **R-7 (MUST NOT)** A bundle built without a contract (by hand, not by
  the collector) MUST NOT change behavior: the existing validator-core
  tests pass unmodified.

## Success criteria

- **SC-1** — Through `collect_bundle` with a faked `gh` runner: the bundle
  carries, for each claimed criterion, the tests the spec's Traceability
  table names at the PR's head; a named test file the PR did not change is
  fetched and present. (R-1, R-2)
- **SC-2** — The 2026-11-09 case: a changed test file holds an older test
  that mentions the claimed id (in an assertion string) ahead of anything
  else, and the PR's real test is in another file named by the table. The
  gate's PASS cites the table's test and not the older one. (R-4)
- **SC-3** — Each of: no row for a claimed criterion; a `*(pending)*`
  cell; a named file that does not exist at the head; a named test not
  found in its file; a named test whose own text lacks the id — is
  REJECTed at the deterministic stage naming the criterion (and the test,
  where there is one); a fake provider proves zero model invocations.
  (R-3)
- **SC-4** — The judgment request contains, inside the data region, each
  claimed criterion's cited tests. (R-5)
- **SC-5** — A criterion whose row names two tests yields a PASS with
  both; the verdict round-trips through the existing JSON form; a
  hand-built bundle with no contract passes exactly as before. (R-4, R-6,
  R-7)

## Approach

One PR, at the same seams validator-evidence used.

- **Parser.** `artifacts.py` gains the Traceability reader: criterion →
  the `path::test_name` references in its row, using the same row and
  backtick conventions as the spec-coverage checker (a `*(pending)*` cell
  is no reference).
- **Bundle.** `Contract` gains the table's entries for the claimed
  criteria. A hand-built bundle has no contract, and for it the existing
  id scan stays (R-7).
- **Collector.** Fetches `spec.md` at the head as well as at the base
  (criterion text still comes from the base, so a rewording still shows),
  reads the table, and adds each named test file to the files it fetches.
- **Checks.** With a contract, citations are the table's entries, each
  verified: the file is in the bundle; the project's test-citation
  pattern finds a test of that name; that test's span contains the id.
  The four failures of R-3 are findings under the existing
  `criterion-citation` check name. The id scan is no longer how a test is
  *found* — only how a named test is *confirmed*.
- **Judgment.** The contract block lists each criterion's cited tests.

### Decisions

- *2026-11-09* — vpc accepted all four open questions as drafted.

## Rollout and undo

The gate is advisory (ADR 0005): nothing here can block a merge. Undo is
reverting the PR. Two visible changes:

- A PR that claims a criterion without filling in its Traceability row is
  REJECTed, where today it can PASS. Worker briefs already require the row
  and the spec-coverage check already requires it at `Implemented`.
- A PASS may carry more citations than before (every test a row names).

## Open questions

All resolved 2026-11-09 (human sign-off).

- [x] **A claimed criterion whose row is still `*(pending)*`: REJECT.**
  (R-3a) The PR claims the criterion; the table is where it says which
  test proves it.
- [x] **Keep the id scan for a bundle with no contract.** (R-7) Only
  hand-built bundles reach it. Rejected: removing the scan and making a
  contract mandatory, which rewrites the frozen validator-gate tests'
  fixtures for no production effect.
- [x] **Keep check (d), that the named test's own text contains the id.**
  It is what "cites" means, and the spec-coverage checker only checks that
  the *file* mentions the id. Known limit: a test's "own text" runs to the
  start of the next test, so a comment between two tests counts for the
  first.
- [x] **Read the table at the head, criterion text at the base.** The
  table is the one part of a spec a task PR is meant to change; the
  criteria are the part it must not.

## Out of scope (for now)

- Making the spec-coverage checker verify citations at test level rather
  than file level (it is the methodology's reference checker; ADR 0003).
- Bounding a test's span more tightly than "up to the next test".
- The other open findings of the 2026-11-09 review.

## Traceability

| Criterion | Requirement(s) | Verified by (test) |
|---|---|---|
| SC-1 | R-1, R-2 | *(pending)* |
| SC-2 | R-4 | *(pending)* |
| SC-3 | R-3 | *(pending)* |
| SC-4 | R-5 | *(pending)* |
| SC-5 | R-4, R-6, R-7 | *(pending)* |
