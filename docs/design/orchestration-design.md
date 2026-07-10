# Agent-team orchestration — design sketch

A chief/worker/validator agent team, coordinating **through the methodology's
artifacts** rather than through chat. The artifacts are the API; the org chart
is disposable. The human is author of record — above the chief.

## Principle: the artifacts are the coordination protocol

No agent passes another agent freeform English. Every handoff is a durable
artifact the receiver can act on *without the sender's context*:

- Chief → Workers: `tasks.md` items traced to success-criterion ids.
- Workers → Validator: a PR whose tests **cite** the criterion ids.
- Validator → Chief: a structured verdict with **cited evidence**.
- Chief → Human: the Traceability table (every criterion → a passing test).

This is what makes the team robust: a worker reads `spec.md` + its task, not
the chief's head; the validator checks tests-vs-criteria, not vibes.

---

## Part 1 — Chief: decomposing a spec into dispatchable tasks

**Input:** an agreed `spec.md` (Goals, Requirements `R-…`, Success criteria
`SC-…`) + `plan.md` (approach, components). Both already human-signed-off
(the methodology's sign-off-between-stages gate).

**Output:** `tasks.md` — a DAG of PR-sized tasks. Each task is a *self-contained
brief*:

```
### T-3 — <imperative title>
- Satisfies: SC-4, SC-5          # ≥1 criterion, always
- Touches: src/auth/session.ts, tests/auth/
- Depends on: T-1                # explicit; forms a DAG
- Done when: tests citing SC-4, SC-5 pass (and, if a fix, red→green shown)
- Brief: <enough for a worker with zero chief-context to execute>
```

**Decomposition rules the chief enforces:**
1. **Every task traces to ≥1 `SC-`.** No task without a criterion — if you
   can't name the criterion, it isn't scoped work (it's exploration → back to
   the spec).
2. **PR-sized** (~<300 line diff). Split anything larger.
3. **Independently mergeable where possible;** real dependencies are explicit
   edges, so the chief can dispatch the ready frontier in parallel and
   serialize only what must be.
4. **`MUST` requirements are covered** — every `R-…(MUST)` reflected in a
   criterion some task owns (ADR 0011), so nothing normative ships untested.
5. **The task is the dispatch unit** — it names its criteria, its files, its
   "done" test. A worker needs nothing else.

**Why this shape:** it's the methodology's `spec → tasks` step, made
machine-dispatchable. The criterion ids are the thread that ties chief intent →
worker output → validator check → chief's final requirements-met verdict.

---

## Part 2 — Validator: the cite-the-test gate

The validator's job is **"show done, don't assert it" (ADR 0015), mechanized.**
It never returns "looks correct." Every PASS cites evidence; every REJECT names
the specific failure.

**Input:** a worker's PR + the task's `SC-` ids.

**Gate — all must hold, each with cited evidence:**

| # | Check | Evidence it must cite (not assert) |
|---|---|---|
| 1 | Each claimed `SC-` maps to ≥1 test citing that id, and it **passes** | the passing test run |
| 2 | If the task is a fix: **red→green** | the test failing *before* (output or test-first commit) + passing after |
| 3 | Deterministic CI green | lint / types / tests / spec-coverage check results |
| 4 | Review checklist (ADR 0015) | spec-conformance (diff does the task, no scope creep, criteria not silently reworded); test honesty (asserts behavior, would fail if broken); glossary language; boundaries/reversibility/secrets; artifacts ride along |
| 5 | **Cross-model** | validator is a *different model* than the worker — blind-spot coverage (the session's own finding) |

**Output → chief:** a structured verdict —
- `PASS { task: T-3, criteria: [SC-4✓(test::a), SC-5✓(test::b)], ci: green }`, or
- `REJECT { task: T-3, finding: "SC-5 has no test citing it; state-machine edge X unhandled", evidence: <cite> }`.

**What it prevents:** the #1 multi-agent failure — an agent (worker *or* chief)
reporting success without proof. The gate makes "done" a cited fact, not a
claim. A REJECT goes back to the worker with the exact finding; the loop is
bounded (N attempts → escalate to human).

---

## The surrounding loop (for context)

1. **Human** signs off `spec.md` → `plan.md` (methodology gates).
2. **Chief** decomposes → `tasks.md` (Part 1).
3. **Dispatch** — chief sends ready-frontier tasks to **workers** (parallel;
   isolated worktrees/branches so they don't collide).
4. **Worker** → small PR, tests citing `SC-` ids.
5. **Validator** → cite-the-test gate (Part 2) → verdict to chief.
6. **Chief, requirements-met check** — aggregate: every `SC-` in `spec.md`
   traced to a passing test (Traceability table); every `MUST` covered; DoD
   met. This is the chief verifying the *whole*, not just each PR.
7. **Human accepts** the diff. The chief is not the final authority — you are.

## Escalation rules (the drift guardrails, ADR 0008 — load-bearing for a swarm)

- **Worker finds the spec wrong** → escalate to chief. A contract change is its
  *own* diff for human sign-off — **never** folded into an implementation PR,
  never a quiet `tasks.md` edit to match the code.
- **Validator disagrees with chief** → the criterion + test is the tiebreaker,
  not seniority.
- **Anything unspecified** (a boundary, a security posture, a domain term) →
  stop and surface, don't invent.

## Implementation notes (orchestration-agnostic)

The design is independent of *how* you run the agents — Claude Code subagents,
the Workflow fan-out primitive, separate sessions, or a custom harness. Because
coordination is through the artifacts (`spec.md` / `tasks.md` / PRs / the
Traceability table), the harness is swappable. Suggested first cut: workers in
isolated git worktrees (parallel, no collisions); validator as a distinct model;
chief holds the DAG and the aggregate traceability check.

**This whole design adds nothing to the methodology** — it's disposable
orchestration *over* the artifacts the methodology already defines. It lives in
the agent-framework repo (and, per project, a `CLAUDE.md`/`CONTRIBUTING.md` note
on how that repo runs its agents).
