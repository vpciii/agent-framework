# Spec: Validator agent — the cite-the-test gate

- **Status:** Approved
- **Date:** 2026-07-11
- **Author:** vpc
- **Related ADRs:** ADR 0001 (model-agnostic roles), ADR 0003 (spec-coverage
  CI), ADR 0004 (role execution surfaces)
- **Related design:** `docs/design/orchestration-design.md` (Part 2; the
  two-stage review note)

> This spec is editable while `Draft` / `Under review` / `Approved`.
> When it reaches `Implemented` it **freezes** into a historical record.

## Problem

The framework's load-bearing guarantee is "show done, don't assert it": a
worker's PR is *done* only when every claimed success criterion is backed by
cited, passing evidence. Nothing enforces that today beyond deterministic CI
(ADR 0003) — which proves tests pass and criteria are *traced*, but cannot
judge whether a test is honest (would it fail if the behavior broke?), whether
the diff does the task without scope creep, or whether a criterion was
silently reworded. That judgment gap is the #1 multi-agent failure mode: an
agent reporting success without proof. The validator agent closes it — and it
must exist *before* the worker role, so every worker PR (and every
agent-authored PR in this repo) is gated from day one.

Per the two-stage review note, this role is **conformance with a refutation
mindset** — it checks the PR *against* the spec's criteria. Challenging the
criteria themselves is the spec-stage adversarial gate: a separate, later
slice.

## Goals

1. A **validator** that, given a task's PR evidence, returns a structured,
   **cited** verdict: `PASS` (each claimed `SC-` → its passing test, CI
   green) or `REJECT` (a specific finding with cited evidence).
2. **Deterministic checks run as code, judgment runs as a model.** Whatever
   is machine-checkable (criterion→test citation exists, CI status) is
   checked by script *before* any model call; the model judges only what
   code cannot (test honesty, scope creep, unstated edge cases).
3. The model judgment is reached **through role dispatch** (`validator` in
   the roster, ADR 0001) — single-shot `Request → Response` over the
   existing provider adapters, per ADR 0004. Cross-model coverage (validator
   lineage ≠ worker lineage) stays a roster choice.
4. The verdict is a **durable artifact** a receiver (human now, chief later)
   can act on without the validator's context.

## Non-goals

- The **chief** (dispatch, aggregate requirements-met check) and **worker**
  roles — later specs. The validator's consumer today is the human.
- The **spec-stage adversarial gate** (challenging criteria/requirements
  themselves) — explicitly a different stage per the two-stage review note;
  its own slice and ADR.
- A separate per-PR adversarial reviewer — rejected by the two-stage note;
  the refutation mindset lives *inside* this validator.
- The bounded REJECT→retry loop (N attempts → escalate) — that is chief
  orchestration; today a REJECT simply lands in front of the human.
- Automatically posting verdicts as PR comments / GitHub App integration —
  the slice emits the verdict artifact; wiring it into GitHub UX can follow.
- Re-running tests. CI already runs them (ADR 0003); the validator judges
  the *evidence*, it does not re-execute it (ADR 0004).

## Requirements

Use RFC 2119 keywords. Every `MUST` is reflected in a success criterion.

- **R-1 (MUST)** The validator consumes an **evidence bundle** for one task's
  PR — the task's `SC-` ids, the diff, the tests citing those ids, and the
  deterministic CI outcome — and returns exactly one structured verdict:
  `PASS` or `REJECT`.
- **R-2 (MUST)** A `PASS` cites, for every claimed `SC-` id, the specific
  passing test (`path::test_name`) and the green CI evidence. A `PASS` with
  any uncited criterion is impossible by construction.
- **R-3 (MUST)** A `REJECT` names at least one specific finding with the
  evidence for it (the missing citation, the failing check, the dishonest
  test, the out-of-scope hunk). "Looks wrong" without evidence is not a
  verdict.
- **R-4 (MUST)** Deterministic checks run **before** any model invocation,
  as code: every claimed `SC-` id has ≥1 test citing it, and CI is green.
  If they fail, the validator REJECTs **without spending a model call**.
- **R-5 (MUST)** The model judgment is invoked via `dispatch(roster,
  "validator", …)` — no provider or model named in validator code
  (ADR 0001, ADR 0004).
- **R-6 (MUST)** The judgment prompt carries the **refutation mindset** and
  the review checklist: test honesty (would the test fail if the behavior
  broke?), spec conformance (diff does the task; no scope creep; criteria
  not silently reworded), and a hunt for an unstated edge case. The verdict
  records the checklist findings, not just the outcome.
- **R-7 (MUST)** The verdict is emitted as a durable, structured artifact
  (machine-parseable), self-contained enough to act on without the
  validator's session context.
- **R-8 (SHOULD)** For a task marked as a **fix**, the bundle includes
  red→green evidence (the failing run before the change), and its absence
  is a REJECT finding.

## Success criteria

Each has a stable id and is verified by ≥1 test that cites it; together they
cover every `MUST`.

- **SC-1** — Given a bundle whose criteria all have citing tests and green
  CI, and a validator-role model response that finds no defect, the verdict
  is `PASS` listing every `SC-` id with its cited test and the CI evidence.
  (R-1, R-2, R-5)
- **SC-2** — A bundle with a claimed `SC-` id that no test cites is
  REJECTed by the deterministic stage, naming that id — and **no model call
  is made**. (R-3, R-4)
- **SC-3** — A bundle with red (or missing) CI is REJECTed by the
  deterministic stage citing the CI evidence — no model call. (R-3, R-4)
- **SC-4** — When the model judgment reports a defect (e.g. test theatre),
  the verdict is `REJECT` carrying the model's finding and evidence verbatim
  from the structured response. (R-1, R-3, R-6)
- **SC-5** — The judgment request is dispatched through the roster's
  `validator` role: with the role bound to a fake provider in a test
  registry, the validator uses it (and the prompt it receives contains the
  refutation-mindset checklist). (R-5, R-6)
- **SC-6** — The emitted verdict round-trips: written as the structured
  artifact, re-parsed, and equal to the in-memory verdict (PASS and REJECT
  cases). (R-7)
- **SC-7** — A bundle for a fix-task without red→green evidence yields a
  REJECT finding that names the missing evidence. (R-8)

## Open questions

Resolved before the spec is `Approved` (inline or via an ADR).

- [x] **Evidence-bundle source** — resolved in `plan.md`: the core takes
  an `EvidenceBundle` *value* (hermetic, unit-testable); a thin collector
  edge assembles it from `gh`/git behind one fakeable seam.
- [x] **Verdict format** — resolved in `plan.md`: JSON (round-tripping
  dataclasses, SC-6); human-readable rendering derived from it, never a
  second source of truth.
- [x] **ADR 0005** — drafted alongside `plan.md`
  (`docs/adr/0005-one-per-pr-gate.md`): one per-PR gate, conformance +
  refutation in a single validator; contract-challenge stays upstream.
- [x] **How the model's structured response is enforced** — resolved in
  `plan.md`: a single `return_verdict` `ToolDef` whose schema is the
  judgment shape; the model must answer with that tool call, else a typed
  `JudgmentFormatError`. Zero extension to `Request`/`Response` — the
  existing tool mechanism carries it (ADR 0001's thinness untouched).
- [x] **Coverage-checker semantics for `Approved` specs (drift found
  drafting this).** Resolved by #12 before approval: at `Approved` the
  checker allows rows whose test cell is exactly `*(pending)*` (anything
  cited is still validated); at `Implemented`, pending rows fail.
  Regression-tested in `tests/test_check_spec_coverage.py`.

## Out of scope (for now)

- Verdict delivery (PR comments, checks API, notifications).
- Validator cost/latency accounting and free-tier budget tracking.
- Multi-validator panels / majority voting (the two-stage note's diversity
  ideas) — one validator, one verdict, for this slice.
- Gating this repo's own PRs in CI automatically (dogfooding follows once
  the CLI exists).

## Traceability

Built up during implementation; complete before the spec is `Implemented`.
Every `SC-` maps to the test(s) that verify it (full `path::test` — no
shorthand, ADR 0003) and the requirement(s) it covers; the CI coverage check
(ADR 0003) enforces this table from `Approved` onward.

| Criterion | Requirement(s) | Verified by (test) |
|---|---|---|
| SC-1 | R-1, R-2, R-5 | *(pending)* |
| SC-2 | R-3, R-4 | *(pending)* |
| SC-3 | R-3, R-4 | *(pending)* |
| SC-4 | R-1, R-3, R-6 | `tests/validator/test_judgment.py::test_sc4_defect_from_return_verdict_is_carried_verbatim` |
| SC-5 | R-5, R-6 | `tests/validator/test_judgment.py::test_sc5_judgment_dispatches_through_validator_role_with_checklist` |
| SC-6 | R-7 | `tests/validator/test_verdict.py::test_sc6_pass_round_trips_through_json`, `tests/validator/test_verdict.py::test_sc6_reject_round_trips_through_json` |
| SC-7 | R-8 | *(pending)* |
