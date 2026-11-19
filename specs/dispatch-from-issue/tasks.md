# Tasks: A dispatch issue starts a worker run

- **Status:** Approved
- **Approved:** 2026-11-18, signed off by vpc, accepting the two
  departures from the plan described below (eight tasks where its
  rollout lists five; the existing `dispatch.py` moved into the new
  package)
- **Amended:** 2026-11-19 — T-9 added after T-6's review, and T-8 made
  to wait for it (*One task added*, below). Signed off by vpc
  2026-11-19.
- **Corrected:** 2026-11-19 — T-9's *Done when* contradicted itself and
  the worker escalated (#160); one sentence changed (the tally's last
  row). Signed off by vpc 2026-11-19.
- **Corrected again:** 2026-11-19 — T-9 named `ps` as how to tell the
  session's process from another, and the worker's sandbox cannot run
  `ps`; the worker escalated (#162). The session now holds a lock
  instead (vpc's choice, 2026-11-19). Signed off by vpc 2026-11-19.
- **Corrected a third time:** 2026-11-19 — the brief had the tick take
  the session lock and did not say what a pass does when it cannot. The
  worker chose to fail the pass; the validator rejected #164 for
  behaviour the brief did not ask for and no test covered. The brief
  now states it and asks for the test. Signed off by vpc 2026-11-19.
- **Spec:** ./spec.md
- **Plan:** ./plan.md

PR-sized tasks derived from the plan. Each task traces to ≥1 success
criterion — the tests it must make pass cite those ids — and replaces its
`*(pending)*` Traceability rows as its tests land. Mark a task `[x]` with
its merged PR number when done. Task PRs carry a `Satisfies:` declaration
and name `specs/dispatch-from-issue/` in their body.

**DAG:** one at a time, in order. T-1 and T-2 touch different code but
neighbouring Traceability rows, so they are not run side by side. T-2 →
T-3; T-1 → T-4; T-5 after T-3 and T-4; T-5 → T-6 → T-7 (all three change
`tick.py`); T-9 after T-7 (it changes `tick.py` too); T-8 after T-9.

**Criterion coverage:** SC-1 → T-1 (the decision), T-4 (no session for a
refused issue), T-5 (a session for the accepted one, the oldest only) ·
SC-2 → T-1 (the configuration), T-4 · SC-3 → T-4 (the lock), T-5 (the
claim) · SC-4 → T-1 (the longer title), T-5 (the marker text) · SC-5 →
T-2 · SC-6 → T-6 · SC-7, SC-8 → T-5 · SC-9 → T-4 (refusals), T-5
(endings) · SC-10 → T-7 · SC-11, SC-14 → T-3 · SC-12 → T-6, T-9 (recovery made safe) · SC-13 → T-3
(the worker's half), T-5 (the comment) · SC-15, SC-16 → T-7 · SC-17 →
T-7, T-8 (the live half) · SC-18 → T-2 (the same commands), T-3 (still refuses). A criterion
claimed by more than one task is complete when the last of them merges;
each adds its own test to the criterion's Traceability row.

**Two departures from the plan, accepted with this list.**

- **Eight tasks where the plan's rollout lists five.** The six tasks
  dispatched for the worker eval were each written for about 300 lines
  and came back at 350 to 570, tests included, and the one that passed
  480 drew a REJECT for its size. On that evidence the plan's step 2
  (starting again) is two tasks here — the worker reading its task at a
  commit (T-2), then what it does with what an earlier run left (T-3) —
  and its step 3 (the pass) is three: a pass that refuses (T-4), a pass
  that runs (T-5), and the checkout and a run that died (T-6). Steps 1,
  4 and 5 are T-1, T-7 and T-8 with their content unchanged. No
  criterion moves out of the plan's order except that SC-6 and SC-12
  land after the pass that runs, not with it.
- **`src/agent_framework/dispatch.py` already exists.** It holds the
  function that resolves a role to its model, and the validator imports
  it. The plan puts the tick in a package of the same name without
  saying what happens to the file. T-1 moves the file, unchanged, to
  `src/agent_framework/dispatch/__init__.py`, so every existing import
  and every name in the plan (`agent_framework.dispatch`,
  `python -m agent_framework.dispatch`) stays true.

**One thing the plan leaves to the tasks.** The lock file names the
session's process group, and `work()` does not report it. T-6 has the
session launcher (`run_claude`) take an optional callback that is told
the process group when the session starts, and the tick passes it in
through `work()`'s existing `session_run` argument. `work()` keeps the
plan's two new keyword arguments and no third.

**Dispatch.** T-1 to T-7 are code and tests with no network beyond the
package index, and are for dispatch to a worker session by hand, from
the main checkout, one at a time. As for the worker eval, note for each
whether it reached an open pull request, whether that merged without an
interactive session reworking it, what the session record says it cost,
and which alert fired. **T-8 is not for dispatch:** it needs the host,
`agent-framework.toml` is a protected path, and the Home Assistant
change is made on vpc's word.

**Dispatch tally.** Cost and time are what the session record reports.

| Task | Pull request | Merged without rework | Time | Cost | Alert |
|---|---|---|---|---|---|
| T-1 | #151 | yes | 3m 40s | $1.05 | none |
| T-2 | #152 | yes | 3m 19s | $0.97 | none |
| T-3 | #153 | yes | 3m 34s | $1.21 | none |
| T-4 | #154 | yes | 4m 12s | $1.24 | none |
| T-5 | #156, opened by hand | yes — the worker's changes, unchanged | 5m 31s | $1.48 | escalation (#155): the session's own permission layer refused `git commit` |
| T-6 | #157 | yes | 7m 18s | $2.13 | none |
| T-7 | #158 | yes | 5m 37s | $1.60 | none |
| T-9, first run | none | — | 29s | $0.29 | escalation (#160): the task as written could not be met — a lock file with no start time was to stop nothing, and T-6's test, which writes one and expects its group stopped, was to pass unmodified |
| T-9, second run | none | — | 44s | $0.44 | escalation (#162): the brief had the start time read from `ps`, which is setuid and cannot run in the worker's sandbox, so its own tests could not pass there |

T-1 to T-7: seven tasks, seven pull requests merged with none of the
worker's code reworked, $9.68, about 33 minutes of session time, one
alert. T-9's first two runs add $0.73 and two more alerts, and no code.

- **T-5's escalation was not about the contract.** The work was done
  and the gate green, but the commit command was refused: its message
  held text the CLI's shell check wants a person to approve (angle
  brackets, braces beside quotes), a headless session has nobody to
  approve, and the refusal told the session not to try again. On vpc's
  word the chief committed the worker's changes from its worktree,
  unchanged, ran `check_handoff` on the commit (no findings) and the
  gate (green), and opened #156. T-6 and T-7 met the same refusal and
  worked round it. An unattended run that does not work round it ends
  as T-5 did: an alert and no pull request. Not yet fixed.
- **Sizes.** Lines added, tests included: 289 (T-2) to 701 (T-4); five
  of the seven passed 400. The validator rejected none for size.
- **T-9's escalations were about the contract, and were right.** The
  chief first wrote a *Done when* that asked for two things at once,
  then a brief that named a program the sandbox cannot run. Each time
  the session stopped before writing code and asked. Letting `ps` out
  of the sandbox was weighed and not done: the profile forbids any
  unsandboxed command (ADR 0007). The lesson for a brief: name a
  mechanism only after running it where the worker will.
- **Found in review, not by a test.** T-6's recovery trusts two things
  the plan did not question; T-9 below is the fix. `worker/__main__.py`
  prints an outcome it does not know as `timed_out`, and it does not
  know `PrAlreadyOpen`; nothing reaches that today, since the command
  never passes `existing="continue"`.

**One task added (2026-11-19).** T-6 does what the plan's step 2 says,
and reading it showed two cases the plan did not consider. Neither can
happen until the schedule is on, so T-9 fixes both before T-8.

- **The recorded process group may no longer be the session's.** A run
  most often dies because the Mac restarts or sleeps, and after a
  restart the number in the lock file may belong to another program,
  which recovery would stop. The plan guards the lock against a reused
  process id (*Alternatives considered*) but not the stop. T-9 has the
  session hold a lock of its own: free means the session is gone, and
  after a restart it is always free. It errs towards doing nothing — a
  child that outlives the session's main process and no longer holds
  the lock is left running, not stopped. Whether the real CLI keeps the
  inherited lock open is not something a test with a stand-in can show;
  it is checked in T-8, and if it does not, recovery stops nothing,
  which is the safe failure.
- **A run can die before its worktree exists.** The run is recorded
  before `work()` cuts the worktree. Recovery then creates the folder to
  hold the handoff note, and the next dispatch issue takes that folder
  for a worktree to resume in — a plain folder inside the checkout,
  where the session's git commands act on the checkout itself.

Names the later tasks rely on, fixed here so each brief stands alone:
`work(..., at=None, existing="refuse")`; the outcome `PrAlreadyOpen`;
`agent_framework.dispatch.issue.decide`; `agent_framework.dispatch.tick.run_pass`.

---

### [x] T-1 — The decision: the `[dispatch]` table, the title, and whether an issue may start a run (#151)
- **Satisfies:** SC-1, SC-2, SC-4
- **Depends on:** —
- **Touches:** `src/agent_framework/dispatch.py` →
  `src/agent_framework/dispatch/__init__.py` (moved, unchanged),
  `src/agent_framework/dispatch/issue.py` (new),
  `src/agent_framework/project.py`, `src/agent_framework/artifacts.py`,
  `tests/dispatch/test_issue.py` (new), `tests/test_project_config.py`,
  `specs/dispatch-from-issue/spec.md` (Traceability rows)
- **Brief:** Pure code; no git, no network, no session. First move
  `dispatch.py` to `dispatch/__init__.py` with `git mv`, changing only
  its relative imports; `tests/test_dispatch.py` and the validator's
  import must pass unmodified. Add the optional `[dispatch]` table to
  the project configuration as the plan's *Data model changes* gives it:
  `author` (absent means off), `enabled` (default true),
  `worker_cli_version` (absent means any); a wrong type is refused when
  the file is loaded, as the other tables' are. In `artifacts.py`, say
  whether a task's heading in `tasks.md` is marked done. In
  `dispatch/issue.py`: the title pattern from the plan's *API changes*,
  matched against the whole title with nothing trimmed or lowered; and
  `decide`, which takes one issue (number, title, author, when it was
  opened), the dispatch configuration, and the text of the named spec's
  `tasks.md` as it is on `origin/main` (or nothing, when the spec is not
  there), and returns either the spec slug and task id to run or one
  refusal from a fixed set: dispatch is off, another author, the title's
  shape, an unknown spec, an unknown task, a task already done, a task
  that claims no criterion. Checks run in that order, so an issue from
  another author is refused before its title is looked at. A refusal
  carries a reason code and nothing taken from the issue. Add the choice
  of the oldest issue from a list.
- **Done when:** tests citing SC-1 show `decide` accepts only the
  configured author's well-formed title naming a task that exists, is
  not done and claims a criterion, refuses each other case with its own
  reason, and that the oldest of several is chosen; tests citing SC-2
  show no author, and `enabled = false`, are each reported as off;
  tests citing SC-4 show a title with text after the task id, with
  another separator, with other letter case, and with leading or
  trailing space is refused. The gate passes.

### [x] T-2 — The worker reads its task at a commit (#152)
- **Satisfies:** SC-5, SC-18
- **Depends on:** —
- **Touches:** `src/agent_framework/worker/orchestrator.py`,
  `src/agent_framework/worker/brief.py`,
  `src/agent_framework/worker/worktree.py`,
  `src/agent_framework/evals/worker/case.py`,
  `tests/worker/test_at_commit.py` (new),
  `specs/dispatch-from-issue/spec.md` (Traceability rows)
- **Brief:** `work()` gains a keyword argument `at`, a commit, default
  none. With none, nothing changes: the task is parsed from the working
  files and the worktree is cut from the freshly fetched `origin/main`,
  as today. With a commit, the task is parsed from `tasks.md` and
  `spec.md` as they are *at that commit* — read with `git show`, never
  from the working files — and the worktree is cut at that same commit
  with no further fetch. The code that builds a brief from a commit
  already exists for the worker eval (`brief_at_start` in
  `evals/worker/case.py`): move the reading into `worker/brief.py` and
  have `brief_at_start` call it, with its behavior and error messages
  unchanged (the eval's tests pass unmodified). A commit at which the
  spec or the task is missing is refused before any worktree exists.
  Also add `HANDOFF.md` to the entries the worktree code writes to the
  repository's exclude file, beside the result file.
- **Done when:** a test citing SC-5 shows that when the checkout's
  working copy of `tasks.md` differs from the one at the commit given,
  the brief the session receives is the one built from the commit, and
  the worktree's head is that commit; a test citing SC-18 records the
  commands `work()` issues for a task with nothing left behind and no
  new argument and shows they are the list issued before this change,
  written out in the test. The worker's and the eval's existing tests
  pass unmodified. The gate passes.

### [x] T-3 — Starting again: resume, afresh, and a branch already pushed (#153)
- **Satisfies:** SC-11, SC-13, SC-14, SC-18
- **Depends on:** T-2
- **Touches:** `src/agent_framework/worker/orchestrator.py`,
  `src/agent_framework/worker/worktree.py`,
  `src/agent_framework/worker/brief.py`,
  `src/agent_framework/worker/handoff.py`,
  `src/agent_framework/worker/types.py`,
  `tests/worker/test_starting_again.py` (new),
  `specs/dispatch-from-issue/spec.md` (Traceability rows)
- **Brief:** `work()` gains a keyword argument `existing`, `"refuse"`
  (the default: today's behavior, unchanged) or `"continue"`. With
  `"continue"`, what happens is decided from the remote and the disk in
  the order of the plan's table, *What "starting again" does*: (1) an
  open pull request for the task's branch — no session; return a new
  outcome, `PrAlreadyOpen`, carrying the pull request's address;
  (2) the branch on the remote with no open pull request — no session;
  open the pull request and return `PrOpened`, its body taken from the
  result file if the worktree still holds one and otherwise saying it
  was opened after an interrupted run, then remove the worktree if
  there is one; (3) a local worktree holding `HANDOFF.md` — resume: read
  the note, remove it and any result file from the worktree, and run a
  session in that worktree on its branch with a brief that is the usual
  one plus the note under its own heading; the branch keeps the base it
  was cut from, so the handoff note and the handoff check measure from
  the merge base with `origin/main`; (4) a local worktree or branch with
  no note — start afresh: rename the branch to
  `attempt/<slug>-<task>-<UTC time>`, remove the worktree, and carry on
  as for a task with nothing left; (5) nothing — as today. Everything
  after the session (the handoff check, the push, the pull request, the
  alerts) is the code that runs today. Tests use a real repository with
  a bare remote in `tmp_path`, a fake `gh` and a fake session.
- **Done when:** tests citing SC-11 show that after a run stopped at
  its time budget, and after one stopped at its spend limit, `work()`
  with `existing="continue"` runs a session in the same worktree on the
  same branch, its brief contains the note, and the note and the old
  result file are gone before the session starts; tests citing SC-13
  show one pull request and no session for a pushed branch, and
  `PrAlreadyOpen` with the address and no session when one is open;
  tests citing SC-14 show that for a worktree left by an escalation,
  and for one left by a refused handoff, a session runs in a fresh
  worktree and the earlier commits are reachable from an `attempt/`
  branch; a test citing SC-18 shows the default still refuses an
  existing worktree and an existing branch with today's messages. The
  gate passes.

### [x] T-4 — A pass that refuses: the command, the lock, the list, the comment and the close (#154)
- **Satisfies:** SC-1, SC-2, SC-3, SC-9
- **Depends on:** T-1
- **Touches:** `src/agent_framework/dispatch/tick.py` (new),
  `src/agent_framework/dispatch/lock.py` (new),
  `src/agent_framework/dispatch/report.py` (new),
  `src/agent_framework/dispatch/__main__.py` (new), `pyproject.toml`,
  `tests/dispatch/test_pass_refuses.py` (new),
  `tests/dispatch/test_lock.py` (new), `tests/test_entry_points.py`,
  `specs/dispatch-from-issue/spec.md` (Traceability rows)
- **Brief:** The command `agent-framework-dispatch` (and
  `python -m agent_framework.dispatch`) with the plan's options, making
  one pass through `tick.run_pass` and exiting 0 for a completed pass
  and 1 for a failed one. This task builds every step of the plan's
  *One pass* that does not start a session; an accepted issue is left
  exactly as it was found, for T-5. In order: take an advisory file
  lock (`fcntl.flock`, not blocking) on `.worktrees/dispatch.lock`, held
  until the process exits — if it is held, log that another pass is
  running and end as a completed pass; read the configuration — if
  dispatch is off, log why and end without listing anything; fetch
  `origin/main` and resolve the commit; list open issues labelled
  `dispatch` through a tracker seam that asks for the number, title,
  author and creation time **and nothing else** (never the body, the
  comments or the labels); take the oldest; read the named spec's
  `tasks.md` at the fetched commit and call T-1's `decide`. A refusal
  removes the `dispatch` label, writes one comment and closes the
  issue. The comment is one of a fixed set of wordings in `report.py`,
  one per reason code; it contains no text from the issue, the title
  included. A fetch or a listing that fails is a failed pass. `lock.py`
  also reads and writes the lock file's content — the run in progress,
  in the plan's shape — for the tasks that follow. Every step logs one
  line. Tests: a fake tracker and a real repository in `tmp_path`; for
  the lock, a second real process.
- **Done when:** tests citing SC-1 show that for each refused case a
  pass starts no session; tests citing SC-2 show that with no author,
  and with dispatch switched off, the tracker is never asked for
  issues and the pass says why; a test citing SC-3 shows a pass made
  while another process holds the lock lists nothing and leaves its
  issue open and labelled; tests citing SC-9 show each refusal leaves
  exactly one comment, the label removed and the issue closed, and that
  marker text carried in the issue's title is not in the comment. The
  entry-point test covers the new command. The gate passes.

### [x] T-5 — A pass that runs: the claim, the session, the outcome on the issue (#156)
- **Satisfies:** SC-1, SC-3, SC-4, SC-7, SC-8, SC-9, SC-13
- **Depends on:** T-3, T-4
- **Touches:** `src/agent_framework/dispatch/tick.py`,
  `src/agent_framework/dispatch/report.py`,
  `tests/dispatch/test_pass_runs.py` (new),
  `specs/dispatch-from-issue/spec.md` (Traceability rows)
- **Brief:** For an accepted issue: remove the `dispatch` label first —
  if that fails, start nothing, leave the issue, and end as a failed
  pass; write the run into the lock file; call `work()` with the spec
  slug and task id `decide` returned, the roster, the limits from the
  command line, `at` the fetched commit and `existing="continue"`, and
  nothing else of the tick's own — no other argument differs from a
  hand dispatch; then write one comment, close the issue, and mark the
  run finished in the lock file. The comment is fixed wording per
  outcome plus values the code computed: the pull request's address for
  `PrOpened`; for `PrAlreadyOpen`, that the issue was refused and the
  address of the open pull request; the alert's address for an
  escalation, a timeout, the spend limit and a refused handoff; for a
  run that raised an error, that it ended in an error (T-7 adds its
  alert). A run that raises still gets its comment and its close, and
  the pass is a completed one. Only the oldest acceptable issue is
  acted on; the others are left for later passes. Tests: the fake
  tracker's issues carry marker text in their body, comments and
  labels; a fake session records its brief, command line and
  environment; a recording runner captures every `git` and `gh`
  command.
- **Done when:** tests citing SC-1 show a session starts for the
  accepted issue and, with several, only for the oldest; tests citing
  SC-3 show the label is removed before the session starts and that a
  failed removal starts none; a test citing SC-4 shows none of the
  marker text reaches the brief, the command line or the environment;
  a test citing SC-7 shows the profile arguments, environment, time
  budget, spend limit and model the session is launched with are those
  of a hand dispatch of the same task; a test citing SC-8 shows that
  across a pull request, an escalation, a timeout, the spend limit, a
  refused handoff and an error, no merge, approve or review command is
  issued and no branch but the task's is pushed; tests citing SC-9 show
  each of those endings leaves exactly one comment naming the pull
  request, the alert or the reason, with none of the marker text, and a
  closed issue; a test citing SC-13 shows the comment for an open pull
  request names it. The gate passes.

### [x] T-6 — The checkout, and a run that died (#157)
- **Satisfies:** SC-6, SC-12
- **Depends on:** T-5
- **Touches:** `src/agent_framework/dispatch/tick.py`,
  `src/agent_framework/dispatch/lock.py`,
  `src/agent_framework/dispatch/report.py`,
  `src/agent_framework/worker/session.py`,
  `tests/dispatch/test_checkout.py` (new),
  `tests/dispatch/test_recovery.py` (new),
  `specs/dispatch-from-issue/spec.md` (Traceability rows)
- **Brief:** Two steps of the plan's *One pass*, placed where it puts
  them. **The checkout (step 3):** after the lock and before the
  configuration is read, bring the checkout to `origin/main` by
  fast-forward. Refuse — start nothing, raise an alert through `notify`
  under one key for the condition, send nothing else, exit 2 — when a
  tracked file is changed, when the fast-forward fails, or when the
  checkout's parent directory is inside another repository's working
  tree. An untracked file does not refuse. If the fast-forward moved
  the checkout, the command starts itself again once (releasing the
  lock first, and marked so it cannot do so twice), so the pass runs the
  code it fetched. **A run that died (step 2):** `run_claude` takes an
  optional callback told the session's process group as it starts; the
  tick passes it through `work()`'s `session_run` argument and records
  the group in the lock file. A pass that takes the lock and finds a
  run recorded and not marked finished treats it as dead: stop anything
  left of that process group, write the handoff note into the run's
  worktree with the worker's own `write_handoff_note`, raise a
  `timeout` alert, comment on and close the issue the run had claimed,
  and clear the record — then carry on with the pass. Tests for
  recovery use a real process that takes the lock, records a run and is
  killed.
- **Done when:** tests citing SC-6 show a pass starts nothing, lists
  nothing, raises one alert and exits 2 for a changed tracked file, for
  a checkout that cannot be fast-forwarded and for a nested checkout,
  is not refused for an untracked file, and otherwise has the checkout
  at `origin/main` before the tracker is asked for anything; tests
  citing SC-12 show that after a holder is killed the next pass clears
  the record, leaves a handoff note in the worktree, raises a `timeout`
  alert and comments on and closes the claimed issue, and that a
  dispatch issue for the same task then resumes in that worktree. The
  gate passes.

### [x] T-7 — When it stops working: the `failed` alert, the CLI version, three failed passes, the heartbeat (#158)
- **Satisfies:** SC-10, SC-15, SC-16, SC-17
- **Depends on:** T-6
- **Touches:** `src/agent_framework/dispatch/tick.py`,
  `src/agent_framework/dispatch/report.py`,
  `src/agent_framework/alerts.py`,
  `src/agent_framework/worker/session.py`,
  `src/agent_framework/evals/worker/run.py`,
  `tests/dispatch/test_failures.py` (new),
  `tests/dispatch/test_heartbeat.py` (new),
  `specs/dispatch-from-issue/spec.md` (Traceability rows)
- **Brief:** Four things in `report.py`, wired into the pass. **The
  `failed` alert:** a run that raised an error raises one alert
  labelled `failed`, keyed by the task. Its kind — login, usage limit,
  CLI version, other — is read from the session's exit and the end of
  its record against one table of patterns kept in one place. The alert
  names the kind, the exit status and where the session record is on
  that Mac; it never quotes the record or the session's output. The
  issue's comment for this ending now gives the alert's address. **The
  CLI version:** move `claude_code_version` from the worker eval to
  `worker/session.py` (the eval imports it from there). When the
  configuration names a version and the installed CLI reports another,
  the pass starts no session and raises a `failed` alert naming both;
  with none configured the session starts. **Failed passes:** count
  them in `.worktrees/dispatch-state.json`; the third in a row raises
  one `failed` alert, later ones raise none, and a completed pass sets
  the count to zero. A pass that refused its checkout is not counted.
  **The heartbeat:** a completed pass — including one that found
  nothing, one that found dispatch off and one that found another pass
  running — sends one request to the address in `AF_HA_HEARTBEAT_URL`;
  a failed pass and a pass that refused its checkout send none; no
  address, or an address that refuses or times out, changes neither the
  outcome nor the exit status. Also give `notify` a switch that skips
  the push when the condition's issue is already open, and use it for
  every alert the tick itself raises (the checkout, the CLI version,
  three failed passes), so one condition is not pushed to the phone
  every ten minutes.
- **Done when:** tests citing SC-10 show one `failed` alert per failed
  run, and that a login failure, a usage limit and a CLI version
  mismatch are each named as such and anything else as "other"; tests
  citing SC-15 show no session and an alert naming both versions when
  they differ, and a session when none is configured; a test citing
  SC-16 shows exactly one alert at the third failed pass in a row, none
  at the fourth, and the count starting again after a completed pass; tests
  citing SC-17 show one heartbeat for a completed pass with and without
  an issue, none for a failed pass, and the same outcome and exit
  status with no address and with one that refuses. The gate passes.

### [ ] T-9 — Recovery stops only its own session, and resumes only a real worktree
- **Satisfies:** SC-12
- **Depends on:** T-7
- **Touches:** `src/agent_framework/dispatch/tick.py`,
  `src/agent_framework/dispatch/lock.py`,
  `src/agent_framework/worker/session.py`,
  `tests/dispatch/test_recovery.py`,
  `specs/dispatch-from-issue/spec.md` (Traceability rows)
- **Brief:** Two changes to the recovery T-6 built (`_Pass.recover` in
  `tick.py`), and the one thing they bring with them where a run is
  started; nothing else about a pass changes. **Stop only the
  session.** The session holds a second lock for as long as it lives.
  Before starting a session the tick opens
  `.worktrees/dispatch-session.lock` and takes an advisory lock on it
  (`fcntl.flock`, as for the tick's own lock); `run_claude` takes an
  optional argument naming file descriptors the session inherits, and
  the tick passes this one through the `session_run` argument it
  already uses for the process-group callback; the tick then closes its
  own copy, so the lock is held by the session and what it starts, and
  the operating system frees it when the last of them is gone. When
  that lock cannot be taken — a session, or something one started, is
  still alive — the pass starts nothing: the issue is left open and
  labelled, no run is recorded, and the pass ends as a failed one, so
  that passes held up this way reach the alert for failed passes in a
  row. At recovery, try to take that lock without waiting. Taken: no session is
  left, so release it, send no signal, and log that the session is
  already gone. Held: the session is alive, so stop the recorded process
  group as now. Nothing is read from `ps` or any other program, and no
  process is asked when it started. **Resume only a real worktree.** At recovery, write the handoff note
  only when the run's recorded worktree is one of the repository's
  worktrees (`git worktree list --porcelain` names it). When it is not —
  the run died before its worktree was cut — create nothing: raise the
  `timeout` alert, comment on and close the issue, and clear the record
  as now, with the alert and the comment saying the run stopped before
  it started work and that a new dispatch issue starts it afresh. That
  wording is fixed, in `report.py`'s style, and carries nothing from the
  issue. Tests use a real repository and real processes, as T-6's do.
- **Done when:** tests citing SC-12 show that recovery sends no signal
  to a live process group that has the recorded number but does not
  hold the session lock, and that the group is still alive afterwards;
  that it does stop a live stand-in session that holds the session lock
  and leads the recorded group; that after a stand-in session's launcher
  is killed the lock is still held, and is free once the session is
  stopped; that a pass which finds the session lock held starts no
  session, leaves its issue open and labelled with no comment, records
  no run and ends as a failed pass, and that a pass after the lock is
  freed runs the issue; that for a run whose worktree was never cut, recovery leaves no folder
  at the worktree's path, raises the alert, comments on and closes the
  issue and clears the record, and a dispatch issue for the same task
  then runs in a fresh worktree cut from `origin/main`; and T-6's
  existing SC-12 tests keep every assertion they make, with one change
  to their setup: the helper in `tests/dispatch/test_recovery.py` that
  stands in for a dead pass gives its stand-in session the session
  lock, as the tick now does. The gate passes.

### [ ] T-8 — Delivery: the host, the switch, the schedule, the heartbeat check, the docs, the live check
- **Satisfies:** SC-17
- **Depends on:** T-7, T-9
- **Touches:** `agent-framework.toml`, `docs/architecture.md`,
  `docs/adoption.md`, `specs/dispatch-from-issue/spec.md` (Status),
  `specs/dispatch-from-issue/tasks.md`; outside the repository: a
  launchd agent, the env file, Home Assistant
- **Brief:** Not for dispatch; done with vpc. In order: (1) the bet's
  spike on the host — a session started by launchd logs in on the Max
  plan, what a run does to usage, what it does to the host's other
  jobs — with the bet's first no-go applying if it fails; and, apart
  from the bet, whether the session lock is held while a real session
  runs (T-9), recorded here either way; (2) turn the
  CLI's self-update off on that Mac; (3) this repository's `[dispatch]`
  table, by vpc's own pull request, since the file is a protected path;
  (4) the `dispatch` and `failed` labels; (5) the launchd agent, every
  ten minutes, from the main checkout; (6) the heartbeat address in the
  env file and, on vpc's word, the Home Assistant check that alerts
  after one hour without one; (7) `docs/architecture.md` — the
  component, ADR 0010's trust boundary, and the launchd agent, the
  CLI's self-update and the heartbeat check as settings outside the
  repository — and `docs/adoption.md`, how to set it up and that
  untracked escalation files in the checkout are cleared by hand;
  (8) the spec's *Live check*, each line recorded here with its date.
- **Done when:** the four lines of the spec's *Live check* are recorded
  here as seen; the docs describe what is running and where; the plan's
  open risk about the host is closed with the host named in
  `docs/architecture.md`; and the pull request that records it marks the
  spec `Implemented`. SC-17 is claimed for the live half of the
  heartbeat (the address set, a heartbeat received); its tests are
  T-7's.
