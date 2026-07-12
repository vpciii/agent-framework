# Spec: Verdict rendering — human-readable verdicts

- **Status:** Approved
- **Date:** 2026-07-12
- **Author:** vpc
- **Related ADRs:** ADR 0005 (verdicts cite, never assert)
- **Note:** Deliberately small — the validator-gate plan deferred exactly
  this ("human-readable rendering derived from the JSON, not a second
  source of truth"), and it is the worker agent's first dispatched task
  (worker-agent T-5 smoke run).

> This spec is editable while `Draft` / `Under review` / `Approved`.
> When it reaches `Implemented` it **freezes** into a historical record.

## Problem

Verdicts are durable JSON (validator-gate R-7) — right for machines, poor
for humans reading a CI log or a future PR comment. There is no rendering
of a verdict for people. The rendering must be *derived* from the verdict
value — never a second source of truth.

## Requirements

- **R-1 (MUST)** A function renders any `Verdict` (`Pass` or `Reject`) to
  markdown: a PASS shows the task id and each criterion with its cited
  test and the CI evidence; a REJECT shows the task id and each finding's
  check, finding, and evidence.
- **R-2 (MUST)** The rendering is derived purely from the verdict value —
  no I/O, no second representation to keep in sync.

## Success criteria

- **SC-1** — Rendering a `Pass` yields markdown containing the task id,
  every citation's criterion and `path::test`, and the CI evidence;
  rendering a `Reject` yields markdown containing the task id and every
  finding's check, finding, and evidence. Verified by tests citing SC-1.
  (R-1, R-2)

## Out of scope

- Posting renderings anywhere (PR comments, logs) — consumers come later.
- Any change to the JSON form or the verdict types.

## Traceability

| Criterion | Requirement(s) | Verified by (test) |
|---|---|---|
| SC-1 | R-1, R-2 | *(pending)* |
