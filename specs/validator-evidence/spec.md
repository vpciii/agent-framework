# Spec: Validator evidence — the judgment sees the criteria; the collector finds any project's tests

- **Status:** Draft
- **Date:** 2026-11-09
- **Author:** Claude (draft) — vpc is author of record
- **Related ADRs:** ADR 0005 (one per-PR gate — its deterministic-before-model
  order is kept), ADR 0002 (Python is the harness's language, not the
  target's), ADR 0001 (dispatch through the roster — unchanged)

> This spec is editable while `Draft` / `Under review` / `Approved`.
> When the PR that marks it `Implemented` merges it **freezes** into a
> historical record (methodology ADR 0027);
> a contradiction found later goes to a test, a new spec, or an ADR —
> not back into this file (methodology §2, §8).

## Problem

A review of the validator on 2026-11-09 found two gaps between what the
cite-the-test gate claims to check and the evidence it is given.

1. **The judgment is asked about criteria it never sees.** The evidence
   bundle carries the claimed criteria as ids only (`SC-1, SC-2`). The
   judgment prompt asks whether the diff "does the task — and only the
   task" and whether any success criterion was "silently reworded or
   weakened", but the criterion text and the task are not in the request.
   The validator model can judge test honesty from the diff and tests; it
   cannot judge conformance to a contract it was not shown. A PASS today
   therefore says less than the gate's definition says it does.
2. **The collector only ever collects Python tests under `tests/`.**
   `collect_bundle` keeps a changed file as a test only if its path starts
   with `tests/` and ends with `.py`. The project-portability spec gave
   target projects a configurable test-citation pattern so non-Python
   projects could be gated (its SC-3), but that pattern is applied to a
   bundle the collector has already emptied of every non-Python file. On
   such a project every claimed criterion is REJECTed as uncited. The
   project-portability SC-3 tests pass because they hand-build the bundle
   and never go through the collector.

Both are found now, before the chief exists: a chief multiplies whatever
the gate lets through.

## Goals

1. The judgment request carries the **text** of every claimed success
   criterion and, when the PR names a task, that task's block from
   `tasks.md` — read from the artifacts, never from the PR's description of
   them.
2. A claim the gate cannot tie to a spec is REJECTed by code, for free,
   rather than judged blind.
3. Which changed files are test files is the **target project's**
   declaration, so a project in any language can be gated through the real
   collector.

## Non-goals

- Changing what a PASS or REJECT is, or the verdict's JSON shape.
- Judging the criteria themselves (the spec-stage adversarial gate —
  ADR 0005 decision 4).
- Finding citing tests in files the PR did not change. A criterion whose
  test already exists and is untouched is still reported uncited, as today
  (see *Out of scope*).
- Per-test pass/fail evidence. "Passing" still means the PR's CI is green.
- Forcing the verdict tool call, a per-request data fence, or filtering
  large diffs — real gaps from the same review, each its own change.

## Requirements

RFC 2119 keywords. Every `MUST` / `MUST NOT` is reflected in a success
criterion.

- **R-1 (MUST)** The collector resolves the spec a PR's claims belong to:
  the slug in the first `specs/<slug>/` path named in the PR body; failing
  that, the one `specs/<slug>/` directory among the PR's changed files when
  there is exactly one. Otherwise the spec is unresolved.
- **R-2 (MUST)** For a resolved spec, the evidence bundle carries the text
  of each claimed criterion, read from `specs/<slug>/spec.md` at the PR's
  **base** commit — the contract as it stood before the PR, so a rewording
  inside the PR shows up as a difference rather than as the new truth. If
  the spec file does not exist at the base (the PR introduces it), the text
  is read at the PR's head, and the bundle records that.
- **R-3 (MUST)** When the PR names a task id that `specs/<slug>/tasks.md`
  defines, the bundle carries that task's block, read the same way.
- **R-4 (MUST)** Before any model call, the gate REJECTs — naming the gap,
  with zero model invocations — a PR that claims criteria when (a) no spec
  is resolved, or (b) a claimed id is not defined in the resolved spec.
- **R-5 (MUST)** The judgment request includes each claimed criterion's
  text and the task block when present, inside the delimited data region,
  labelled as the contract and with which commit it was read from.
- **R-6 (MUST)** The set of changed files collected as tests is decided by
  a `test_paths` list of path patterns in the `[project]` table of
  `agent-framework.toml`. Absent, it selects exactly the files selected
  today (under `tests/`, ending `.py`). A malformed value fails loudly,
  naming the field.
- **R-7 (MUST NOT)** The verdict JSON shape, the exit codes, and the
  validator core's hermeticity MUST NOT change: the core still takes an
  `EvidenceBundle` value and touches neither network nor repository.
- **R-8 (SHOULD)** `docs/adoption.md` documents `test_paths` next to
  `test_pattern`, and `docs/architecture.md` is updated in the same PR.

## Success criteria

- **SC-1** — Through `collect_bundle` with a faked `gh` runner: a PR whose
  body names `specs/<slug>/` yields a bundle carrying each claimed
  criterion's text and the named task's block, read at the base commit;
  with no path in the body and exactly one spec directory among the
  changed files, the same. (R-1, R-2, R-3)
- **SC-2** — A PR that adds its own spec (no spec file at the base) yields
  the criterion text read at the head, and the bundle says so. (R-2)
- **SC-3** — A PR claiming criteria with no resolvable spec, and a PR
  claiming an id the resolved spec does not define, are each REJECTed at
  the deterministic stage naming the gap; a fake provider proves zero
  model invocations. (R-4)
- **SC-4** — The judgment request built from such a bundle contains every
  claimed criterion's text and the task block inside the data region, and
  states the commit they were read from. (R-5)
- **SC-5** — Through `collect_bundle`: with `test_paths` naming a
  non-Python location and a matching `test_pattern`, a changed non-Python
  test file is collected and its criterion is cited by the gate end to
  end; with no `test_paths`, the files collected are exactly today's.
  A malformed `test_paths` raises `ProjectConfigError` naming the field.
  (R-6)
- **SC-6** — A verdict produced after this change round-trips through the
  existing JSON form unchanged, and the validator core's tests run with no
  runner or network seam. (R-7)

## Approach

One PR, two commits' worth of change, both at the collector edge and the
bundle value.

- **Bundle.** `EvidenceBundle` gains the contract as plain values:
  criterion id → text, the optional task block, and where they were read
  from (`base` / `head`), plus whether a spec was resolved. Defaults keep
  every hand-built bundle in the existing tests valid.
- **Parsing, in one place.** The worker's brief already extracts a task
  block and criterion texts from `tasks.md` / `spec.md`. That text-level
  parsing moves to a small shared module both the brief and the collector
  use, so the worker and the validator can never disagree about what
  `SC-3` says.
- **Collector.** Reads `baseRefOid` alongside `headRefOid` from `gh pr
  view`, resolves the slug (R-1), and fetches the two artifact files
  through the existing contents-API seam. The test-file filter becomes the
  project's `test_paths`.
- **Checks.** Two new deterministic findings ahead of the judgment:
  `spec-resolution` and `criterion-defined`.
- **Judgment.** `build_request` adds a `[CONTRACT]` block inside the
  existing data region. The checklist text is unchanged.
- **Config.** `ProjectConfig.test_paths`, validated like `test_pattern`.

### Decisions

- *2026-11-09* — (none yet; open questions below are resolved before
  `Approved`).

## Rollout and undo

The gate is advisory (ADR 0005): nothing here can block a merge. Undo is
reverting the PR; no stored data changes shape. One visible behavior
change: a PR that claims `SC-` ids without naming or touching a spec is
REJECTed where today it could PASS (R-4). Worker PRs always name their
spec in the body, so they are unaffected.

## Open questions

- [ ] **An unresolved spec: REJECT, or judge without the text?** Drafted as
  REJECT (R-4a): criterion ids are only unique within a spec, so a claim
  with no spec is ambiguous, and the house rule is no silent fallback. The
  cost is the behavior change under *Rollout and undo*.
- [ ] **How the PR names its spec.** Drafted as inference from the
  `specs/<slug>/` path the worker's PR body already carries (R-1) — no new
  convention and no new glossary term. The alternative is an explicit
  declaration line beside `Satisfies:`, which is stricter but needs a
  glossary entry and a change to the worker's PR body.
- [ ] **`test_paths` as path patterns, or detect by content?** Drafted as
  an explicit list (R-6). The alternative — treat any changed file the
  `test_pattern` matches as a test — needs no new field but fetches every
  changed file's content and can mistake source for tests.
- [ ] **Interaction with `specs/regression-claims/` (Approved, not yet
  built).** Its R-2 counts "a changed test file" by the project's pattern;
  it should use `test_paths` once this lands. Noted here; that spec is
  still editable, and the change to it is its own signed-off commit.

## Out of scope (for now)

- Citing a test that exists but was not changed by the PR.
- Reading per-test results from CI (e.g. JUnit output) so that "passing"
  is shown per cited test rather than inferred from a green run.
- The other findings of the 2026-11-09 review: least privilege for the
  worker session, forcing the verdict tool call, a per-request data fence,
  an eval set for the judgment, posting the verdict on the PR, a run
  record for worker sessions.

## Traceability

| Criterion | Requirement(s) | Verified by (test) |
|---|---|---|
| SC-1 | R-1, R-2, R-3 | *(pending)* |
| SC-2 | R-2 | *(pending)* |
| SC-3 | R-4 | *(pending)* |
| SC-4 | R-5 | *(pending)* |
| SC-5 | R-6 | *(pending)* |
| SC-6 | R-7 | *(pending)* |
