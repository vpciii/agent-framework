# Spec: Worker agent — one task to one gated PR

- **Status:** Approved
- **Date:** 2026-07-12
- **Author:** vpc
- **Related ADRs:** ADR 0001 (model-agnostic roles), ADR 0004 (role execution
  surfaces — the worker is headless Claude Code, not a bespoke API loop),
  ADR 0005 (its PRs face the cite-the-test gate)
- **Related design:** `docs/design/orchestration-design.md` (the loop, steps
  3–5; escalation rules)

> This spec is editable while `Draft` / `Under review` / `Approved`.
> When it reaches `Implemented` it **freezes** into a historical record.

## Problem

The framework can gate PRs (validator, Implemented) but cannot produce them:
there is no way to hand a task from an approved `tasks.md` to a model and get
back a reviewable PR. Per ADR 0004 the worker is **orchestrated headless
Claude Code** — the agentic coding harness already exists; what this slice
builds is the *orchestration around it*: brief assembly, isolated execution,
the PR handoff contract, and escalation. The consumer today is the human
(dispatching one task at a time); the chief (ready-frontier dispatch, retry
loops) is a later slice that calls the same entry point.

Dogfooding the validator also exposed the missing handoff contract: the
collector scrapes `SC-` ids from PR prose, so any body that *mentions* an id
appears to claim it (#18, #20 advisory REJECTs). Worker PRs need a
**structured claim** — the `Satisfies:` declaration — and the collector must
prefer it. This spec owns that convention (a new glossary term rides with
this spec).

## Goals

1. **One task → one session → one PR.** Given a task id from an approved
   `tasks.md`, assemble a self-contained brief, run one headless Claude Code
   session in an isolated worktree, and open a PR that declares what it
   satisfies.
2. **The PR is the handoff artifact.** Its body carries the task id and a
   structured `Satisfies: SC-…` declaration; its tests cite those ids. The
   validator (and later the chief) can act on it with zero worker context.
3. **Escalation is a first-class outcome.** A worker that finds the spec
   wrong or underspecified stops and surfaces a structured escalation — no
   PR, no quiet workaround (methodology guardrail; design doc escalation
   rules).
4. **Bounded and isolated.** Sessions get a worktree and a time budget;
   parallel workers cannot collide; the orchestrator never merges.

## Non-goals

- The **chief**: decomposition, ready-frontier dispatch, REJECT→retry loops,
  and the aggregate requirements-met check — a later spec that invokes this
  slice's entry point per task.
- **Worker pools / scheduling** — one invocation runs one task; parallelism
  is the caller running two invocations (isolation makes that safe).
- **Auto-merge or self-validation** — the PR faces the advisory validator in
  CI and the human; the worker never judges or merges its own work.
- **Cost/token accounting** and session telemetry beyond a structured log.
- **Sandboxing beyond the worktree** (network/file confinement of the
  session is Claude Code's own permission config, not this slice's).
- Changing the validator core — only the **collector** learns the
  `Satisfies:` declaration (additive; prose scraping stays as fallback for
  human PRs).

## Requirements

Use RFC 2119 keywords. Every `MUST` is reflected in a success criterion.

- **R-1 (MUST)** Given a spec slug and task id, the orchestrator assembles a
  **self-contained task brief** — the task's section from `tasks.md`, the
  spec's requirements and success criteria, and the repo conventions the
  session must follow (branch naming, `Satisfies:` PR body, tests citing
  ids, escalation format). A worker reads its brief, not the chief's (or
  any) conversation context.
- **R-2 (MUST)** The session runs **headless Claude Code** in a **fresh git
  worktree on a fresh branch**; the model is taken from the roster's
  `worker` binding and passed to the session. The orchestrator shells out
  to the session and to `git`/`gh` behind injectable seams (no vendor SDK
  import; ADR 0004 makes worker auth the session's own concern).
- **R-3 (MUST)** On session success the orchestrator pushes the branch and
  opens a PR whose body carries the task id and the structured
  `Satisfies:` declaration naming exactly the task's criteria. The
  orchestrator **never merges** and never marks the task done.
- **R-4 (MUST)** The session's outcome is read from a **structured result**
  (completed / escalated, with detail), not inferred from prose. A session
  that reports **escalation** produces no PR; the escalation is emitted as
  a durable artifact naming the task, the blocking question, and the spec
  location it challenges.
- **R-5 (MUST)** Sessions are **bounded**: a configurable time budget,
  enforced by the orchestrator; expiry produces a structured failure (no
  PR, worktree preserved for inspection).
- **R-6 (MUST)** Two concurrent invocations for different tasks get
  **distinct worktrees and branches** deterministically derived from the
  task id — no shared mutable state.
- **R-7 (MUST)** The validator's collector, when a PR body contains a
  `Satisfies:` declaration, takes the claimed criteria **from it alone**
  (prose scraping applies only when no declaration is present).
- **R-8 (SHOULD)** The orchestrator emits one structured log line per
  lifecycle step (brief built, session started, session ended, PR opened /
  escalated / timed out) for later chief consumption.

## Success criteria

Each has a stable id and is verified by ≥1 test that cites it; together they
cover every `MUST`. Sessions and `git`/`gh` are faked at the seams — no live
model calls, no real worktrees in unit tests (a live smoke run is the
delivery task's job, cited not asserted).

- **SC-1** — Brief assembly: for a given spec slug + task id, the brief
  contains the task's `tasks.md` section, every `SC-` id the task satisfies
  with its criterion text, and the PR/escalation conventions — and contains
  no text from outside those artifacts. An unknown task id fails loudly with
  a typed error. (R-1)
- **SC-2** — Session launch: the fake session seam records that the session
  was invoked in a fresh worktree on a branch derived from the task id,
  with the roster's `worker` model and the brief. (R-2)
- **SC-3** — PR handoff: on a fake session reporting success, the
  orchestrator pushes and opens a PR (fake `gh` records it) whose body
  carries the task id and `Satisfies:` naming exactly the task's criteria;
  no merge command is ever issued. (R-3)
- **SC-4** — Escalation: on a fake session reporting escalation, no PR is
  opened and the escalation artifact names the task, question, and spec
  location. (R-4)
- **SC-5** — Timeout: a fake session exceeding the budget yields a
  structured timeout failure, no PR, and the worktree path is reported as
  preserved. (R-5)
- **SC-6** — Isolation: two invocations for different task ids derive
  distinct worktree paths and branch names; same task id → same derivation
  (deterministic). (R-6)
- **SC-7** — Collector honors the declaration: a PR body with
  `Satisfies: SC-1, SC-3` plus prose mentioning `SC-9` yields claimed
  criteria exactly `(SC-1, SC-3)`; a body with no declaration falls back to
  scraping (existing behavior unchanged). (R-7)

## Glossary addition (proposed with this spec)

- **Satisfies declaration** — the structured `Satisfies: SC-…` line in a
  task PR's body: the worker's explicit claim of which success criteria the
  PR delivers. The collector reads claims from it exclusively when present;
  prose mentions of `SC-` ids are not claims. (Added to `docs/glossary.md`
  in this spec's PR.)

## Open questions

Resolved before the spec is `Approved` (inline or via an ADR).

- [x] **Session invocation surface** — resolved in `plan.md`: `claude -p`
  via subprocess behind one seam. No new dependency, no vendor SDK in the
  orchestrator, auth stays session config (ADR 0004).
- [x] **Structured result channel** — resolved in `plan.md`: the session
  writes `.worker-result.json` in the worktree root; missing/malformed →
  typed `SessionResultError`, worktree preserved. The contract binds to
  the worktree, not the tool.
- [x] **Worktree lifecycle** — resolved in `plan.md`: `.worktrees/<task>`
  in-repo (gitignored); cleanup after successful push, preserved on
  failure/timeout with the path reported in the outcome.
- [x] **Does the brief include validator expectations?** — yes (resolved
  in `plan.md`): the gate's checks are part of the conventions the brief
  states.

## Out of scope (for now)

- REJECT→rework loops (chief); multi-task sessions; cross-task context.
- PR review comments / validator verdict delivery to the worker.
- Windows support for worktree orchestration.

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
| SC-6 | R-6 | *(pending)* |
| SC-7 | R-7 | `tests/validator/test_collector.py::test_sc7_satisfies_declaration_is_the_exclusive_claim_channel`, `tests/validator/test_collector.py::test_sc7_without_declaration_scraping_is_unchanged` |
