# Plan: Worker agent — one task to one gated PR

- **Status:** Approved
- **Date:** 2026-07-12
- **Author:** vpc
- **Spec:** ./spec.md
- **Related ADRs:** ADR 0001 (roster), ADR 0004 (worker = headless Claude
  Code), ADR 0005 (its PRs face the gate)

> This plan freezes with its spec: editable while `Draft` / `Under review` /
> `Approved`, a historical record once `Implemented`. A contradiction found
> later goes to a test, a new spec, or an ADR — not back into this file.

## Approach

The same shape that worked for the validator: **pure core, injectable
seams**. The orchestrator is a small state machine — brief → worktree →
session → result → handoff — where every effectful step goes through one
fakeable seam, mirroring the collector's `Runner` pattern.

1. **Brief (pure).** `build_brief(spec_slug, task_id)` parses
   `specs/<slug>/tasks.md` for the task's `### … T-n …` section and
   `spec.md` for the criterion texts of every `SC-` the task satisfies,
   then renders one self-contained document: task brief + criteria + the
   repo conventions (branch name, Conventional Commits, tests citing ids,
   the **Satisfies declaration** the PR body must carry, the validator's
   expectations, and the escalation contract). Unknown slug/task id →
   typed `UnknownTaskError`. No repo-external text can enter the brief —
   its inputs are the two artifact files, by construction (SC-1).
2. **Worktree (seam: git).** `git worktree add .worktrees/<task-id-lower>
   -b feat/<slug>-<task-id-lower>` from current `main`. Deterministic
   derivation from the task id gives SC-6's isolation; an already-existing
   tree/branch fails loudly (no silent reuse). `.worktrees/` is gitignored.
3. **Session (seam: subprocess).** Decision on the spec's open question:
   **`claude -p` via subprocess** — no new Python dependency, the
   orchestrator stays vendor-SDK-free (R-2), and auth (Max subscription vs
   `ANTHROPIC_API_KEY`) remains entirely the session's own config, which is
   exactly ADR 0004's reversibility story. The roster's `worker` binding
   supplies `--model`. The brief goes in as the prompt; the working
   directory is the worktree; the orchestrator enforces the time budget by
   killing the process on expiry (SC-5).
4. **Result (structured, not inferred).** Decision on the spec's open
   question: the session must write **`.worker-result.json`** in the
   worktree root — `{"status": "completed" | "escalated", "detail": str,
   "spec_location": str?}` — as instructed by the brief. File missing or
   malformed → typed `SessionResultError`, worktree preserved. Chosen over
   parsing `claude -p --output-format json` because it survives a session-
   surface swap (SDK, another CLI, a human in a terminal) — the contract is
   with the *worktree*, not the tool.
5. **Handoff (seam: git/gh).** `completed` → commit check (the session
   commits; the orchestrator verifies a non-empty diff vs `main`, fails
   loudly otherwise), push, `gh pr create` with the templated body: task
   id, `Satisfies: SC-…` naming exactly the task's criteria, and a pointer
   to the brief's conventions. Never `gh pr merge` (SC-3). `escalated` →
   no push, no PR; the escalation is written to
   `specs/<slug>/escalations/<task-id>-<n>.md` (durable artifact, SC-4)
   and the worktree preserved.
6. **Collector (R-7, in the same slice).** `_SATISFIES_RE` on the PR body:
   when a `Satisfies:` line is present, claimed criteria come from it
   exclusively; otherwise the existing scraping stands (human PRs
   unchanged). One function, additive (SC-7).

## Components touched

New, under `src/agent_framework/worker/`:

- `brief.py` — `TaskSpec` parsing (`tasks.md` section, criterion texts),
  `build_brief()` (pure).
- `worktree.py` — derive paths/branches; `git worktree` seam.
- `session.py` — `run_session(brief, worktree, model, timeout, run=...)`;
  reads/validates `.worker-result.json`.
- `handoff.py` — commit check, push, PR body template, `gh pr create`;
  escalation artifact writer.
- `orchestrator.py` — `work(spec_slug, task_id, roster, ...) ->
  WorkerOutcome`; the lifecycle log lines (R-8).
- `__main__.py` — `python -m agent_framework.worker <spec-slug> <task-id>
  [--timeout SECONDS] [--roster PATH]`.
- `errors.py` gains `UnknownTaskError`, `SessionResultError`,
  `WorktreeError`.

Touched: `src/agent_framework/validator/collector.py` (Satisfies parsing,
R-7); `.gitignore` (`.worktrees/`); `docs/architecture.md` (worker row —
same PR as the structural change, in the delivery task).

## Data model changes

In-memory frozen dataclasses only:

```
TaskSpec(spec_slug: str, task_id: str, criteria: tuple[str, ...],
         section: str, criterion_texts: Mapping[str, str])
SessionResult(status: "completed" | "escalated", detail: str,
              spec_location: str | None)
WorkerOutcome = PrOpened(url, branch, task_id)
              | Escalated(artifact_path, detail)
              | TimedOut(worktree_path)
```

## API changes

- `work(spec_slug, task_id, roster, *, timeout_s=1800, seams...) ->
  WorkerOutcome`
- CLI: `python -m agent_framework.worker <spec-slug> <task-id>` → outcome
  JSON on stdout; exit 0 (PR opened) / 2 (escalated) / 3 (timeout/error).
  Exit codes distinct from the validator's 0/1 so a future chief can
  compose both.
- Collector: `Satisfies:` declaration takes precedence over prose scraping
  (behavior change only for bodies carrying the declaration).

## Alternatives considered

- **Session surface** — `claude-agent-sdk` (typed API, streaming) vs
  **`claude -p` subprocess**. Chose the CLI: zero new dependencies, the
  orchestrator never imports a vendor SDK (R-2), auth stays session-config
  (ADR 0004's fallback is an env-var change), and the seam is the same
  `Runner` pattern the collector already proved testable. Revisit via ADR
  if the chief needs streaming/steering.
- **Result channel** — parse the CLI's `--output-format json` vs
  **`.worker-result.json` in the worktree**. Chose the file: the contract
  binds to the worktree, not the tool; a malformed/missing file is a typed
  error with the tree preserved for inspection.
- **Worktree location** — temp dir vs **`.worktrees/` in-repo
  (gitignored)**. Chose in-repo: inspectable failures, trivial cleanup,
  no cross-filesystem surprises for `git worktree`.
- **Orchestrator retries on session failure** — rejected: retry policy is
  chief territory (spec non-goal); this slice fails loudly once.

## Risks

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| Session ignores the result-file contract | Med | Med | Typed `SessionResultError`, worktree preserved; the brief states the contract twice (top and bottom) |
| Session runs up Max-plan headroom (shared with interactive use, ADR 0004) | Med | Med | Hard timeout, one task per invocation, no retries; ADR 0004's revisit triggers stand |
| Subscription-auth policy shifts under headless use | Med | Low | ADR 0004 fallback: `ANTHROPIC_API_KEY` env in the session — config, not code |
| Worker PR claims criteria it doesn't satisfy | Med | Low | That is the validator's job (ADR 0005); the orchestrator only guarantees the declaration matches the *task's* criteria |
| Worktree/branch litter on failures | High | Low | Deterministic names, loud collision errors, preserved-tree paths in the outcome for manual sweep |
| `claude` CLI absent/incompatible on the host | Low | Med | Session seam fails loudly with install guidance; no silent fallback |

## Rollout

A library + `python -m` entry; nothing invokes it automatically. Fully
reversible (new code, additive collector change behind the presence of a
`Satisfies:` line). The delivery task's smoke run is one real task
dispatched against this repo — cited in its PR, with the human merging.

## Observability

One structured log line per lifecycle step (R-8): brief built (criteria
count), worktree created (path, branch), session start (model, timeout),
session end (status, duration), handoff (PR url | escalation path |
timeout). Nothing else until the chief exists.

## Test strategy

`pytest` + `pytest-asyncio`; no live sessions, no real worktrees in unit
tests — `git`/`gh`/`claude` all behind the seams, faked per test. Each SC
gets ≥1 citing test (checker enforces from `Approved`):

- **SC-1** brief contains the task section, criterion texts, conventions;
  nothing else; unknown task id → `UnknownTaskError`.
- **SC-2** fake session seam records worktree cwd, derived branch, roster
  model, brief handed as prompt.
- **SC-3** fake success → push + `gh pr create` recorded with task id +
  exact `Satisfies:` line; no merge command in the recorded calls.
- **SC-4** fake escalation → no PR; escalation artifact written with task,
  question, spec location.
- **SC-5** fake session exceeding budget → `TimedOut`, no PR, preserved
  worktree path reported.
- **SC-6** distinct task ids → distinct deterministic paths/branches; same
  id → same derivation.
- **SC-7** collector: body with `Satisfies: SC-1, SC-3` + prose `SC-9` →
  claims exactly `(SC-1, SC-3)`; body without the line → scraping
  unchanged (existing tests keep passing).
