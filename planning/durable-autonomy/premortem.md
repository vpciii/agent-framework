# Pre-mortem: durable autonomy (D now, A next)

- **Status:** Open
- **Date:** 2026-10-26
- **Author:** Claude (draft, from three independent red-team postmortems) — vpc is author of record

> Imagine it shipped and failed — work backward to why, then probe the
> most dangerous assumptions cheaply before committing (planning.md §5).

Target: the converged plan in [options.md](options.md) — **D** (a
`STATUS.md` resume card, a weekly nudge, an escalation phone push, cheap
worker fixes) now, then **A** (a launchd tick on defiant running the
headless worker unattended, with handoff notes and risk-tiered,
time-limited sign-offs). Three agents each wrote "it is October 2027, it
shipped and failed — why?", blind to one another, through a technical,
a human/adoption and an external lens.

## "It failed. Why?"

**Human / adoption**
- D worked, so A ate the freed attention — a July-style burst of
  building, then silence.
- The weekly nudge became wallpaper among the existing Home Assistant
  alerts (OPNsense, ACME, Gmail cleanup); swiped away unread by week six.
- Escalations landed mid-session or at dinner; a spec diff can't be
  reviewed on a phone, so they were starred "for later", timed out, and
  tasks parked one after another.
- Re-notifies on parked tasks read as a guilt backlog; the automation
  was muted.
- Reviewing unattended PRs without the conversation cost more than
  approving live work in chat; the queue outgrew vpc.
- One PR cited a test it hadn't really exercised; trust collapsed back
  to reviewing everything, so the risk tiers saved nothing.
- The tick spent the shared Max 5x week on routine work; vpc got
  rate-limited on KinshipBonds, unloaded the plist "temporarily", and
  never reloaded it.
- It became a fourth homelab job to maintain (CLI flags, `gh` auth, HA
  upgrades, launchd quirks), all needing vpc.
- Spec → plan → tasks with a sign-off at each stage meant the agent
  mostly waited on gates; a one-day change took two weeks of taps.
- No trial verdict was recorded (as with the planning-orchestration
  bet), so A shipped without evidence D wasn't enough.
- Projects people actually use (KinshipBonds, the homelab) out-competed
  "a framework for building frameworks" every week.
- The live session itself was what kept vpc engaged; removing him from
  the loop removed his reason to come back.

**Technical**
- A Claude Code auto-update changed `-p` again (exit codes, permission
  defaults, flag names); every tick failed the same way, read as
  ordinary task failure, and nothing alerted on "all runs failing".
- The 1800 s SIGKILL killed only `claude`; its MCP servers, `pytest` and
  bash children kept running and held files; no handoff note could be
  written by a killed process.
- `create_worktree` (deliberately) refuses an existing tree or branch, so
  every later tick hit `WorktreeError` on the same task forever.
- A stale lock file (sleep, or a tick killed mid-run) stopped everything
  silently for weeks, while the nudge kept reporting as if all was well.
- Memory contention: `mlx_lm.server` (up to ~45 GB), Ollama, Open WebUI,
  Time Machine and a worker running tests pushed the 64 GB machine into
  swap; the Gmail and OPNsense jobs missed their windows.
- Each fresh-context orientation re-read the repo and log, burning
  weekly limits; ticks spun on the limit error instead of waiting.
- When the Max token failed, the auth fallback ran on the API key and
  used the $100 credit in days; the spend limit then stopped workers
  mid-turn, with no handoff note.
- A kill between `git push` and `gh pr create` left a pushed branch with
  no PR; the exactly-once check looked for a PR, not a branch, so a
  second branch and PR were opened.
- **Prompt injection via the public repo:** the reconciler fed outsiders'
  issue and comment text to an unattended `claude -p` with auto-approved
  tools, which inherited vpc's user-level MCP servers (Home Assistant,
  Gmail, Monarch, OPNsense).
- **Spoofable sign-offs:** approvals read from labels or comments
  without a strict author check; a timeout defaulted to "proceed" on a
  spec-touching PR.
- Home Assistant is LAN-only: off-LAN or after a token rotation, pushes
  went nowhere while the HTTP call to HA still returned 200.
- Regenerating `STATUS.md` on worker branches broke its CI equality
  check on every PR whose base had moved.

**External**
- The paused Agent SDK / `claude -p` billing change shipped after all;
  unattended runs became metered and A's premise ("covered by Max")
  collapsed.
- Anthropic's own product covered it: cloud scheduled tasks
  ("routines") — schedule, GitHub-event and API triggers, running even
  when the computer is off — made the home-built tick an inferior copy.
- Weekly limits were tightened for always-on use; the budget governor
  slept most of the week and throughput looked like D anyway.
- GitHub's own agents and mobile approvals made the "GitHub as inbox"
  layer redundant; self-hosted runners on private repos became billed.
- The Gemini free tier was cut or changed terms; the independent
  validator went dark.
- Local models passed the validator by mid-2027, and other harnesses
  did durable runs natively; a Claude-only tick was the lock-in vpc
  wanted to avoid.
- macOS tightened permissions for launchd agents, or lid sleep and dock
  hangs stopped ticks unnoticed.
- Workload Identity Federation or HA cloud-push changes broke CI auth or
  notifications silently.
- Cloud agents made "sit down for one session" cheap enough that D alone
  ended the stalls, and A was never used.

## Assumptions it depends on

| # | Assumption | Confidence | Impact if wrong |
|---|---|---|---|
| 1 | A must be **home-built** (no vendor scheduler fits) | **L** — cloud and Desktop scheduled tasks exist | H |
| 2 | Max 5x leaves **headroom for unattended runs** without starving interactive work | L | H |
| 3 | vpc will **answer sign-offs from the phone** in time; "two minutes" is real | L | H |
| 4 | **Untrusted GitHub text** can be kept away from an agent holding home-network credentials | M (it's a design choice, not yet made) | H |
| 5 | A **killed run leaves recoverable state** (no orphans, no worktree collision, no half-made PR) | L (the code today says otherwise) | H |
| 6 | `claude -p` **behavior stays stable** across auto-updates, or drift is detected | L | H |
| 7 | "**No news" means nothing is happening** — stalls, dead pushes and stale locks are visible | L | H |
| 8 | **Losing the thread** (not lack of autonomy) is the main cause of stalls — D's premise | M | M |
| 9 | **defiant has spare capacity** (memory, uptime) for workers alongside its other jobs | M | M |
| 10 | **HA push reaches the phone off-LAN** | L | M |
| 11 | Unattended `claude -p` **stays covered by the subscription**; terms stay put | M (true today, paused change could return) | H |
| 12 | **Free services stay free** (Gemini free tier, public-repo Actions) | M | M |
| 13 | **Unattended PRs are trustworthy enough** that risk tiers save review time | L | M |
| 14 | The **process overhead** (stage gates) fits small routine work | M | M |

## Spikes

For the high-impact, low-confidence assumptions. Spike code stays in
scratch space; only the finding lands here.

| # | Assumption | Spike (time-boxed) | Finding |
|---|---|---|---|
| 1 | Home-built tick needed | **1–2 h.** Create one cloud scheduled task (and one Desktop scheduled task) on a throwaway repo: on a schedule, read a `tasks.md`, do one trivial task, open a PR. Note: auth, which plan limits it draws on, what tools/MCP servers it can reach, how it notifies, what happens on failure. | *pending* |
| 2 | Max 5x headroom | **1 task.** Run one real worker task headless; read `/usage` before and after; extrapolate a week of unattended runs against current interactive use. | *pending* |
| 3 | Phone sign-off works | **D's trial itself, 3–4 weeks.** Log each escalation/nudge: sent, seen, answered, time-to-answer, answered-from (phone vs keyboard). | *pending* |
| 5 | Kill leaves recoverable state | **30 min.** Run the worker on a toy task; `kill -9` mid-run; list orphan processes, worktree/branch state, and whether a retry collides. Repeat with SIGTERM. | **Done 2026-10-26 — assumption false today.** Ran the real worker seams (`run_claude`, `create_worktree`, `open_pr`) in a scratch repo with a fake `claude` that spawns two long-lived children. (a) Budget expiry returns promptly (3.0 s for a 3 s budget, no hang), but **both children survive as orphans**; the worktree is kept with partial work, no result contract, no handoff note, no notification. (b) **The task is wedged:** a retry fails on the existing worktree, and after removing it, on the existing branch — every later tick would error on the same task until a human cleans up. (c) **Killed between `git push` and `gh pr create`:** the branch is on origin with no PR; the retry is blocked by the worktree, so the red team's *duplicate* PR cannot happen today — the task wedges instead. (d) **Starting the session in its own process group and signalling the group** (`start_new_session=True` + `killpg`) cleaned up every child (2 → 0) — a cheap, proven fix. |
| 6 / 7 | Drift and silent stalls are visible | **15 min, desk check.** List every silent-failure path above (CLI drift, stale lock, dead push, all-runs-failing) and confirm each has a loud signal in the design; no code. | **Done 2026-10-26 — assumption false today: every path below is silent.** The worker reports by exit code (0 PR / 2 escalated / 3 timeout-or-error) and stdout JSON only; under launchd that reaches a log file, nothing else. Paths and the signal each needs: **CLI drift** (every run exits 3) → classify failures and alert after N consecutive, plus pin the worker's CLI version; **timeout** → write a handoff note and notify, instead of a silent `TimedOut`; **escalation** → push (D); **missed or stopped ticks** (sleep, dock hang, stale lock) → a heartbeat checked by something *not* on defiant — a Home Assistant "no heartbeat in N hours" alert, in the same style as the existing fail-alerts; **stale lock** → lock records PID + start time and is broken when the PID is gone; **push dropped off-LAN** (HA returns 200 either way) → every escalation is also a GitHub issue/PR mention, so GitHub's own notification is the second channel; **usage limit or auth fallback to API billing** → record which auth and limit state each run used, in its outcome; **STATUS.md drift** → loud by design (CI check), but regenerate it only on `main`, never on worker branches. |
| 10 | HA push off-LAN | **10 min.** With the phone off Wi-Fi, fire a test notification through the same HA service the alerts use. | *pending* |
| 9 | defiant capacity | **30 min.** Run the test suite while `mlx_lm.server` has Qwen3-Coder-Next loaded; record memory pressure and whether the Gmail/OPNsense jobs are delayed. | *pending* |

## Disposition

**Accepted by vpc, 2026-10-26.** Nothing is left dangling: each item is retired by a spike, escalated to A's spec, or accepted with its rationale.

| # | Disposition |
|---|---|
| 1 | **Spike before A.** If a cloud or Desktop scheduled task fits, A becomes "configure a routine" rather than "build a tick" — possibly a return to `plan-options` for A only. D is unaffected. |
| 2 | **Spike before A.** If headroom is thin, A runs only on the $100 API credits under the spend limit, or only overnight. |
| 3 | **Retired by D's trial**, which is exactly this measurement. A does not start until D's verdict is written down (answering the "no verdict" failure). |
| 4 | **Escalated to A's spec** as a hard requirement: the unattended worker never reads text not authored by vpc, runs with no user-level MCP servers (e.g. `--bare` / an explicit MCP config), and sign-offs count only from vpc's account. Also an ADR (trust boundary). |
| 5 | **Retired (spike done): false today.** Escalated to A's spec as requirements: run each session in its own process group and signal the group; a retry *resumes* an existing worktree/branch from its handoff note instead of refusing it; exactly-once PR creation keyed on the pushed branch (open the missing PR rather than re-cut). Part of this also belongs in D's "cheap worker fixes": the process-group kill and a handoff note + notification on timeout. |
| 6 / 7 | **Retired (desk check done): every path is silent today.** Escalated to A's spec: pinned worker CLI; failure classification + alert after N consecutive failures; an external heartbeat (HA "no heartbeat in N hours"); PID-stamped lock; GitHub as the second notification channel; auth/limit state in each run's outcome; STATUS.md regenerated only on `main`. D needs the GitHub second channel and the timeout notification from day one. |
| 8 | **Accepted** — D tests it directly at near-zero cost. |
| 9 | **Spike before A**; otherwise accept and pause the local model server during worker runs. |
| 10 | **Spike now** (10 min) — D's escalation push depends on it. |
| 11, 12 | **Accepted** with the harness/provider seams kept, so a terms change is a swap, not a rewrite. |
| 13 | **Accepted** — the validator and vpc's merge remain the gate; calibrating the validator from vpc's overrides is the mitigation. |
| 14 | **Accepted for D** (a compact spec, ADR 0024). Revisit for A. |

**What changed because of this pre-mortem:** D stands, with one 10-minute
check (HA push off-LAN) before it. A is no longer "build a launchd tick";
it is "first find out whether a scheduled task already does this", and
it may not start until D's trial verdict is recorded.
