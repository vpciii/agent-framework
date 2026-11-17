# Spec: An eval for the worker

- **Status:** Approved
- **Date:** 2026-11-15
- **Approved:** 2026-11-15, signed off by vpc
- **Author:** Claude (draft) — vpc is author of record
- **Related ADRs:** ADR 0001 (roles are bound by the roster), ADR 0004
  (the worker is headless Claude Code), ADR 0007 (the worker session is
  confined), ADR 0009 (the validator is bound by what the eval set
  measures)

> This spec is editable while `Draft` / `Under review` / `Approved`.
> When the PR that marks it `Implemented` merges it **freezes** into a
> historical record (methodology ADR 0027);
> a contradiction found later goes to a test, a new spec, or an ADR —
> not back into this file (methodology §2, §8).

## Problem

Nobody knows how well the worker does its job.

The roster binds the worker to `claude-opus-5-5` with the comment
"chosen by judgment, not by a scorecard: nothing measures the worker
yet". The validator is held to the opposite rule: ADR 0009 binds it to
whatever its eval set's scorecard shows is best, and every change to its
judgment cites a run from before and after. The worker has no such
instrument, so four questions have no answer:

- **Model.** Would `claude-sonnet-5-5`, at half the price, finish the
  same tasks as well? The roster keeps it "one line away" with nothing to
  say when to use it.
- **Effort.** The worker runs at Claude Code's default effort, because
  the orchestrator refuses an effort on the worker's binding. Whether a
  higher effort would help is unknown.
- **Changes to the worker.** The brief, the confinement profile and the
  session's limits have all changed since the worker was built; none
  with a measurement of what it did to the worker's results.
- **Cost.** Until specs/worker-spend-and-record, nothing recorded what a
  task costs. Its session records now hold that number for each session,
  but there is no fixed set of tasks to read it over.

The material for a measurement exists. This repository has merged task
pull requests, each a task from a `tasks.md` that a human accepted, each
starting from a known commit. The validator's eval set already freezes
27 of them. Only three were written by the worker itself (#31, #38,
#73); the rest were written in interactive sessions, so they show what
an accepted result for the task looks like, not what the worker did.

## Goals

1. One command runs today's worker over a fixed set of past tasks, each
   from the commit its accepted pull request started from, and says how
   many it finished in a state ready for review, how many of the
   accepted work's own tests its result passes, and what each cost.
2. Two runs over the same tasks can be compared, so a change to the
   worker — its model, its brief, its limits — is shown to help, not
   asserted to.
3. The tasks are durable artifacts: reviewed like code and frozen.
4. A first baseline is on record.

## Non-goals

- **Gating anything on the score.** No CI check, no merge rule, no
  automatic roster change.
- **Changing the worker.** Not its brief, its confinement, its limits or
  its roster binding. This spec builds the instrument only.
- **A model grading the worker's work.** Every score is computed by code
  from what a run leaves behind. Running the validator over the worker's
  result is a later choice (see *Out of scope*).
- **Evaluating the chief**, a revise-after-REJECT loop, or escalations
  (every case in this spec is a task that was completed).
- **Statistical significance.** A handful of tasks, each run once or a
  few times, shows large effects and breakages, not small differences.
- **Cases from an adopting repository**, and platforms other than macOS
  (the confinement profile's own limit).

## Requirements

- **R-1 (MUST)** A **worker eval case** is a file in this repository
  holding: the task (spec slug and task id); the **reference pull
  request** — the merged pull request that completed the task, with the
  commit it started from and its head commit; the reference pull
  request's test files that cite the task's claimed criteria; and its
  provenance (the date it was frozen, and by what).
- **R-2 (MUST)** Every case, as stored, is runnable: at its start commit
  the task's `tasks.md` and `spec.md` exist and the worker's brief
  builder builds a brief from them. This is checked in CI with no session
  run, so a case that rots is caught.
- **R-3 (MUST)** One command freezes a merged task pull request into a
  case, reading what it needs from GitHub once; after that, running the
  case needs only the repository.
- **R-4 (MUST)** One command runs the eval. For each case it runs
  today's worker exactly as a dispatch does — the same brief builder,
  confinement profile, session seam, time budget and spend limit, through
  the roster's worker role — in a fresh worktree cut from the case's
  start commit instead of `origin/main`. Every case runs under the same
  session paths, hosts and variable names, declared once for the case
  set, not under its start commit's `agent-framework.toml`. A case may be
  run more than once in one run.
- **R-5 (MUST NOT)** An eval run never pushes, opens a pull request,
  raises an alert, or changes anything outside its own worktrees, its
  session records and its result file. It never runs in CI, and no test
  starts a real session; the eval's own tests use a fake session.
- **R-6 (MUST)** For each run of a case, the eval records the worker's
  outcome (completed, escalated, timed out, spend limit reached, handoff
  refused, or error) and, for a completed session:
  - each of the project's gate commands, run by the eval against the
    session's last commit, passed or failed;
  - the handoff check's findings;
  - the reference tests, passed or failed, run on a copy of the
    session's tree with the reference pull request's versions of those
    test files laid over it;
  - the size of the session's diff.

  For every run it records the cost and turns the session record
  reports, the elapsed time, and where the session record and the
  session's diff are kept.
- **R-7 (MUST)** A failure of the eval itself on one case — the start
  commit cannot be checked out, the gate cannot be set up — makes that
  case "could not run" and the run continues. "Could not run" is never
  counted as a success or a failure of the worker.
- **R-8 (MUST)** The run produces a **worker scorecard**: for each case
  and in total, how many runs finished **ready for review** (completed,
  every gate command passing, no handoff finding), how many passed the
  reference tests, how many ended in each other outcome, how many could
  not run; and the total and median reported cost and elapsed time. The
  reference-test count is reported beside "ready for review", never
  folded into it.
- **R-9 (MUST)** A run's result says what was measured: the worker's
  model as the roster binds it, the Claude Code version, the date, the
  spend limit and time budget, a fingerprint of the brief each case was
  given, and a fingerprint of the case set. Two results are comparable
  when their case-set fingerprints match; comparing two that do not says
  so.
- **R-10 (MUST)** Every run that is not ready for review, and every
  reference-test failure, is listed with where its session record,
  diff and gate output are kept, so a human can decide whether the worker
  failed or the case is wrong. A case changes only as its own reviewed
  change.
- **R-11 (MUST)** The initial set holds at least 6 cases from this
  repository's merged task pull requests: #31, #38, #73 (the three the
  worker wrote), #88 (a reference pull request of more than 300 changed
  lines), and at least two more.
- **R-12 (SHOULD)** The delivery records a first baseline: one run of
  every case with the roster's current worker binding, by the human,
  committed as a result file and cited, with its total reported cost.
- **R-13 (SHOULD)** From then on, a change to the worker's model, brief,
  confinement profile, time budget or spend limit cites a run from before
  and after. Stated in `docs/architecture.md`; not enforced by code.

## Success criteria

- **SC-1** — A case file round-trips: frozen, written, read back with
  its task, reference pull request, start and head commits, reference
  test files and provenance. A file missing any of them fails to load,
  naming the file and the field. (R-1)
- **SC-2** — A CI test builds the brief for every case in the set at its
  start commit, with no session run; a case whose task cannot be found
  there fails it, naming the case. (R-2)
- **SC-3** — Freezing a merged task pull request (through a fake GitHub
  seam) writes a case with its start and head commits and the test files
  that cite its claimed criteria; freezing a pull request that is not
  merged, or that names no task, writes nothing and says why. (R-3)
- **SC-4** — A run (through a fake session) launches each case's session
  with the brief built at the case's start commit, the confinement
  profile, the time budget, the spend limit and the roster's worker
  model, in a worktree cut from that commit; a case run three times
  starts three sessions in three worktrees. (R-4)
- **SC-5** — Across a run with completed, escalated, timed-out,
  spend-limit and refused fake sessions, no push, pull request or alert
  command is issued, and nothing is written outside the run's worktrees,
  session records and result file. No workflow file names the eval
  command. (R-5)
- **SC-6** — For a completed fake session, the result records each gate
  command's outcome at the session's last commit, the handoff check's
  findings, the reference tests' outcome against the session's code, the
  diff size, and the reported cost, turns and elapsed time; for every
  other outcome, the outcome, cost, turns and elapsed time. (R-6)
- **SC-7** — A case whose start commit cannot be checked out is "could
  not run", the next case still runs, and the scorecard counts it in
  neither the successes nor the failures. (R-7)
- **SC-8** — Given recorded runs, the scorecard's counts (ready for
  review, reference tests passed, each other outcome, could not run) and
  its total and median cost and time are what the runs say. (R-8)
- **SC-9** — A result carries the model, Claude Code version, date,
  limits, brief fingerprints and case-set fingerprint; comparing two
  results with different case-set fingerprints says they are not
  comparable. (R-9)
- **SC-10** — Every run not ready for review, and every reference-test
  failure, is listed with the paths of its session record, diff and gate
  output. (R-10)
- **SC-11** — The case set holds at least 6 cases, among them #31, #38,
  #73 and #88. (R-11)

## Glossary additions (proposed with this spec)

Added to `docs/glossary.md` in the implementing PRs.

- **Worker eval case** — one past task the worker is measured on: the
  task, the commit its accepted pull request started from, that **reference
  pull request**, and the tests it added for the task's criteria.
- **Reference pull request** — the merged pull request that completed a
  worker eval case's task, accepted by the human. Its start commit is
  where the worker begins; its tests are run against what the worker
  produced. It shows one accepted result, not the only one.
- **Ready for review** — a worker run that completed with every gate
  command passing and no handoff finding: a pull request the human would
  be asked to review.
- **Worker scorecard** — the result of running the worker over the
  worker eval cases (the validator's is the **scorecard**).

## Open questions

- [x] **Is this a bet to plan first?** A full run is hours of sessions:
  6 cases at up to 30 minutes and $10 each is up to 3 hours and $60 at
  list price, from the Max plan's allowance while the worker runs on it.
  The methodology plans an uncertain or expensive bet before its spec.
  Decided (vpc, 2026-11-15): no planning folder; go straight to a plan,
  since the shape follows the validator's eval closely, and treat R-12's
  baseline as the measurement of what a run costs.
- [x] **Reference tests against different code.** The worker's code can
  be correct and still fail the reference tests, if it names things
  differently than the reference pull request did, and its own test files
  sit at the same paths. Decided (vpc, 2026-11-15): run the reference
  test files on a copy of the session's tree with the reference versions
  of those files laid over it, and report the result beside "ready for
  review", not folded into it (R-6, R-8).
- [x] **Which project configuration a case runs under.** Older start
  commits have an `agent-framework.toml` from before the confinement
  fields existed, so a session there cannot reach the package host its
  gate needs. Decided (vpc, 2026-11-15): every case runs under the
  session paths, hosts and variable names the case set declares once,
  today's, so the runs differ only in the task (R-4).
- [x] **Which cases.** Decided (vpc, 2026-11-15): #31 and #73 (worker
  written, about 90 lines each), #38 (worker written, 72 lines), #88
  (688 lines), and two more medium tasks from the validator's eval set.
  For the first four, the task's block is in `tasks.md` at the start
  commit (checked 2026-11-15); the other two are chosen when frozen.
- [x] **Effort.** Measuring effort needs the worker to take one, which
  it refuses today. Decided (vpc, 2026-11-15): out of scope here; the
  first comparison is between models, which needs only a roster edit.

## Out of scope (for now)

- The validator's verdict on the worker's result, as a further column.
- Seeded cases that should end in an escalation.
- Comparing effort levels (needs the worker to accept an effort).
- Running cases in parallel.

## Traceability

Built up as the feature is implemented; complete before the spec is
marked `Implemented`.

| Criterion | Requirement(s) | Verified by (test) |
|---|---|---|
| SC-1 | R-1 | `tests/evals/worker/test_case.py::test_sc1_a_case_round_trips_through_its_file`, `tests/evals/worker/test_case.py::test_sc1_a_file_missing_a_field_fails_naming_the_file_and_the_field` |
| SC-2 | R-2 | `tests/evals/worker/test_case.py::test_sc2_the_brief_is_built_from_the_start_commits_artifacts`, `tests/evals/worker/test_case.py::test_sc2_a_case_whose_task_is_absent_at_its_start_fails_naming_the_case`, `tests/evals/worker/test_case.py::test_sc2_every_committed_case_builds_its_brief_at_its_start_commit` |
| SC-3 | R-3 | `tests/evals/worker/test_freeze.py::test_sc3_a_frozen_case_loads_with_its_start_head_and_reference_tests`, `tests/evals/worker/test_freeze.py::test_sc3_a_refused_pull_request_writes_nothing_and_says_why`, `tests/evals/worker/test_freeze.py::test_sc3_the_worker_freeze_command_refuses_with_exit_2_writing_nothing` |
| SC-4 | R-4 | `tests/worker/test_worktree.py::test_sc4_a_detached_worktree_is_added_at_a_past_commit_with_the_result_file_excluded` |
| SC-5 | R-5 | *(pending)* |
| SC-6 | R-6 | `tests/worker/test_handoff_check.py::test_sc6_given_a_base_findings_are_for_changes_since_it_and_none_before` |
| SC-7 | R-7 | *(pending)* |
| SC-8 | R-8 | `tests/evals/worker/test_scorecard.py::test_sc8_the_class_follows_the_plans_table`, `tests/evals/worker/test_scorecard.py::test_sc8_counts_medians_and_unstable_are_what_the_runs_say` |
| SC-9 | R-9 | `tests/evals/worker/test_scorecard.py::test_sc9_a_result_round_trips_with_every_field`, `tests/evals/worker/test_scorecard.py::test_sc9_comparing_different_case_sets_is_refused`, `tests/evals/worker/test_scorecard.py::test_sc9_compare_names_the_cases_whose_class_or_reference_tests_changed` |
| SC-10 | R-10 | `tests/evals/worker/test_scorecard.py::test_sc10_every_run_not_ready_and_every_reference_failure_is_listed_with_its_paths` |
| SC-11 | R-11 | *(pending)* |
