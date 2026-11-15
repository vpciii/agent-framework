# Spec: A worker session has a spend limit and leaves a session record

- **Status:** Approved
- **Date:** 2026-11-15
- **Approved:** 2026-11-15, signed off by vpc
- **Author:** Claude (draft) — vpc is author of record
- **Related ADRs:** ADR 0004 (the worker is headless Claude Code, on the
  Max plan while supported, with an API-key fallback), ADR 0007 (the
  worker session is confined; the orchestrator holds the credentials and
  checks what comes back)
- **Compact spec** (methodology ADR 0024): one PR; Approach and Rollout
  below.

> This spec is editable while `Draft` / `Under review` / `Approved`.
> When the PR that marks it `Implemented` merges it **freezes** into a
> historical record (methodology ADR 0027);
> a contradiction found later goes to a test, a new spec, or an ADR —
> not back into this file (methodology §2, §8).

## Problem

A worker session is stopped by one thing only: its time budget (30
minutes by default). Nothing bounds what it spends. On the Max plan that
spend is drawn from the plan's usage allowance; on the API-key fallback
ADR 0004 names, it is money, and the only bound is the account-wide cap
of $100 a month that every role shares. One stuck or looping session can
use a large share of either before the timeout fires.

Nothing is kept of what a session did, either. The orchestrator reads
the session's standard output into memory and discards it; what remains
is the session's commits and its `.worker-result.json`. When a session
times out, is refused at the handoff check, or opens a pull request the
validator rejects, there is no account of its turns, its tool calls or
its cost to look at. For the same reason no one knows what a worker task
costs. The roster binds the worker to `claude-opus-5-5` "by judgment,
not by a scorecard: nothing measures the worker yet", and any future
measurement of the worker needs exactly these numbers.

## Goals

1. Every worker session runs under a spend limit, and a session stopped
   at that limit is handled as a session stopped at its time budget is:
   no pull request, the worktree kept, a handoff note, an alert.
2. Every worker session leaves a session record on the dispatching
   machine, including a session that is killed at its time budget.
3. The cost and number of turns of every session that reported them are
   logged when it ends.

## Non-goals

- **Measuring the worker.** A worker eval is its own spec; this one only
  makes the numbers it needs exist.
- **Choosing the worker's model or effort.** The roster binding is
  unchanged.
- **Reporting cost anywhere public.** Not in the pull request, not in an
  alert issue.
- **Deleting old session records.** They accumulate until a human
  removes them.
- **Changing the time budget**, the confinement profile, or the result
  contract.

## Requirements

- **R-1 (MUST)** Every worker session is launched with a spend limit. The
  limit is taken from the dispatch (`--spend-limit` on the worker CLI,
  default $10 at list price); no session is launched without one.
- **R-2 (MUST)** A session that ends because it reached its spend limit
  opens no pull request; its worktree is kept, a handoff note naming the
  limit and the cost reported is written into it, and an alert labelled
  `timeout` is raised. The worker CLI exits 3, as for a timeout.
- **R-3 (MUST)** Every worker session's output is written, as it
  arrives, to a session record file outside the session's worktree. The
  record survives the worktree's removal.
- **R-4 (MUST)** A session killed at its time budget leaves a session
  record holding everything the session wrote before it was killed.
- **R-5 (MUST NOT)** A session record is never committed, pushed, put in
  a pull request, or quoted in an alert. It holds whatever the session
  read (ADR 0007: what an agent can read, it can publish).
- **R-6 (MUST)** `.worker-result.json` stays the only source of a
  session's outcome when it ends normally (`completed` or `escalated`).
  The session record is used only to tell a spend-limit stop from any
  other failed exit.
- **R-7 (MUST)** A failed exit for any reason other than the spend limit
  is reported as it is today (`SessionResultError`), and its session
  record is kept.
- **R-8 (SHOULD)** When a session ends, the orchestrator logs the cost
  and number of turns the record's final entry reports. A record with no
  readable final entry is logged as "cost unknown" and never changes the
  outcome.

## Success criteria

- **SC-1** — The command every session is launched with carries the
  spend limit from the dispatch, the default when the dispatch gives
  none, and the streamed output format; a dispatch cannot remove the
  limit.
- **SC-2** — A session whose final entry reports the spend limit reached
  returns the spend-limit outcome: no pull request opened, worktree
  kept, a handoff note in it naming the limit and the reported cost, an
  alert raised, CLI exit 3.
- **SC-3** — A session's output is in its session record outside the
  worktree, and the record is still there after the worktree is removed
  on the pull-request path.
- **SC-4** — A session killed at its time budget leaves a session record
  containing what it wrote before the kill.
- **SC-5** — The session record is not in the worktree, not in any
  commit pushed, not in the pull request body and not in any alert text.
- **SC-6** — A session whose final entry reports success but which wrote
  no `.worker-result.json` is a `SessionResultError`; a session that
  wrote one is judged by it alone.
- **SC-7** — A session that exits non-zero for another reason raises
  `SessionResultError` as before, and its record is kept.
- **SC-8** — The orchestrator logs the reported cost and turns for a
  session with a readable final entry, and "cost unknown" for one
  without, with the outcome unchanged.

## Glossary additions (proposed with this spec)

Added to `docs/glossary.md` in the implementing PR, with the change to
**Handoff note** below.

- **Spend limit** — the most a single worker session may spend, in US
  dollars at the provider's list price, set at dispatch. Claude Code
  measures it, and checks it after each turn, so a session can overrun
  it by up to one turn. On the Max plan it measures use of the plan's
  allowance, not money.
- **Session record** — the file of everything a worker session wrote to
  its output (its turns, tool calls and results, and a final entry with
  its cost and why it ended), kept on the dispatching machine outside
  the worktree. Never published.
- **Handoff note** (changed) — "when a worker session is stopped at its
  budget" becomes "when a worker session is stopped at its time budget
  or its spend limit".

## Approach

**Launching.** `run_session` adds three arguments to the command:
`--max-budget-usd <limit>`, `--output-format stream-json` and
`--verbose` (the CLI refuses the stream format in print mode without
it). The limit reaches `run_session` the way the time budget does: a
`spend_limit_usd` argument to `work()`, from a `--spend-limit` option
on the worker CLI. The flags are added by the session seam, not the
confinement profile: they are not limits on what commands may reach.

**The record.** The default runner opens the record file and hands it
to the session process as its standard output, instead of reading
standard output into memory. The output is then on disk as it is
written, so a session killed at its time budget leaves everything up to
the kill (R-4). The record lives at
`.worktrees/records/<spec>-<task>-<UTC timestamp>.jsonl`: beside the
worktrees, under a directory `.gitignore` already ignores, and not
inside any worktree, so `remove_worktree` leaves it alone and no
session's commits can include it (R-3, R-5). Standard error is read as
today and still feeds the `SessionResultError` message. The
`SessionRunner` seam gains the record path; the test fake writes canned
stream entries to it.

**Reading the end.** After the process ends, the orchestrator reads the
record's last line. If the session exited non-zero and that line is a
`result` entry with subtype `error_max_budget_usd`, the session reached
its spend limit: the orchestrator writes the handoff note (with the
limit and the reported `total_cost_usd`), raises the alert and returns a
new `SpendLimitReached` outcome, which the CLI maps to exit 3. Any other
non-zero exit is the existing `SessionResultError` (R-7). A zero exit
goes on to `read_result` exactly as today, whatever the record says
(R-6). In every case the reported cost and `num_turns` are logged, or
"cost unknown" (R-8).

**What was measured** (spike, 2026-11-15, Claude Code 2.1.325, Max plan
login, `claude-haiku-5-5`, one-line prompt):

- `--max-budget-usd 0.000001` with `--output-format json`: the session
  ran one turn, then stopped. Exit 1; the result entry had `subtype:
  "error_max_budget_usd"`, `terminal_reason: "budget_exhausted"`,
  `total_cost_usd: 0.0113` and `costBasis: "list"`. So the limit is
  enforced under the Max plan, measured at list price, and checked after
  a turn rather than during it.
- `--output-format stream-json` without `--verbose`: refused, exit 1.
  With `--verbose`: exit 0, one JSON object per line (`system` init,
  `assistant`, `rate_limit_event`, `system` post-turn summary, `result`
  with `total_cost_usd`, `num_turns`, `terminal_reason`). About 24 KB for
  the one-line prompt.

Not measured: a stream-format session stopped at its spend limit (the
`result` entry is expected to match the JSON-format one), and the size
of a full worker session's record.

### Decisions

- *2026-11-15* — The stream format, not the single JSON result: a
  session killed at its time budget never reaches a final JSON result,
  so only the stream leaves a record of it (R-4).
- *2026-11-15* — vpc settled the open questions: the default spend limit
  is $10 a session at list price; records live in `.worktrees/records/`;
  a spend-limit stop raises an alert labelled `timeout`, titled
  "<task> of <spec> reached its spend limit".
- *2026-11-15* — Implementing: the spend limit reaches the session's
  argument list as the value of `--max-budget-usd`. specs/worker-confinement
  R-5 says no caller "can pass arguments to the session or otherwise widen
  the profile at dispatch", and its SC-3 test asserted the exact launch
  command. The limit is not an argument a caller passes: it is a number the
  orchestrator checks (at least $0.01, finite) and formats into a fixed
  flag, and it can only narrow what a session may do. That test now
  asserts the launch with the two fixed flags appended; it still fails if
  anything else is added. Flagged for vpc's acceptance in the implementing PR.
- *2026-11-15* — Measured while implementing, with the same CLI and model:
  a stream-format session given `--max-budget-usd 0.000001` exits 1 and
  its last line is a `result` entry with subtype `error_max_budget_usd`,
  which `read_end` reads as reaching the limit. The size of a full worker
  session's record is still unmeasured.
- *2026-11-15* — vpc accepted the reading of specs/worker-confinement R-5
  above, and kept the implementation as one PR (about 680 changed lines,
  over the ~300 guideline), since the spend-limit check reads the session
  record.

## Rollout and undo

No flag. The default spend limit is set high enough that it should stop
only a runaway session. The first records will show what tasks actually
cost, and the default can then be lowered in an ordinary PR. The undo is
reverting the implementing PR: there is no migration and no stored state
beyond the record files, which are local, ignored by git, and safe to
delete. Nothing here is irreversible.

## Open questions

- [x] **The default spend limit.** $10 a session at list price (vpc,
  2026-11-15). With no records yet, this is a guess at "well above any
  normal task"; the records this spec creates are how to replace it.
- [x] **Where records live.** `.worktrees/records/` (vpc, 2026-11-15).
  The alternative was the repository's git directory
  (`<git common dir>/agent-framework/sessions/`). A later session can
  read either location, since both are inside the repository it may
  read, and a record holds only what an earlier session read from that
  same repository.
- [x] **The alert's label.** Reuse `timeout` (vpc, 2026-11-15), so the
  resume card and the nudge pick it up unchanged, with a title saying the
  spend limit was reached. The alternative was a new `spend-limit` label,
  which the resume card's alert query would have needed to learn.

## Out of scope (for now)

- A worker eval, which would read the session records (follow-up spec).
- Per-task spend reported in the pull request or on the resume card.
- Pruning or rotating old session records.

## Traceability

| Criterion | Requirement(s) | Verified by (test) |
|---|---|---|
| SC-1 | R-1 | `tests/worker/test_spend_and_record.py::test_sc1_every_session_carries_the_spend_limit_and_the_stream_format`, `tests/worker/test_spend_and_record.py::test_sc2_the_cli_passes_its_spend_limit_to_the_dispatch` |
| SC-2 | R-2 | `tests/worker/test_spend_and_record.py::test_sc2_a_session_stopped_at_its_spend_limit_is_handled_as_a_timeout`, `tests/worker/test_spend_and_record.py::test_sc2_the_cli_passes_its_spend_limit_to_the_dispatch` |
| SC-3 | R-3 | `tests/worker/test_spend_and_record.py::test_sc3_the_record_is_outside_the_worktree_and_outlives_it` |
| SC-4 | R-4 | `tests/worker/test_spend_and_record.py::test_sc4_a_session_killed_at_its_time_budget_leaves_its_record` |
| SC-5 | R-5 | `tests/worker/test_spend_and_record.py::test_sc5_the_record_is_never_published` |
| SC-6 | R-6 | `tests/worker/test_spend_and_record.py::test_sc6_the_result_file_alone_decides_a_normal_ending` |
| SC-7 | R-7 | `tests/worker/test_spend_and_record.py::test_sc7_any_other_failed_exit_is_reported_as_before` |
| SC-8 | R-8 | `tests/worker/test_spend_and_record.py::test_sc8_cost_and_turns_are_logged_or_unknown` |
