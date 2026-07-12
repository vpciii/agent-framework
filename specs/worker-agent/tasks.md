# Tasks: Worker agent — one task to one gated PR

- **Status:** Approved
- **Spec:** ./spec.md
- **Plan:** ./plan.md

PR-sized tasks derived from the approved plan. Each behavioural task traces
to ≥1 success criterion — the tests it must make pass cite those ids. Mark a
task `[x]` with its merged PR number when done. Each task replaces its
`*(pending)*` Traceability rows as its tests land (zero pending required at
`Implemented`, per #12). **Task PRs from here on carry a `Satisfies:`
declaration** — T-4 teaches the collector to read it, so land T-4 early.

**DAG:** T-1 → T-2 → T-3 → T-5; **T-4 independent** (touches only the
validator collector — dispatchable in parallel with T-1, must merge before
T-5 so the delivery smoke run's PR is judged by its declaration).

**Criterion coverage:** SC-1 → T-1 · SC-6 → T-2 · SC-2, SC-3, SC-4, SC-5 →
T-3 · SC-7 → T-4 · T-5 is the delivery edge and closes out the spec.

---

### [x] T-1 — Types + brief assembly (#26)
- **Satisfies:** SC-1
- **Depends on:** —
- **Touches:** `src/agent_framework/worker/{__init__,types,brief}.py`,
  `src/agent_framework/errors.py` (`UnknownTaskError`, `SessionResultError`,
  `WorktreeError`), `tests/worker/test_brief.py`
- **Brief:** The plan's data model (`TaskSpec`, `SessionResult`,
  `WorkerOutcome` variants) as frozen dataclasses. `parse_task(spec_slug,
  task_id)` extracts the task's `### … T-n …` section from `tasks.md` and
  the criterion texts from `spec.md`; `build_brief(task_spec)` renders the
  self-contained brief: task section, criteria with texts, conventions
  (branch, Conventional Commits, tests citing ids, the `Satisfies:` line,
  validator expectations, escalation contract, the `.worker-result.json`
  contract stated top and bottom).
- **Done when:** SC-1's tests pass citing it — brief contains the section,
  every criterion text, and the conventions; contains nothing from outside
  the two artifact files; unknown slug/task id → `UnknownTaskError`.

### [x] T-2 — Worktree + session seams (#27)
- **Satisfies:** SC-6
- **Depends on:** T-1
- **Touches:** `src/agent_framework/worker/{worktree,session}.py`,
  `.gitignore` (`.worktrees/`), `tests/worker/test_worktree.py`,
  `tests/worker/test_session.py`
- **Brief:** `derive(task_spec)` → `(worktree_path, branch)` deterministic
  from slug+task id; `create_worktree`/`remove_worktree` over the git seam,
  loud on collision. `run_session(brief, worktree, model, timeout_s,
  run=...)` — invokes `claude -p` (model from the roster's `worker`
  binding), kills on expiry, then reads and validates
  `.worker-result.json` (missing/malformed → `SessionResultError`).
- **Done when:** SC-6's test passes citing it (distinct ids → distinct
  paths/branches; same id → same derivation); session unit tests cover
  result-file happy path, malformed file, and timeout kill against a fake
  runner.

### [x] T-3 — Orchestrator + handoff (this PR)
- **Satisfies:** SC-2, SC-3, SC-4, SC-5
- **Depends on:** T-2
- **Touches:** `src/agent_framework/worker/{handoff,orchestrator}.py`,
  `tests/worker/test_orchestrator.py`
- **Brief:** `work(spec_slug, task_id, roster, *, timeout_s, seams...) ->
  WorkerOutcome` — the lifecycle: brief → worktree → session → outcome.
  `completed` → verify non-empty diff, push, `gh pr create` (body: task id
  + `Satisfies:` naming exactly the task's criteria), cleanup worktree →
  `PrOpened`. `escalated` → write
  `specs/<slug>/escalations/<task-id>-<n>.md`, preserve worktree, no PR →
  `Escalated`. Timeout → `TimedOut(worktree_path)`, no PR. One structured
  log line per step (R-8). No merge command, ever.
- **Done when:** SC-2 (fake seams record worktree cwd, derived branch,
  roster model, brief-as-prompt), SC-3 (success → push + PR with exact
  declaration; recorded calls contain no merge), SC-4 (escalation → no PR
  + artifact with task/question/spec location), SC-5 (budget expiry →
  `TimedOut`, no PR, preserved path reported) pass, citing their ids.

### [x] T-4 — Collector reads the Satisfies declaration (#25)
- **Satisfies:** SC-7
- **Depends on:** — (parallel with T-1; merge before T-5)
- **Touches:** `src/agent_framework/validator/collector.py`,
  `tests/validator/test_collector.py`
- **Brief:** Parse `Satisfies:` from the PR body (first matching line);
  when present, claimed criteria come from it exclusively; otherwise the
  existing prose scraping stands. Additive — every existing collector test
  keeps passing.
- **Done when:** SC-7's test passes citing it (declaration + prose `SC-9`
  → claims exactly the declared ids; no declaration → scraping unchanged);
  ends the false-positive advisory REJECTs for declared PRs.

### [ ] T-5 — CLI + delivery + spec close-out
- **Satisfies:** — (delivery edge; the core criteria are T-1–T-4's)
- **Depends on:** T-3, T-4
- **Touches:** `src/agent_framework/worker/__main__.py`,
  `tests/worker/test_cli.py`, `docs/architecture.md`,
  `specs/worker-agent/{spec,tasks}.md` (bookkeeping)
- **Brief:** `python -m agent_framework.worker <spec-slug> <task-id>
  [--timeout] [--roster]` → outcome JSON on stdout, exit 0 (PR) / 2
  (escalated) / 3 (timeout/error). Update `docs/architecture.md` (worker
  component + surfaces row — same PR as the structural change). Flip spec
  + plan to `Implemented` (zero pending rows required). **Smoke run,
  cited:** dispatch one real task from this repo through a live headless
  session; its PR (with `Satisfies:` declaration) faces the advisory
  validator; cite the outcome JSON and the PR in the T-5 PR body.
- **Done when:** CLI tests pass against fake seams; the smoke run's
  outcome and resulting PR are cited (not asserted) in the PR body;
  architecture doc rides along; coverage check passes at `Implemented`.

---

## Criterion → task map

Which task delivers each criterion. The canonical `SC-` → **test** mapping
lives in `spec.md`'s Traceability table (single source, checked in CI);
this is only the planning view.

| Criterion | Requirement(s) | Task | Status |
|---|---|---|---|
| SC-1 | R-1 | T-1 | ✅ (#26) |
| SC-2 | R-2 | T-3 | ✅ (this PR) |
| SC-3 | R-3 | T-3 | ✅ (this PR) |
| SC-4 | R-4 | T-3 | ✅ (this PR) |
| SC-5 | R-5 | T-3 | ✅ (this PR) |
| SC-6 | R-6 | T-2 | ✅ (#27) |
| SC-7 | R-7 | T-4 | ✅ (#25) |
