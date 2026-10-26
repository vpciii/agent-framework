# Spec: Orientation and alerts — a resume card, a weekly nudge, escalations that reach vpc

- **Status:** Under review
- **Date:** 2026-10-26
- **Author:** Claude (draft) — vpc is author of record
- **Related ADRs:** ADR 0001 (artifacts are the coordination protocol),
  ADR 0004 (worker execution surface — unchanged here), ADR 0005 (one
  per-PR gate — nothing here joins it)
- **Related specs:** worker-agent (Implemented, frozen — this changes its
  timeout and escalation behavior additively)
- **Planning record:** `planning/durable-autonomy/` — brief (Validated),
  options (Converged: option D), bet (Placed: ≤ 2 sessions + 4-week
  trial), pre-mortem (dispositions accepted)
- **Compact spec** (ADR 0024): one PR; Approach and Rollout below.

> This spec is editable while `Draft` / `Under review` / `Approved`.
> When it reaches `Implemented` it **freezes** into a historical record;
> a contradiction found later goes to a test, a new spec, or an ADR —
> not back into this file (methodology §2, §8). If the feature is later
> sunset, only the status flips to `Retired` (ADR 0019) — the content
> stays frozen.

## Problem

agent-framework advances only while vpc is driving it, and stalls stick:
its history is 49 PRs on 4 days in July, then three idle months, after
which vpc no longer knew where it stood and needed a session just to
re-orient. Nothing tells him where a project stands or what to do next,
and the moments that need him go nowhere: an escalation is a file nobody
is notified about, and a worker that hits its time budget is killed
silently — leaving orphaned child processes, a worktree a retry refuses,
and no note of what was in progress (pre-mortem kill-recovery spike,
2026-10-26). Every failure path today is silent (pre-mortem desk check).

## Goals

1. vpc can see where agent-framework stands and its single next action
   at a glance, without a re-orientation session.
2. Once a week, that picture reaches him without his asking.
3. When a worker needs him — an escalation or a timeout — he hears about
   it on his phone, with a durable record in GitHub.
4. A timed-out worker leaves no orphan processes and leaves a note of
   what it was doing.
5. The four-week trial that follows is measurable from records alone.

## Non-goals

- Running any work unattended — no scheduler dispatches workers; that is
  option A, gated on this trial's verdict (bet).
- Resuming or retrying a timed-out task automatically.
- Local models, a durable runtime (option C), or changes to ADR 0004.
- A heartbeat or dead-man's switch for unattended runs (an A concern).

## Requirements

- **R-1 (MUST)** Render a **resume card** from the repository's
  artifacts alone: every spec not in a terminal status (`Implemented`,
  `Retired`, `Superseded`, `Withdrawn`) with its status; each such spec's
  unchecked tasks from `tasks.md`; every planning bet with its status;
  every escalation file; and exactly one **next action**, chosen by a
  fixed precedence rule. The same repository state renders the same card.
- **R-2 (MUST)** When GitHub is reachable, the card also lists open pull
  requests and open issues labelled `escalation` or `timeout`; when it is
  not, the card says so explicitly instead of omitting them.
- **R-3 (MUST)** A **weekly nudge** posts the card to a single GitHub
  issue labelled `status` (updated in place, never duplicated) and sends
  vpc a phone push with the next action and the issue's link.
- **R-4 (MUST)** An escalation, in addition to its file, opens a GitHub
  issue labelled `escalation` — at most one per task, so a retry finds
  the existing issue — and sends a phone push linking it.
- **R-5 (MUST)** When a worker session exceeds its budget, the whole
  process group it started is terminated; no child process outlives it.
- **R-6 (MUST)** A timeout writes a **handoff note** into the kept
  worktree — task, budget, elapsed time, `git status` and diff summary,
  and any progress file the session left — and opens a GitHub issue
  labelled `timeout` (at most one per task) with a phone push, as for an
  escalation.
- **R-7 (MUST)** A failed notification — phone push or GitHub — never
  changes the worker's outcome or exit code and never crashes the nudge;
  the failure is reported in the command's output. The GitHub issue is
  the channel of record; the phone push is best-effort.
- **R-8 (MUST NOT)** The nudge, or anything else in this spec, dispatch a
  worker session or perform task work.
- **R-9 (MUST)** The phone-push endpoint and any credentials come only
  from the environment, never from files in the repository; with none
  configured, the push is skipped and the skip is reported.
- **R-10 (SHOULD)** Every nudge, escalation and timeout leaves a labelled
  GitHub issue whose timestamps (created, first comment by vpc, closed)
  are enough to compute the trial's response times.

## Success criteria

- **SC-1** — Against a fixture repository, the resume card lists the
  non-terminal specs with their statuses, their unchecked tasks, the
  bets with statuses, and the escalation files; rendering twice yields
  identical output.
- **SC-2** — The next action follows the precedence rule (Approach) in a
  fixture for each rule branch, and exactly one is shown.
- **SC-3** — With GitHub unavailable (a failing fake), the card states
  that pull-request and issue status is unavailable rather than omitting
  the section.
- **SC-4** — A nudge with an existing `status` issue updates it and
  opens none; with none, it opens exactly one; either way it sends one
  push containing the next action and the issue link (fake tracker, fake
  push).
- **SC-5** — An escalation opens one `escalation` issue and sends one
  push; a second escalation for the same task finds the existing issue
  and opens no new one.
- **SC-6** — With a fake session that spawns long-lived children, a
  budget expiry leaves no descendant process running.
- **SC-7** — A timeout writes a handoff note containing the task, budget,
  elapsed time, git status and diff summary, opens one `timeout` issue,
  and sends one push.
- **SC-8** — With the push endpoint and GitHub both failing, the worker
  returns the same outcome and exit code as with them working, and its
  output reports each failed notification; the nudge exits without a
  crash and reports the failures.
- **SC-9** — The nudge's code path never invokes the worker session
  runner (a structural test: the nudge module does not import the worker
  orchestrator or session modules).
- **SC-10** — The push endpoint is read from the environment only; with
  it unset, no push is attempted and the skip is reported.

## Approach

- **`status.py` — the resume card.** A pure renderer over the repo
  directory plus an optional GitHub snapshot (open PRs, labelled issues,
  fetched through the existing `gh` seam). Markdown out. **Next-action
  precedence:** (1) an open escalation or timeout → "answer it";
  (2) a spec in `Draft` / `Under review` → "sign off <spec>"; (3) an
  `Approved` spec with unchecked tasks → "next task <T-n> of <spec>";
  (4) an open PR → "review <PR>"; (5) a bet that is `Placed` with no
  spec → "write the spec for <bet>"; else "nothing pending". CLI:
  `python -m agent_framework.status`.
- **The card is published, not committed.** It lives in the `status`
  issue (and the terminal), not in a committed `STATUS.md`: a committed,
  CI-checked file would need regenerating on every branch (the
  pre-mortem's drift failure) or a bot commit to `main`, which would
  bypass vpc's review of every change. *(This refines the options doc's
  "STATUS.md, CI-equality-checked" — flagged for sign-off.)*
- **`alerts.py` — one way to reach vpc.** `notify(kind, title, body,
  key)` opens or finds a GitHub issue labelled `kind` and keyed by `key`
  (e.g. `escalation:<slug>/<task>`), then POSTs title + link to a Home
  Assistant webhook. Reuses the tracker pattern from
  `currency/issue.py`; the push uses the standard library's HTTP client.
  Every result (issue opened/found, push sent/skipped/failed) is returned
  for the caller to report (R-7).
- **Worker changes.** `session.run_claude` starts the session in its own
  process group (`start_new_session=True`) and, on budget expiry,
  signals the group (SIGTERM, then SIGKILL after a short grace) — the
  spike showed this cleans up every child. `orchestrator.work` on
  timeout writes `HANDOFF.md` into the kept worktree and calls
  `notify("timeout", …)`; on escalation calls `notify("escalation", …)`
  after writing the escalation file. Outcomes and exit codes unchanged.
- **`nudge` CLI.** `python -m agent_framework.nudge`: render the card
  with a GitHub snapshot, update the `status` issue, push the summary.
  No worker imports (SC-9).
- **Home Assistant side.** A new automation with a `local_only` webhook
  trigger that pushes to `notify.mobile_app_typhone` — the same target
  and pattern as the existing OPNsense and Gmail fail-alerts, proven to
  reach vpc off-LAN (pre-mortem spike 10). The webhook URL lives in
  `~/.config/agent-framework/agent-framework.env` (mode 600), never in
  the repo.
- **Schedule.** A weekly launchd agent on vpc's primary Mac runs the
  nudge, Mondays 08:00 America/New_York (it needs both `gh` and the
  LAN-only webhook; a cloud scheduled task cannot reach Home Assistant,
  pre-mortem spike 1).
- **Size.** Renderer, alerts, nudge CLI, worker changes and tests: likely
  400–550 lines, mostly tests. If it outgrows one PR, this spec gains a
  `plan.md` (ADR 0024) rather than the bet gaining sessions.

### Decisions

- *2026-10-26* — Resume card published to a GitHub issue rather than
  committed as a CI-checked `STATUS.md` (see Approach).

## Rollout and undo

Additive. Order: (1) merge the code — dormant until configured;
(2) create the Home Assistant automation (reversible: delete it);
(3) write the env file with the webhook URL; (4) load the weekly launchd
agent (`launchctl bootout` stops it); (5) the trial starts with the first
nudge. Undo: unload the agent, delete the automation and env file, revert
the PR; the worker's process-group kill is a pure improvement and can
stay. Nothing irreversible.

## Open questions

- [x] **Glossary.** Resolved 2026-10-26 (vpc): the implementing PR adds
  "resume card", "nudge" and "handoff note" to `docs/glossary.md`.
- [x] **Where the nudge runs.** Resolved 2026-10-26 (vpc): on vpc's
  primary Mac (the one this spec was drafted on), via launchd; a run
  missed while it sleeps runs on wake.
- [x] **Nudge timing.** Resolved 2026-10-26 (vpc): Mondays 08:00
  America/New_York.
- [x] **"Answered" for the trial.** Resolved 2026-10-26 (vpc): an
  escalation or timeout counts as answered at vpc's first comment on its
  issue, or its closing, whichever comes first.

## Out of scope (for now)

- Unattended runs and anything else in option A — gated on the verdict.
- A heartbeat / dead-man's switch, a pinned worker CLI, and consecutive-
  failure alerts — needed only once runs are unattended (pre-mortem
  desk check; escalated to A's spec).
- Validator calibration from vpc's overrides.
- Writing the trial verdict itself (vpc writes it into the planning
  folder when the four weeks end).

## Traceability

Built up as the feature is implemented; complete before the spec is
marked `Implemented`.

| Criterion | Requirement(s) | Verified by (test) |
|---|---|---|
| SC-1 | R-1 | |
| SC-2 | R-1 | |
| SC-3 | R-2 | |
| SC-4 | R-3 | |
| SC-5 | R-4 | |
| SC-6 | R-5 | |
| SC-7 | R-6 | |
| SC-8 | R-7 | |
| SC-9 | R-8 | |
| SC-10 | R-9 | |
