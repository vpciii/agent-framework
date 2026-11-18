# Plan: A dispatch issue starts a worker run

- **Status:** Approved
- **Date:** 2026-11-18
- **Approved:** 2026-11-18, signed off by vpc, accepting the three
  readings of the spec the plan makes and five pull requests where the
  bet said three or four; the host stays open until the bet's spike
- **Author:** Claude (draft) — vpc is author of record
- **Spec:** ./spec.md
- **Related ADRs:** ADR 0004, ADR 0007, ADR 0010

> This plan freezes with its spec: editable while `Draft` / `Under
> review` / `Approved`, and a historical record once the PR that marks
> the spec `Implemented` merges (methodology §2, ADR 0007, ADR 0027). A contradiction found later goes to a test,
> a new spec, or an ADR — not back into this file.

## Approach

The dispatch tick is a new package, `agent_framework.dispatch`, that
does three small things around the worker that exists: it decides
whether an issue may start a run, it calls `work()`, and it reports back
on the issue. Everything a session is given, and everything that bounds
it, stays where it is — in `work()`, the confinement profile and the
handoff check — so a session started by the tick is launched by the same
code as one started by hand (R-9).

`work()` gains two keyword arguments whose defaults are today's
behavior (R-22): the commit to read `tasks.md` and `spec.md` from, and
what to do when the task's worktree or branch already exists (refuse, as
now, or continue). The tick passes both; a hand dispatch passes neither.
**Starting again is therefore an extension of the worktree and branch
handling, not a redesign of it** — the bet's third no-go condition does
not fire on this reading of the code.

### One pass

1. **Take the lock.** An advisory file lock (`flock`) on
   `.worktrees/dispatch.lock`, held for the life of the process. If it
   cannot be taken, another pass is running: send the heartbeat and
   exit. The operating system releases the lock when a process dies, so
   "is a run in progress" never rests on guessing whether a process id
   is still the same process.
2. **Recover a run that died.** The lock file's content names the run
   the last holder started (issue, spec, task, worktree, when). If it is
   there and not marked finished, that run died: stop anything left of
   its session's process group, write the handoff note, raise a
   `timeout` alert, comment on and close its issue, clear the content
   (R-15).
3. **Bring the checkout to `origin/main`** (R-8). Refuse when a tracked
   file is changed, when the fast-forward fails, or when the checkout's
   parent directory is inside another repository's working tree. If the
   fast-forward moved the checkout, the tick starts itself again once,
   so the pass runs the code it just fetched.
4. **Read the configuration.** No `[dispatch]` author, or
   `enabled = false`: say so, send the heartbeat, exit (R-3).
5. **List open `dispatch` issues** — number, title, author and creation
   time only. The body, comments and other labels are never requested,
   so there is nothing to keep out of the brief (R-6).
6. **Decide on the oldest** (R-2): author, then title pattern, then the
   task at the fetched commit of `origin/main` (exists, not done, claims
   a criterion), then the branch on the remote (R-16).
7. **Refuse**, or **claim and run.** A refusal removes the label,
   comments and closes. A claim removes the label first (R-4), writes
   the run into the lock file, calls `work()` at that commit, then
   comments with the outcome and closes (R-11), and marks the run
   finished.
8. **Send the heartbeat** (R-20) and exit.

### What "starting again" does

Decided from what is on disk and on the remote, in this order:

| What is found for the task | What a dispatch issue does |
|---|---|
| An open pull request for its branch | Refused, naming the pull request (R-16) |
| Its branch on the remote, no open pull request | The pull request is opened; no session (R-16) |
| A local worktree holding a handoff note | A session resumes in it (R-14) |
| A local worktree or branch, no handoff note | Starts afresh; the old branch is renamed, its worktree removed (R-17) |
| Nothing | A fresh worktree at the fetched commit, as today |

- **Resume.** The handoff note is read into the brief under its own
  heading, then removed from the worktree along with any result file the
  earlier session left, so a resumed session cannot commit the one or be
  judged by the other. `HANDOFF.md` also joins the result file in the
  repository's exclude file. The branch keeps the base it was cut from.
- **Afresh.** The old branch is renamed to
  `attempt/<slug>-<task>-<UTC time>`; nothing is deleted.
- **The pull request without a session.** Its body uses the result file
  if the worktree still holds one, and otherwise says the pull request
  was opened after an interrupted run.

### What a pass reports

- **On the issue:** one comment from a fixed set of wordings, filled
  with values the code computed — the pull request's address, the
  alert's address, or which rule refused it (R-11, R-12).
- **A `failed` alert** for a run that raised an error (R-13). The kind
  is read from the session's exit and the end of its record against one
  table of patterns: login, usage limit, CLI version, other. The alert
  names the kind, the exit status and where the session record is on
  that Mac; it never quotes the record or the session's output.
- **Alerts the tick itself raises** (the checkout cannot be used, the
  CLI version differs, three failed passes) use one key each, so there
  is one open issue per condition. `notify` gains a switch so that a
  condition already reported is not pushed to the phone again every
  ten minutes.
- **Failed passes** are counted in a small state file beside the lock
  (R-19).

### Three readings of the spec this plan makes

- **A pass that refuses the checkout (R-8) is not a completed pass.** It
  raises its own alert at once and sends no heartbeat. It is not counted
  toward R-19's three, which is for a tick that cannot reach GitHub.
- **A pass that finds another pass running is a completed pass** and
  sends the heartbeat: the tick is alive.
- **R-7 does not lean on R-8.** The brief is built by reading the two
  files from the fetched commit, not from the checkout's working files,
  so it is right even if the two ever differ. The worker eval already
  builds a brief this way (`brief_at_start`); that code moves into the
  worker and both use it.

## Components touched

- `src/agent_framework/dispatch/` (new) — `issue.py` (the title pattern
  and the acceptance decision, pure), `tick.py` (one pass), `lock.py`
  (the file lock and the run it names), `report.py` (the comment
  wordings, the failure table, the failed-pass count, the heartbeat),
  `__main__.py` (the command).
- `src/agent_framework/worker/orchestrator.py` — `work()` takes the
  commit to read the artifacts at and what to do with an existing
  worktree; today's refusal is the default.
- `src/agent_framework/worker/worktree.py` — cut a worktree at a given
  commit; rename a branch aside; exclude `HANDOFF.md`.
- `src/agent_framework/worker/brief.py` — read a task from a commit; the
  resume heading.
- `src/agent_framework/worker/handoff.py` — open a pull request for a
  branch that is already pushed.
- `src/agent_framework/worker/session.py` — report the installed CLI's
  version (moved from the worker eval, which keeps using it).
- `src/agent_framework/evals/worker/case.py` — `brief_at_start` calls
  the moved code; no behavior change.
- `src/agent_framework/alerts.py` — the `failed` kind; the switch that
  skips the push for a condition already reported.
- `src/agent_framework/project.py` — the `[dispatch]` table.
- `src/agent_framework/artifacts.py` — whether a task is marked done.
- `pyproject.toml` — the `agent-framework-dispatch` command.
- `agent-framework.toml` — this repository's `[dispatch]` table. A
  protected path: changed by vpc's own pull request, never a worker's.
- `docs/architecture.md`, `docs/adoption.md` — the component, the trust
  boundary (ADR 0010), the launchd agent and the heartbeat check as
  settings outside the repository, and how to set it up.
- `tests/dispatch/` (new), and additions under `tests/worker/`.

## Data model changes

**Configuration** (`agent-framework.toml`), all optional:

```toml
[dispatch]
author = "vpciii"              # the one account whose issues count; absent = off
enabled = true                 # false = off, without removing the author
worker_cli_version = "2.1.325" # absent = any version runs
```

**The lock file** (`.worktrees/dispatch.lock`, never committed) holds
the run in progress, or nothing:

```json
{"pid": 4812, "started": "2026-11-20T14:02:11Z", "issue": 151,
 "spec": "dispatch-from-issue", "task": "T-2",
 "worktree": ".worktrees/dispatch-from-issue-t-2", "session_pgid": 4830}
```

**The state file** (`.worktrees/dispatch-state.json`, never committed):

```json
{"failed_passes": 0}
```

**Environment:** `AF_HA_HEARTBEAT_URL`, beside `AF_HA_WEBHOOK_URL`, in
the same file outside the repository. No secret enters the repository.

Data sensitivity: nothing new is published. Issue numbers and addresses
are already public; the lock and state files stay on the Mac.

## API changes

```
agent-framework-dispatch [--roster FILE] [--timeout SECONDS] [--spend-limit USD]
python -m agent_framework.dispatch ...
    One pass. Exit 0 when the pass completed (whatever it found or
    however a run ended), 1 when the pass failed, 2 when it refused its
    checkout. The limits default to the worker's own (1800 s, $10).
```

`work()`'s two new keyword arguments default to today's behavior, and
the worker's own command line does not change.

The title pattern, fixed in code:
`^[a-z0-9]+(-[a-z0-9]+)* T-[0-9]+$`.

## Alternatives considered

- **A process-id lock, as the pre-mortem worded it.** Rejected for an
  operating-system file lock whose content names the process: a reused
  process id cannot make a dead run look alive.
- **A second code path that launches sessions for the tick.** It would
  keep `work()` untouched. Rejected: two launchers drift, and R-9 is
  only true by construction when there is one.
- **Trust the checkout's files for the brief once it is at
  `origin/main`.** Simpler. Rejected: R-7 would then be true only while
  R-8's check is right.
- **Keep the handoff note in the worktree on resume.** Rejected: the
  session could commit it, and it names a path on the Mac.
- **A wrapper script that updates the checkout before starting
  Python**, as the nudge's launchd agent does. Rejected: the rule that a
  pass refuses a changed or nested checkout needs tests, so it lives in
  code; the tick restarts itself when the update moved it.
- **Labels for state** (`dispatch-running`, `dispatch-refused`).
  Rejected: closing with a comment says the same with nothing to keep in
  step.

## Risks

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| **The host.** `claude -p` under launchd on defiant is unverified, and so is everything else there: the bet's spike has not been run. What is known to work — the nudge's launchd agent, the env file and all six worker runs — is on *enterprise* (checked 2026-11-18: the nudge's agent is loaded there). The options round described the tick as "on defiant, beside the nudge"; whether defiant has a nudge agent of its own was not checked | High that something on defiant needs setting up | High — no run starts | The spike comes before the delivery task. Nothing in the code depends on the host. If defiant fails the spike, the bet's first no-go applies and the host is reopened with vpc |
| A session's own login expires, or the Max plan's allowance runs out, with no one there | Medium | Medium — runs stop | The `failed` alert names login or usage limit; three failed passes alert; the heartbeat covers a tick that stops |
| The failure patterns do not match what the CLI really prints | Medium | Low — the alert says "other" | "Other" still alerts, with the exit status and where the record is. The patterns are one table, corrected from the first real failure |
| The CLI updates itself and no longer matches the configured version | High | Low — runs stop until the version is changed by pull request | The alert names both versions. The delivery turns the CLI's self-update off on that Mac and records it as a setting outside the repository |
| A resumed branch is behind `main` and its pull request conflicts | Medium | Low | The pull request shows it; vpc resolves it or dispatches afresh |
| A merged change breaks the tick, which then cannot run the fix | Low | Medium | The heartbeat stops and alerts; the fix is merged from anywhere and the next pass fetches it. A pass that cannot even start is what the heartbeat is for |
| The Mac sleeps and the heartbeat check raises a false alert | Medium | Low | Settled at delivery: the check's hours, or the Mac kept awake |
| Escalation files written into the checkout accumulate as untracked files | High | Low | Untracked files do not stop a pass (R-8 is about tracked files); clearing them is noted in the docs |

## Rollout

Five pull requests. The first four are code with no network beyond the
package index and are for dispatch to the worker, by hand, one at a
time; the fifth is the human's.

1. **The decision.** The `[dispatch]` table, the title pattern, whether
   a task is done, and the acceptance decision as pure code (SC-1,
   SC-2, SC-4's refusal of a longer title).
2. **Starting again, in the worker.** `work()` at a commit; resume;
   afresh; the pull request for a pushed branch; hand dispatch unchanged
   (SC-5, SC-11, SC-13, SC-14, SC-18).
3. **The pass.** The lock and recovery of a dead run; the checkout; the
   claim; the call to `work()`; the comment and the close (SC-3, SC-4,
   SC-6, SC-7, SC-8, SC-9, SC-12).
4. **When it stops working.** The `failed` alert and its kinds; the CLI
   version; three failed passes; the heartbeat (SC-10, SC-15, SC-16,
   SC-17).
5. **Delivery — not for dispatch.** The spike on the host; this
   repository's `[dispatch]` table; the launchd agent; the heartbeat
   check in Home Assistant, on vpc's word; `docs/architecture.md` and
   `docs/adoption.md`; the spec's live check.

That is one more pull request than the bet's "three or four". The code
is four; the fifth is setup and docs.

Nothing changes for anyone until step 5: with no `[dispatch]` author the
tick does nothing, and no schedule runs it. **Undo:** unload the launchd
agent, or merge `enabled = false`, or remove the table; hand dispatch is
untouched throughout.

## Observability

- Each pass logs one line per step to the launchd agent's log file: what
  it found, what it decided, how the run ended.
- The issue's comment and the alerts are the record vpc sees.
- The heartbeat is the signal that the tick is alive; the state file
  holds the failed-pass count.
- The session record and the worker's own log lines are unchanged.

## Test strategy

- **Unit, pure:** the title pattern, over accepted and refused shapes
  including text after the task id, other separators and other cases;
  the acceptance decision over every refusal in R-2; the failure table;
  the failed-pass count across failures and a success.
- **Integration, fake tracker and fake session, a real repository in
  `tmp_path`:** a pass from start to finish for each ending; the label
  removed before the session and no session when that fails; marker
  text in an issue's body, comments and labels absent from the brief,
  the command line, the environment and every comment the tick writes;
  the brief built from the fetched commit when the working file
  differs; resume, afresh and the pull request for a pushed branch; the
  recorded commands containing no merge, approve or review.
- **The lock, with real processes:** a second pass while the first holds
  the lock starts nothing; a lock file left by a process that was
  killed is recovered by the next pass.
- **The checkout:** refused when a tracked file is changed, when the
  fast-forward fails, and when it is nested; not refused for an
  untracked file.
- **Unchanged behavior:** the worker's existing tests pass untouched,
  and one test compares the commands a hand dispatch issues before and
  after for a task with nothing left behind.
- **Not testable here, so in the spec's live check:** launchd starting a
  session that is logged in; the phone flow; the heartbeat check
  outside the repository.
