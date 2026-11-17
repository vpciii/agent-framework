# Options: how a worker run starts and finishes with vpc away (option A, second round)

- **Status:** Converged
- **Date:** 2026-11-17
- **Converged:** 2026-11-17, by vpc — option A1 as the first build
- **Author:** Claude (draft, from four independent divergers) — vpc is author of record

> At least two genuinely different approaches, kept alive until the last
> responsible moment (planning.md §3). The chosen option's rejected
> siblings become the ADR's "alternatives considered" (methodology.md §1).

This is the round the [verdict](verdict.md) unlocked ("D + A": re-run
`plan-options` for A only). It sits beside [options.md](options.md),
which is frozen and is not edited. The problem is still the
[brief](brief.md)'s; the pre-mortem's dispositions bind every option
here ([premortem.md](premortem.md), dispositions 1, 4, 5, 6/7).

## The decision

What starts a worker run, where does it execute, and how does it reach
an open pull request or a question while vpc is away — both when vpc
hands it a task and when an outside trigger does (vpc's example: an
issue arrives in YouTrack, the run reads it and starts a fix)? Forced
by: the verdict (every day with a merge in the trial was a day vpc sat
down), and vpc's statement on 2026-11-17 that he wants unattended
dispatch.

Each option was drafted by a separate agent holding one stance (boring /
reuse / structural / contrarian), blind to the others. Edits here are
for length; the substance is theirs. "Unverified" marks are theirs too.

## Options

### Option A1 — Dispatch-issue tick on defiant *(boring)*
- **What** — A second launchd agent on defiant, beside the nudge, ticks
  every ~10 minutes. It lists open issues labelled `dispatch`, accepts
  one only if its author is vpc's account and its body matches
  `<spec-slug> <task-id>`, and runs today's
  `python -m agent_framework.worker <slug> <task>` under a PID-stamped
  lock, one run at a time. vpc starts a run from the GitHub app on his
  phone. The session reads only the brief built from `tasks.md` and
  `spec.md` on `origin/main`; the issue is a pointer, never content.
  Questions reach vpc through the existing `escalation` / `timeout` /
  `refused` alerts and the latched Home Assistant push. Kill switch:
  remove the label or `launchctl bootout`.
- **Attractive because** — Most of it exists: process-group kill,
  `--strict-mcp-config`, the spend limit, the handoff check, the alerts,
  and a launchd pattern the nudge has proven. ADR 0007's confinement is
  unchanged. No new dependency, host or credential.
- **Trade-offs / risks** — **No outside trigger:** a YouTrack issue
  cannot start a run until vpc has turned it into a task on `main`.
  **No non-Mac runner:** nothing runs while defiant is off or asleep.
  Resume from a handoff note must be built (`worktree.py` refuses an
  existing worktree or branch). The heartbeat is new work. A question is
  answered by a merged artifact change, not a reply. Unverified: whether
  `claude -p` authenticates under launchd, whether the CLI is pinned,
  Max-plan headroom.
- **Wins when** — The backlog is tasks already specified on `main`,
  defiant is usually on, and the aim is a first unattended PR within
  about two weeks.
- **Appetite / reversibility** — 1–2 weeks: one compact spec, one ADR
  (the trust boundary), 3–4 PRs (tick + lock + author check; resume +
  exactly-once PR; heartbeat + failure classification + CLI pin; docs).
  Undo: unload the agent, delete the label; hand dispatch is untouched.
- **Trust boundary** — The session reads only artifacts on `origin/main`
  (reachable only by PR, only vpc can merge). The issue is reduced by
  code to a slug and a task id, and counts only from vpc's login.

### Option A2 — Rent the run: a cloud scheduled task fired by phone or a YouTrack workflow *(reuse)*
- **What** — One Claude Code cloud scheduled task ("routine") bound to
  this repo, connectors removed, network limited to the package index.
  Its saved prompt is the fixed part of the worker's brief. vpc starts
  it from the Claude app with `worker-eval T-3`; a YouTrack workflow
  rule POSTs an issue's summary and description to the task's `/fire`
  URL. It runs on an Anthropic-managed Linux VM (defiant can be off),
  pushes `claude/<task>`, opens a PR, and waits in the app if it has a
  question. The validator gates the PR in CI as today.
- **Attractive because** — Trigger, scheduler, runner, phone client, VM
  isolation and a resumable transcript already exist. Glue is one saved
  prompt, one YouTrack rule (~20 lines) and one CI job. No launchd,
  lock, heartbeat or process-group code.
- **Trade-offs / risks** — **Runs as vpc's GitHub identity**, and the
  credential proxy does not limit which branches a push updates: "never
  `main`" and "sign-offs only from vpc" then rest on a ruleset vpc
  cannot bypass plus the prompt. **The spend limit is lost** (no per-run
  dollar limit; draws the same Max usage as interactive work). The
  handoff check moves to CI, so it runs *after* the push to a public
  repo. Orchestrator, worktree and session record are replaced; local
  models and the HA push from the run are lost. Research preview;
  Claude-only, against "model-agnostic — no hardcoded vendor". A leaked
  `/fire` token lets anyone send text. Unverified: cloud-session push
  notifications; YouTrack reporter guards and how it protects the token.
- **Wins when** — vpc wants unattended runs this month, defiant's uptime
  is not to be depended on, and tasks need no LAN and no local model.
- **Appetite / reversibility** — ~1 week, 3 PRs. The ADR must decide the
  trust boundary, running as vpc's GitHub identity, and superseding
  ADR 0007's "only the orchestrator pushes" for this surface. Undo:
  delete the task, revoke the token, disable the rule.
- **Trust boundary** — The YouTrack rule fires only when vpc applies a
  "Dispatch" state to an issue he reported, in a project where only he
  can edit issues; it sends summary and description, never comments.
- **Sources** — [routines](https://code.claude.com/docs/en/routines),
  [Claude Code on the web](https://code.claude.com/docs/en/claude-code-on-the-web),
  [cloud environments](https://code.claude.com/docs/en/cloud-environments),
  [GitHub Action](https://code.claude.com/docs/en/github-actions)
  (rejected by the diverger: a long-lived subscription token in a public
  repo's secrets),
  [YouTrack Connection API](https://www.jetbrains.com/help/youtrack/devportal/v1-Connection.html).
  Read by the diverger on 2026-11-17, not re-checked here.

### Option A3 — Intake becomes an artifact; triggers and runners are bound seams *(structural)*
- **What** — Three seams, bound in `agent-framework.toml` the way the
  roster binds models. (1) The only thing that starts a run is a pair
  `(spec-slug, task-id)` naming a task already on `origin/main`, parsed
  by code. Triggers produce it: vpc's `dispatch` issue from the phone,
  or a `tasks.md` change marked for auto-dispatch landing on `main`.
  (2) **Intake:** a tracker adapter (YouTrack first) fetches an issue by
  code; if its reporter is on the project's allowlist, a tool-less
  single-shot model call drafts a compact spec and one task with `SC-`
  ids as a pull request. vpc merging that PR is the sign-off and the
  trigger. (3) **Runner:** `local-macos` (defiant, today's profile) and
  later `linux-ephemeral` (a CI VM whose session job holds no GitHub
  credential and hands a bundle to a second job that checks, pushes and
  opens the PR). Needs four new glossary terms, proposed and not yet
  accepted: *dispatch request*, *trigger*, *runner*, *intake record*.
- **Attractive because** — A bare bug report gains criteria before any
  worker sees it, so "agents coordinate through artifacts" holds. The
  trust line is one place: merge to `main`. A new tracker or runner is
  an adapter plus a config line.
- **Trade-offs / risks** — vpc's review of the intake PR is the gate
  against laundered text; rubber-stamping defeats it. Intake PRs on a
  public repo publish tracker content. A Linux sandbox is untested
  (ADR 0007). An intake sign-off plus a PR review per bug may be slower
  than fixing it by hand. Unverified: Max authentication on a CI runner.
- **Wins when** — A second adopting project, a second tracker, or
  defiant being off or busy actually arrive, and vpc will review short
  intake PRs from his phone.
- **Appetite / reversibility** — Four specs, 12–14 PRs, 6–8 weeks: run
  recovery; the seams with the local binding; intake and the YouTrack
  adapter; the Linux runner after a confinement spike. Three ADRs. Undo:
  remove the bindings and unload the plist. **Smallest first slice:**
  run recovery plus the phone trigger on defiant — which is option A1.
- **Trust boundary** — The worker reads only `origin/main`. The
  tool-less drafter reads only issues whose reporter is on an allowlist
  checked by adapter code. Requests and answers count only from vpc's
  GitHub account.

### Option A4 — Walk away from the next ten tasks first *(contrarian)*
- **What** — Build no trigger and no runner yet. Write `tasks.md` for
  the two Approved specs (worker-eval, regression-claims), dispatch each
  task with today's command, and leave. Tally about ten dispatches:
  reached an open PR; merged without an interactive session reworking
  it; cost; which alert fired. Run the pending usage-headroom spike on
  the first one. If REJECTs dominate, the next spec is the
  verdict-to-worker loop, not a trigger.
- **Attractive because** — No new code; starts tomorrow. First real
  exercise of the alert path the trial never tested, and the first
  measured share of tasks that finish without vpc.
- **Trade-offs / risks** — vpc still types the dispatch command. No
  YouTrack trigger, no off-Mac runner. Ten tasks is a small sample.
- **Wins when** — The real constraint is the supply of worker-ready
  tasks and the worker's finish rate, not who presses Enter.
- **Appetite / reversibility** — Two to three sessions of task-writing
  plus at most $10 and 30 minutes per task. Nothing is installed.
- **The contrarian's case against building now:**
  - the worker has finished three tasks, ever (#31, #38, #73 of 123
    merged PRs);
  - a trigger would have nothing to feed: every `tasks.md` on `main` is
    finished and the two Approved specs have none;
  - there is no revise-after-REJECT loop (`render_verdict` has no
    caller), so an unattended run that draws a REJECT waits for vpc;
  - the finish-without-vpc share and the usage headroom are unmeasured
    (pre-mortem spikes 2 and 9 still pending);
  - an issue is not a task: dispatch refuses a task that claims no
    criterion (#130), and the chief that would write one from an issue
    does not exist as code.

## Genuine difference?

Three shapes, not four. A2 (rent the run) and A4 (don't build yet) are
distinct. **A1 and A3 are one idea at two sizes:** A3's smallest first
slice is A1, and both independently chose the same trigger (a
`dispatch` issue from vpc's account, reduced by code to a slug and a
task id) and the same trust line (the worker reads only `origin/main`).
They differ in whether the trigger and runner seams and tracker intake
are built now or when a second one is needed.

Two convergences worth recording: every build option kept **the issue
as a pointer, never as content** for the worker; and the two options
that handle YouTrack both put **vpc's own act** between the outside
text and the run (A2: vpc sets a state on an issue he reported; A3: vpc
merges an intake PR).

## Comparison

| Option | Cost / appetite | Risk | Reversibility | Notes |
|---|---|---|---|---|
| A1 — tick on defiant | 1–2 wk, 3–4 PRs, 1 ADR | Low–medium: resume and heartbeat are new | High: `launchctl bootout` | Phone trigger only; needs defiant awake; confinement unchanged |
| A2 — cloud routine | ~1 wk, 3 PRs, 1 ADR | High: runs as vpc's GitHub identity, no spend limit, check after push | High: delete the task and token | Only option with YouTrack and an off-Mac runner in week one; Claude-only |
| A3 — seams + intake | 6–8 wk, 4 specs, 3 ADRs | Medium: build size; Linux confinement untested | High per seam | First slice is A1; YouTrack arrives in spec 3 |
| A4 — walk away first | 2–3 sessions, no code | Low | Total | Makes nothing unattended; measures whether it would work |

## Recommendation

**Converged 2026-11-17 (vpc): A1 as the build, on A3's line of growth,
with A4's tally run alongside rather than in front.** The reasoning
below was drafted for vpc's decision and stands as the record of it.

- **A1 first** because it is the smallest thing that makes a run happen
  with vpc away, it keeps everything decided so far (confinement, spend
  limit, handoff check before any push, the roster), and it is the
  first slice of the structural option in any case. Its run-recovery
  work (resume from the handoff note, exactly-once PR, lock, heartbeat)
  is required by pre-mortem dispositions 5 and 6/7 whichever option
  wins.
- **From A3, carried forward:** the rule that a run is started only by
  `(spec-slug, task-id)` naming a task on `main`, and YouTrack handled
  as **intake that produces a pull request vpc merges** — a second,
  later spec, written when A1 is producing PRs. The seams and the Linux
  runner wait for a second tracker or host to exist.
- **A2 not taken:** it gives up the spend limit, moves the handoff
  check to after the push, acts as vpc's own GitHub account, and binds
  the worker to one vendor against the project's model-agnostic rule.
  Revisit if defiant's uptime turns out to be the binding limit.
- **A4's case, answered:** its facts stand, and two of them change the
  order of work. A trigger with nothing to feed is useless, so
  worker-eval's `tasks.md` is written first — it is the queue, and its
  first tasks are dispatched by hand and left alone, which is A4's
  tally at no extra cost. And a REJECT that waits for vpc caps what
  unattended runs can finish, so the verdict-to-worker loop is the spec
  after A1's, ahead of YouTrack intake. What is not taken is A4's gate:
  A1 does not wait for ten tallied dispatches.

Still open, for the spec rather than this choice: whether "defiant must
be awake" is acceptable for the first version, and whether the YouTrack
project is one where only vpc reports issues (it decides how strict
intake must be).

Next: `plan-bet` (appetite for A1), then a compact spec and the trust
boundary ADR. The rejected options become that ADR's "alternatives
considered".
