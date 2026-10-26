# Options: how agent-framework keeps moving without vpc at the keyboard

- **Status:** Open
- **Date:** 2026-10-26
- **Author:** Claude (draft, from four independent divergers) — vpc is author of record

> At least two genuinely different approaches, kept alive until the last
> responsible moment (planning.md §3). The chosen option's rejected
> siblings become the ADR's "alternatives considered" (methodology.md §1).

## The decision

What do we build, if anything, so that work progresses — and survives
interruption — between vpc's sessions, while every phase sign-off and
merge stays his ([brief](brief.md))? Forced by: the July–October stall,
a worker that is killed at its budget with nothing to resume, and
escalations that notify no one.

Each option below was drafted by a separate agent holding one stance
(boring / reuse / structural / contrarian), blind to the others and given
only the brief plus verified facts. Edits here are for length and to
correct facts; the substance is theirs.

## Options

### Option A — launchd tick, resumable sessions, GitHub as the inbox *(boring)*
- **What** — No new engine. A launchd agent on defiant runs a stateless,
  idempotent `python -m agent_framework.tick` every ~10 minutes:
  (1) **reconcile** — read `specs/*/tasks.md` plus `gh pr/issue list`,
  pick the next task whose predecessors are merged; (2) **run or
  resume** — the worker session gets a fixed `--session-id` recorded in
  the worktree, a budget expiry or crash leaves worktree + id behind, and
  the next tick resumes with `claude --resume`, `--permission-prompts
  none`, `--max-turns`, `--max-budget-usd`; (3) **notify** — an
  escalation also opens a GitHub issue, and each new PR or issue triggers
  a Home Assistant push. vpc answers from the phone on GitHub (approve,
  merge, or comment + label); the next tick picks it up. Durable state
  is only git, GitHub and the worktree; a lock file prevents overlapping
  ticks.
- **Attractive because** — Every piece already runs on defiant (launchd,
  `gh`, HA alerts, Claude Code's resume flags, the existing subprocess
  seam). State is the artifacts, as ADR 0001 already intends; no database
  or daemon to babysit; reboots need no recovery logic.
- **Trade-offs / risks** — Up to ~10 min latency. Resume is per Claude
  session, not per step, so some tool calls may repeat. Local model stays
  idle (ADR 0004 corollary 3 unchanged). Slightly deeper reliance on
  Claude Code's resume behavior; Max 5x weekly limits must be waited out,
  not spun on. **Fact-check:** since Claude Code 2.1.236 a SIGTERM'd
  print-mode run no longer records an interrupted turn, so "resume after
  budget expiry" may restart the turn's context — unverified, and the
  first thing to spike.
- **Wins when** — The pain is "nobody restarts it and nobody hears about
  it", not crash-consistency inside a step.
- **Appetite / reversibility** — ~1–1.5 weeks, 3 small PRs (resumable
  session; escalation issue + HA notify; tick + plist) under a compact
  spec and one ADR. `launchctl bootout` stops it instantly; the manual
  worker path keeps working.

### Option B — GitHub as the orchestrator: self-hosted runner + Environment approvals *(reuse)*
- **What** — Write no orchestration code. Register defiant as a
  self-hosted Actions runner. The worker is a workflow job (triggered by a
  task landing on `main` or an `agent:ready` issue) running
  `anthropics/claude-code-action` or a plain `claude -p` / `opencode`
  step; it opens a PR and stops. The validator is the existing PR job.
  **Phase gates are GitHub Environments with required reviewers**: the
  run pauses (up to 30 days) until vpc taps Approve in GitHub Mobile.
  Escalations become issues that @mention vpc; his reply re-triggers.
  Each phase is its own job, so a crash costs one re-runnable job; the
  self-hosted job limit is 5 days rather than 1800 s.
- **Attractive because** — Queue, retries, history, notifications,
  approval UI, audit log and concurrency limits come free. `src/` could
  shrink toward a dispatch script plus prompts. Agent steps stay plain
  CLI calls, so any harness or local model fits.
- **Trade-offs / risks** — **Lock-in moves to GitHub** (workflow YAML,
  approval semantics) — portable agent steps, non-portable orchestration.
  **Security:** the repo is public, and GitHub advises against
  self-hosted runners on public repos; requires owner-only triggers, no
  fork-PR runs, or a private repo. Approvals are per job, not
  mid-session: a worker with a question must end and be re-dispatched.
  GitHub outages stall everything. `claude-code-action` on a macOS
  self-hosted runner with Max OAuth is unverified.
- **Wins when** — Phases map cleanly to jobs and "pause until vpc
  approves" is enough; true mid-turn suspension is not needed.
- **Appetite / reversibility** — ~1 week, 1–2 PRs plus a runner-setup
  operation record and an ADR. Delete the workflows and unregister the
  runner; artifacts are untouched.

### Option C — Durable phase engine behind ports *(structural)*
- **What** — A long-running daemon (`afd`, Python, launchd) runs each
  spec as a durable workflow (tasks → per-task work → validate → PR →
  gate) behind three ports: **runtime** (DBOS on SQLite — every phase
  and harness call a checkpointed step, gates as durable waits),
  **harness** (`ClaudeCodeHarness`, `OpencodeHarness` against the local
  `mlx_lm.server`; the roster gains a `harness` field), **notifier** (HA
  push first). Git stays canonical: every gate is an artifact (draft PR
  or `specs/<slug>/gates/G-n.md`); DBOS holds only execution position and
  a `reconcile` command rebuilds it from git + GitHub; `afd status` reads
  the repo. vpc answers gates on GitHub (`/approve`, `/revise <note>`); a
  poller turns that into a durable message. A budget governor sleeps
  durably through Max usage limits and the API spend cap. Needs ~5 ADRs:
  runtime choice, gate protocol, harness abstraction, a programmatic
  chief (superseding ADR 0004 corollaries 1–3), and the trust boundary
  for unattended permissions.
- **Attractive because** — Solves the whole class at once
  (interruption, async sign-off, idle local capacity, lost context).
  Lock-in is contained structurally: DBOS, Claude Code and HA each sit
  behind one adapter, and state is rebuildable from git.
- **Trade-offs / risks** — Largest build before the first unattended
  PR. Two sources of truth to reconcile. Replay-safety when a step
  mutates a worktree mid-way is unproven. A daemon with auto-approved
  tools widens the attack surface. A programmatic chief and local PR
  authors are real methodology shifts.
- **Wins when** — Unattended multi-phase runs become the normal mode,
  model and harness churn continues, and more projects adopt the
  framework.
- **Appetite / reversibility** — ~5–6 weeks part-time, 3–4 specs.
  Engine-level reversibility is high (ports, rebuildable state); the ADR
  0004 supersessions are reversible but reshape roles.

### Option D — Don't build autonomy: a resume card and a nudge *(contrarian)*
- **What** — Treat the real failure as **losing the thread**, not
  "needs vpc present". (1) A generated `STATUS.md` — active spec, open
  task, last decision, next action — CI equality-checked against the
  artifacts. (2) A weekly nudge (the existing weekly Actions pattern or
  an HA alert): "agent-framework: N open items, next action X".
  (3) Cheap worker fixes: longer budget, resume on a kept worktree, and
  one phone push when an escalation file appears. No unattended chief,
  no state machine, ADR 0004 untouched.
- **Attractive because** — The evidence says the bottleneck is
  re-orientation: on 2026-10-26 one interactive session with short
  approvals shipped six PRs, including a live-verified federation setup.
  The stall's measured cost was forgetting where things stood — which a
  resume card fixes directly.
- **Trade-offs / risks** — vpc still sits down to make progress; the
  local model stays idle; if the routine share of tasks is large,
  throughput is left on the table.
- **Wins when** — vpc's binding constraint is attention across projects,
  not keyboard time within a session.
- **Appetite / reversibility** — ~1 session; fully reversible (a doc, a
  CI check, a notification).
- **The contrarian's case against building:** no escalation has ever
  fired (no `escalations/` directory exists); the brief's "routine share"
  and "local model good enough" are *Suspected*; local capacity is supply,
  not demand, and collides with ADR 0004 corollary 3; sign-offs stay
  vpc's, so autonomy mostly moves *where* he waits; there is no chief code
  and the worker has never run unattended — durable orchestration before
  that is the "harness by stealth" the planning-orchestration bet warned
  against; and the brief itself says nothing forces this now.

## Genuine difference?

Yes — four distinct shapes: an in-repo scheduler (A), GitHub's own
orchestration (B), a durable engine (C), and not building (D). One
convergence worth noting: **all three build options independently chose
GitHub (PR approvals / issues / comments) as vpc's answer channel and a
phone push as the notification**, and all three keep git as the source
of truth. A and B differ mainly in who owns the loop (a launchd tick vs.
GitHub Actions); C is A's shape plus a durable runtime and ports.

## Ideas borrowed from Pi Durable

Earendil's [Pi Durable announcement](https://earendil.com/posts/pi-durable/)
(2026-10-01) describes a durable agent harness built for the same class
of problem. It is used here **as a source of methods only — not as a
candidate dependency** (vpc, 2026-10-26); it would also clash with ADR
0002 (TypeScript) and is explicitly experimental. Its design choices are
portable to any option above, in Python, over git artifacts:

| Pi Durable idea | What it means here | Helps |
|---|---|---|
| **Store intent before acting**; every step is a task that checkpoints before it moves on | The worker writes "about to run step X" to its worktree record before doing X, so a restart knows exactly where it was | A, C |
| **Per-step replay declaration** — safe steps rerun after a crash; unsafe ones are reported as *interrupted*, never repeated | Classify each worker step: tests, reads, lint = safe to rerun; `git push`, `gh pr create`, issue creation = unsafe, so they are made idempotent or surfaced to vpc | A, C |
| **Exactly-once submissions** via a caller-supplied request id | Key every outward action by task id (e.g. look for an existing PR on the task's branch before creating one), so a retry never opens a second PR or issue | A, B, C |
| **Memoized human decisions** — a hook stores an approval once (first write wins) so a restart finds the answer instead of asking again | A phase sign-off is recorded once as an artifact (approval, commit, or gate file) and every later run reads it rather than re-asking vpc | A, B, C |
| **Handoff / reset**: end a context with a handoff note, start a fresh one from it; old history stays searchable | Instead of resuming a killed Claude turn, a worker that hits its budget or a usage limit **writes a handoff note** and the next run starts fresh from it — sidesteps option A's biggest unknown (SIGTERM no longer records the interrupted turn since Claude Code 2.1.236) | A, C, D |
| **Ownership tree with abort cleanup** — aborting a task aborts what it owns, bottom-up, each cleaning up its own effects | Cancelling a task closes its draft PR, deletes its branch and removes its worktree, in that order | A, C |
| **Foreground vs. background work** | A worker run blocks its phase; a nightly check or a reminder runs in the background and never holds up a gate | A, C |
| **State lives in documents committed atomically with the transcript** | Already this repo's stance: artifacts are the state. Keep execution position derivable from them, never a second source of truth | all |
| **Conversations store names, not code** — swapping an extension needs no migration | The roster stores role → provider/model (and a future harness) by name, so swapping a harness or model is a config edit, not a state migration | A, C |
| **One process owns the storage; others attach and watch** | A single lock owner on defiant; `status` / phone views read committed state and never write it | A, C, D |

The handoff idea changes the comparison most: it gives option A a way to
survive interruption without depending on Claude Code's resume
semantics, which was A's main unverified risk.

## Other methods surveyed (2026-10-26)

Searched for other published approaches to durable, long-running agents;
read the primary sources below. Used as methods only, like Pi Durable.

**Anthropic, [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
(Nov 2025) and [Harness design for long-running apps](https://www.anthropic.com/engineering/harness-design-long-running-apps)
(Mar 2026).** Claude Agent SDK work spanning many context windows.

| Idea | What it means here | Helps |
|---|---|---|
| **Initializer session** sets up a run script, a progress log and a baseline commit; later sessions only make incremental progress | A task's first run writes its worktree's progress note and setup commit; every later run builds on them | A, C, D |
| **Fixed orientation ritual** at the start of every session: confirm the working directory, read git log + progress file, read the feature list, pick the top unfinished item, run a smoke test *before* new work | The worker brief starts with the same ritual, so a fresh context (after a crash, a budget stop or a handoff) re-orients the same way every time | A, C, D |
| **Machine-readable feature list** the agent may change only by flipping a pass/fail field; tests may not be edited or removed; JSON because models overwrite Markdown more readily | `tasks.md` + the Traceability table already play this role; add the rule that a worker may tick status but never rewrite criteria or delete tests (consistent with the regression-claims spec) | A, C |
| **One feature per session; end clean** — commit plus progress update, code mergeable | Matches "one task → one PR"; make "leave a commit and a progress note before stopping" a hard rule of every run, including budget stops | A, C |
| **Context resets beat compaction** for long jobs, carried by a structured handoff | Same conclusion as Pi Durable's handoff: restart from a handoff note rather than resume a long context | A, C |
| **Planner / generator / evaluator** as separate agents | The chief / worker / validator split this repo already has — independent confirmation of the design | — |
| **A separate, skeptical evaluator** beats self-evaluation; it is calibrated with scored few-shot examples and **re-tuned from logs where it disagreed with a human** | Feed vpc's overrides of validator verdicts back into the validator's prompt as calibration examples — a concrete improvement loop for the cite-the-test gate | A, B, C |
| **"Sprint contract"**: before coding, generator and evaluator agree what "done" means and how it will be verified | The task's `SC-` ids and Satisfies declaration are this contract; a worker that can't state its verification up front escalates instead of starting | A, C |
| Named failure modes: lost coherence as context fills, **"context anxiety"** (wrapping up early near the limit), lenient self-grading, under-scoping, stubbed features | A checklist for the pre-mortem and for validator rules (e.g. reject stubbed or `TODO` implementations) | pre-mortem |

**HumanLayer, [12-Factor Agents](https://github.com/humanlayer/12-factor-agents).**
Principles for production LLM software.

| Idea | What it means here | Helps |
|---|---|---|
| **Unify execution state and business state** (factor 5): where the run is can be inferred from its history, giving one source of truth that is easy to resume, fork and inspect | The strongest argument for git-as-canonical: execution position derived from artifacts, not held in a separate store — supports A over C's second store | A |
| **Launch / pause / resume through simple APIs** (6) and **contact humans with tool calls** (7) | An escalation or sign-off request is a structured action the worker *calls* (role, question, options, what it will do on each answer), which pauses the run — not a free-form file written on the way out | A, B, C |
| **Own your control flow** (8) and **small, focused agents** (10) | Keep the loop in agent-framework's own Python, with each agent doing one phase; don't hand the loop to an opaque framework | A, C |
| **Trigger from anywhere, meet users where they are** (11) | Answers can come from the phone (GitHub, Home Assistant), not only a terminal | A, B, C |
| **The agent as a stateless reducer** (12): state + event → new state | Exactly option A's tick: each run reads the artifacts and an event (a merge, an answer) and writes the next state | A |

**Durable-engine human-approval patterns** — [Temporal's human-in-the-loop cookbook](https://docs.temporal.io/ai-cookbook/human-in-the-loop-python)
and [a 2026 comparison of approval patterns](https://cadenya.com/other-content/human-in-the-loop-approvals-for-ai-agents).

| Idea | What it means here | Helps |
|---|---|---|
| **An approval wait costs nothing and survives restarts** — state lives in a durable store, never a process held open | No process blocks waiting for vpc; the gate is an artifact and the next run checks it | A, B, C |
| **Every wait has a timeout with a defined outcome** (cancel, escalate, or a default) | Each sign-off request states what happens if unanswered (e.g. re-notify after 2 days, park the task after 7) instead of waiting forever | A, B, C |
| **Policy-based auto-approval for low-risk actions** | Tier the gates: e.g. a dependency patch bump or a docs-only PR may proceed to an open PR without asking; anything touching a spec, an ADR or credentials always asks. vpc still merges every PR | A, B, C |
| **LLM and tool calls as journaled steps**, not re-executed on replay | Same as Pi Durable's intent-before-action and replay declaration | A, C |

**What this adds to the recommendation:** the surveyed methods converge
on the same core — *fresh context + a structured handoff + a fixed
orientation ritual + small units that end clean + an independent
evaluator + human requests as durable, time-limited waits*. Almost all
of it is discipline in prompts, artifacts and a small loop, which favors
A (and D's resume card) over a heavier engine. Two ideas are genuinely
new to the options: **validator calibration from vpc's overrides**, and
**risk-tiered gates with timeouts**.

## Comparison

| Option | Cost / appetite | Risk | Reversibility | Notes |
|---|---|---|---|---|
| A — launchd tick | ~1–1.5 wk, 3 PRs | Medium → lower with a handoff note instead of turn resume | High: `launchctl bootout` | Uses only what's on defiant; ADR 0004 intact |
| B — GitHub orchestrator | ~1 wk, 1–2 PRs + op record | Medium–high: self-hosted runner on a **public** repo | High: delete workflows, unregister runner | Lock-in to GitHub; best approval UX for free |
| C — Durable engine | ~5–6 wk, 3–4 specs, ~5 ADRs | High: build size, replay-safety, methodology shifts | High for engine; moderate for ADR 0004 changes | Only option that uses the local model and a programmatic chief |
| D — Resume card | ~1 session | Low | Total | Doesn't make work happen unattended — by design |

## Recommendation

*To be decided with vpc — the divergers don't vote.* A draft to react to:

**Stage it: D now, A next, C's ideas held in reserve.**

- **D first**, because it is one session, fully reversible, and tests the
  contrarian's central claim with evidence: if a resume card and an
  escalation push end the stalls, the build options are solving a problem
  vpc doesn't have.
- **A as the build** when D isn't enough — it is the smallest option that
  actually makes work happen unattended, keeps ADR 0004 intact, and adds
  no runtime. Built with Pi Durable's discipline: intent recorded before
  each step, steps classified safe-to-rerun or not, outward actions keyed
  by task id, sign-offs recorded once, and **a handoff note instead of
  resuming a killed turn** — so it no longer hinges on `claude --resume`
  recovering a budget-killed print-mode run (still worth a quick check).
- **Carried forward from the runners-up:** from C, git-as-canonical with
  rebuildable execution state, the `harness` seam (so a local model can
  enter later via its own ADR), and a budget governor that sleeps through
  usage limits; from B, GitHub approvals as the gate surface and
  @mention-driven escalations.
- **B not taken** primarily for the public-repo self-hosted-runner risk
  and the move of lock-in to GitHub — revisit if the repo goes private.
- **C not taken now**: its value depends on unattended runs being the
  norm and the local model passing the validator, neither yet measured.
  It is the natural destination if A succeeds and demand grows.
- **D's case, answered:** taken as the first step rather than rejected;
  its "no measured demand" point is exactly what D's trial measures.

Whichever is chosen, the rejected options become the ADR's
"alternatives considered".
