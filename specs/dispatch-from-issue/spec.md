# Spec: A dispatch issue starts a worker run

- **Status:** Approved
- **Date:** 2026-11-18
- **Approved:** 2026-11-18, signed off by vpc
- **Author:** Claude (draft) — vpc is author of record
- **Related ADRs:** ADR 0004 (the worker is headless Claude Code), ADR
  0007 (the worker session is confined; the orchestrator holds the
  credentials), ADR 0010 (accepted with this spec: what may start and
  steer a run with no one at the keyboard)
- **Planning:** `planning/durable-autonomy/` — option A1
  (`options-a.md`, Converged 2026-11-17) under the bet `bet-a1.md`
  (Placed 2026-11-18: two weeks, ending 2026-12-02)

> This spec is editable while `Draft` / `Under review` / `Approved`.
> When the PR that marks it `Implemented` merges it **freezes** into a
> historical record (ADR 0027);
> a contradiction found later goes to a test, a new spec, or an ADR —
> not back into this file (methodology §2, §8). If the feature is later
> sunset, only the status flips to `Retired` (ADR 0019) — the content
> stays frozen.

## Problem

A worker run starts only when someone types the dispatch command in a
terminal. On 2026-11-17 and 2026-11-18 the worker took six tasks to six
merged pull requests with no rework, and each of those runs began with
someone sitting down to start it. The trial's verdict found the same
thing from the other side: every day with a merge was a day vpc was at
the keyboard (`planning/durable-autonomy/verdict.md`).

Three things stand between today's worker and a run that starts while
vpc is away. Nothing starts it. A run that is killed leaves a worktree
and a branch that the next dispatch refuses, so recovering needs a
terminal (pre-mortem spike 5). And every way an unattended run can stop
is silent today: a changed CLI, a dead lock, an expired login, a tick
that no longer fires (pre-mortem spikes 6 and 7).

## Goals

1. vpc starts a run from his phone, and it ends in an open pull request
   or an alert, with no terminal used.
2. Only vpc's own act on GitHub starts a run, and only what is merged on
   `main` decides what the run does.
3. A run that was stopped or killed can be started again and ends in
   exactly one pull request.
4. When unattended runs stop working, vpc is told; silence means
   nothing is wrong.
5. Dispatching by hand works exactly as it does today.

## Non-goals

- A trigger other than vpc's dispatch issue: no tracker (YouTrack
  included), no webhook, no change to `tasks.md` that dispatches itself.
- A run on anything but the one Mac the tick is loaded on, or while that
  Mac is off or asleep.
- Sending a validator REJECT back to the worker to revise. An unattended
  run that draws one still waits for vpc.
- More than one run at a time.
- Merging. vpc merges, as now.
- Retrying on the tick's own initiative. Each run answers one dispatch
  issue.
- A limit on how many runs a day may start. Each run has its spend
  limit; how many start is bounded by how many issues vpc opens.

## Requirements

**What starts a run**

- **R-1 (MUST)** A command, the **dispatch tick**, makes one pass and
  exits. A pass looks for open issues labelled `dispatch` in the
  project's repository and acts on at most one, the oldest.
- **R-2 (MUST)** A dispatch issue is accepted only if its author is the
  account named in the project's configuration, its title is exactly
  `<spec-slug> <task-id>`, and that task exists on `origin/main`, is not
  marked done there, and claims at least one criterion. Any other issue
  carrying the label is refused: no session starts.
- **R-3 (MUST)** With no author configured, or with dispatch switched
  off in the project's configuration, a pass does nothing and says so.
  Dispatch from an issue is off until a project turns it on.
- **R-4 (MUST)** The tick claims an accepted issue before it starts a
  session, by removing the `dispatch` label. If the claim fails, no
  session starts.
- **R-5 (MUST)** At most one run is in progress per checkout. A pass
  that finds another pass still running starts nothing.

**What steers a run**

- **R-6 (MUST NOT)** No text from an issue — title, body, comments,
  labels, or the author's name — reaches a session's brief, its command
  line or its environment, other than the spec slug and task id after
  they have matched the pattern in R-2.
- **R-7 (MUST)** The brief is built from `tasks.md` and `spec.md` as
  they are on `origin/main` when the run starts, whatever the working
  files of the tick's checkout hold.
- **R-8 (MUST)** Before each pass the tick brings its checkout to
  `origin/main`. If the checkout has changes to tracked files, cannot be
  fast-forwarded, or lies inside another repository's working tree, the
  pass starts nothing and raises an alert.
- **R-9 (MUST)** The session is launched as a hand dispatch launches it:
  the same confinement profile, time budget, spend limit and roster
  binding (ADR 0007). The tick adds no access.
- **R-10 (MUST NOT)** The tick never merges a pull request, never
  approves one, and never changes a branch other than the task's own.

**What vpc hears back**

- **R-11 (MUST)** Every dispatch issue the tick acts on, accepted or
  refused, gets one comment saying what happened and is closed: the pull
  request's address, or the alert that was raised, or why it was
  refused.
- **R-12 (MUST NOT)** A comment the tick writes contains no text taken
  from an issue. It is fixed wording plus values the code computed.
- **R-13 (MUST)** A run that ends with no pull request and none of
  today's alerts (escalation, timeout, spend limit, handoff refused)
  raises an alert labelled `failed` that names the kind of failure:
  login, usage limit, CLI version, or other.

**Starting again**

- **R-14 (MUST)** When a task's worktree and branch are left from a run
  stopped at its time budget or its spend limit, a new dispatch issue
  for that task resumes them: a new session starts in the same worktree,
  on the same branch, with the brief and the handoff note.
- **R-15 (MUST)** A pass that finds a run's lock held by a process that
  no longer exists clears the lock, writes the handoff note that run
  never wrote, raises a `timeout` alert, and comments on and closes the
  issue that run had claimed. A later dispatch issue then resumes it
  (R-14).
- **R-16 (MUST)** When the task's branch is already on the remote with
  no pull request, a new dispatch issue opens the pull request and
  starts no session. When it already has an open pull request, the issue
  is refused, naming it.
- **R-17 (MUST)** When a task's worktree is left from an escalation or a
  refused handoff, a new dispatch issue starts the task afresh from
  `origin/main`. The earlier attempt's commits are kept under another
  local branch name; nothing is deleted.

**When it stops working**

- **R-18 (MUST)** The project's configuration may name the worker CLI's
  version. When it does and the installed CLI reports another, the tick
  starts no session and raises a `failed` alert.
- **R-19 (MUST)** A pass that cannot do its work — it cannot list
  issues, or cannot fetch — counts as failed. The third failed pass in a
  row raises one `failed` alert; the passes after it raise none until a
  pass succeeds.
- **R-20 (MUST)** Every pass that completes, including one that found
  nothing to do, sends a **heartbeat** to an address taken from the
  environment. A failed pass sends none. A heartbeat that cannot be sent
  never changes a pass's outcome.
- **R-21 (SHOULD)** Something outside the tick's Mac raises an alert
  when no heartbeat has arrived for a set time. It is a setting outside
  the repository, recorded in `docs/architecture.md`.

**What does not change**

- **R-22 (MUST)** `python -m agent_framework.worker <slug> <task>` and
  `work()` behave as they do today for a task with no worktree or branch
  left from an earlier run, including refusing an existing one.

## Success criteria

- **SC-1** — A pass over a fake tracker starts a session only for an
  open `dispatch` issue from the configured author whose title names a
  task that is on `origin/main`, not done, and claims a criterion. For
  each other case (another author, a title of any other shape, an
  unknown spec or task, a task already done) no session starts. With
  several acceptable issues, only the oldest is acted on. (R-1, R-2)
- **SC-2** — With no author configured, and with dispatch switched off,
  a pass lists nothing, starts nothing and says why. (R-3)
- **SC-3** — The `dispatch` label is removed before the session starts;
  when removing it fails, no session starts. A pass made while another
  holds the lock starts nothing and leaves its issue as it was.
  (R-4, R-5)
- **SC-4** — For an issue whose body, comments and labels carry marker
  text, the session's brief, command line and environment contain none
  of it. A title carrying anything beyond a slug and a task id is
  refused. (R-6)
- **SC-5** — When the checkout's working copy of `tasks.md` differs from
  the one on `origin/main`, the brief is the one built from
  `origin/main`. (R-7)
- **SC-6** — A pass starts nothing and raises an alert when the
  checkout has a changed tracked file, when it cannot be fast-forwarded,
  and when it lies inside another repository's working tree; otherwise
  the checkout is at `origin/main` before any issue is read. (R-8)
- **SC-7** — A session started by the tick is launched with the same
  profile arguments, environment, time budget, spend limit and model as
  `work()` gives a hand dispatch of that task. (R-9)
- **SC-8** — Across runs that end in a pull request, an escalation, a
  timeout, the spend limit, a refused handoff and an error, the tick
  issues no merge, approve or review command and pushes no branch other
  than the task's. (R-10)
- **SC-9** — For each of those endings, and for each refusal, the issue
  gets exactly one comment and is closed. The comment names the pull
  request or the alert or the reason, and contains none of the marker
  text the issue carried. (R-11, R-12)
- **SC-10** — A run that ends in an error raises one alert labelled
  `failed`. A login failure, a usage limit and a CLI version mismatch
  are each named as such; anything else is named "other". (R-13)
- **SC-11** — After a run stopped at its time budget, and after one
  stopped at its spend limit, a new dispatch issue for the task starts a
  session in the same worktree on the same branch, and its brief
  contains the handoff note. (R-14)
- **SC-12** — A pass that finds a lock naming a process that does not
  exist clears it, writes a handoff note into the worktree, raises a
  `timeout` alert and comments on and closes the claimed issue; the next
  dispatch issue for the task resumes it. (R-15)
- **SC-13** — With the branch on the remote and no pull request, a
  dispatch issue opens one pull request and starts no session. With an
  open pull request for the branch, the issue is refused and its comment
  names the pull request. (R-16)
- **SC-14** — With a worktree left by an escalation, and with one left
  by a refused handoff, a dispatch issue starts a session in a fresh
  worktree cut from `origin/main`, and the earlier commits are reachable
  from another local branch. (R-17)
- **SC-15** — With a CLI version configured and a different one
  installed, no session starts and a `failed` alert names both versions.
  With none configured, the session starts. (R-18)
- **SC-16** — Three failed passes in a row raise exactly one `failed`
  alert, at the third; a fourth raises none; after a successful pass the
  count starts again. (R-19)
- **SC-17** — A completed pass sends one heartbeat, whether or not it
  found an issue; a failed pass sends none; with no address in the
  environment, or an address that refuses, the pass's outcome and exit
  status are unchanged. (R-20)
- **SC-18** — For a task with no worktree or branch left behind, a hand
  dispatch issues the same commands as before this change, and still
  refuses an existing worktree or branch. (R-22)

## Glossary additions (proposed with this spec)

Three terms this spec needs. They were proposals until the spec was
approved, and are in `docs/glossary.md` from that change on.

- **Dispatch issue** — an open GitHub issue labelled `dispatch`, opened
  by the account the project names, whose title is a spec slug and a
  task id. It asks for one worker run. It is a pointer to a task on
  `main`; nothing in it is read by a session.
- **Dispatch tick** — the command, run on a schedule, that makes one
  pass: it finds a dispatch issue, starts the run it asks for, and
  reports back on the issue.
- **Heartbeat** — the signal a dispatch tick sends when a pass
  completes, so that its absence can be noticed from outside.

## Live check

What no test in the repository can show, checked by hand before the
spec is marked `Implemented`. The first three are the bet's own signal.

- From vpc's phone, away from any keyboard: a dispatch issue is opened
  and a pull request for its task is open, with CI's result on it, with
  no terminal used. Three tasks.
- One run is killed on purpose mid-session; a new dispatch issue ends in
  exactly one pull request.
- With the tick unloaded, the missing heartbeat raises an alert on vpc's
  phone.
- The tick, started by launchd, runs a session that is logged in on the
  Max plan.

## Open questions

All six were answered by vpc on 2026-11-18, each as recommended.

- [x] **Title or body.** Decided: the issue's *title* is
  `<spec-slug> <task-id>` (R-2). The options round said the body;
  GitHub requires a title and not a body, so from a phone it is one
  field instead of two, and the body is never parsed at all.
- [x] **Which Mac.** Decided: not this spec's to name. The bet names
  defiant, and its first spike checks that a session started by launchd
  there logs in on the Max plan, what a run does to usage, and what it
  does to defiant's other jobs. This spec is the same on either Mac; the
  plan names the host once the spike is run, and `docs/architecture.md`
  records it.
- [x] **The tick brings its checkout to `origin/main` on its own
  (R-8).** Decided: accepted. A change merged to `main` — to the worker,
  the tick, or the configuration — runs on that Mac at the next pass,
  with no step in between. That is what makes "merged on `main`" the one
  line of trust (ADR 0010), and it makes the configuration a switch vpc
  can reach from his phone.
- [x] **How long without a heartbeat is too long (R-21).** Decided: one
  hour, with a tick every ten minutes. The Home Assistant side is a
  change to vpc's own configuration and is made on his word when the
  heartbeat exists.
- [x] **What starting afresh keeps (R-17).** Decided: as written. The
  earlier attempt's commits are kept under another local branch name and
  its worktree is removed; refusing until vpc clears it by hand would
  need a terminal.
- [x] **This is more than one pull request.** Decided: a `plan.md` and a
  `tasks.md` follow this spec. It is not the compact spec the options
  round and the bet called it (a compact spec is for work that fits in
  one pull request). The bet's count of three or four stands.

## Out of scope (for now)

- **Tracker intake.** A YouTrack issue becomes a drafted spec and task
  in a pull request that vpc merges; only then can it be dispatched. Its
  own spec, after this one is producing pull requests (`options-a.md`).
- **The revise loop.** A validator REJECT sent back to the worker. The
  spec after this one.
- **A second runner.** A Linux or CI runner, and the trigger and runner
  seams of option A3, when a second tracker or host exists.
- **Dispatching the ready frontier.** Starting every task whose
  dependencies are merged without an issue per task.

## Traceability

| Criterion | Requirement(s) | Verified by (test) |
|---|---|---|
| SC-1 | R-1, R-2 | `tests/dispatch/test_issue.py::test_sc1_accepts_the_configured_authors_title_for_an_open_task`, `tests/dispatch/test_issue.py::test_sc1_refuses_each_other_case_with_its_own_reason`, `tests/dispatch/test_issue.py::test_sc1_another_author_is_refused_before_the_title_is_looked_at`, `tests/dispatch/test_issue.py::test_sc1_a_refusal_carries_nothing_taken_from_the_issue`, `tests/dispatch/test_issue.py::test_sc1_the_oldest_of_several_issues_is_chosen`, `tests/dispatch/test_pass_refuses.py::test_sc1_a_refused_issue_starts_no_session` |
| SC-2 | R-3 | `tests/dispatch/test_issue.py::test_sc2_no_author_and_disabled_are_each_reported_as_off`, `tests/test_project_config.py::test_sc2_no_author_and_enabled_false_are_each_off`, `tests/dispatch/test_pass_refuses.py::test_sc2_with_dispatch_off_the_tracker_is_never_asked_and_the_pass_says_why` |
| SC-3 | R-4, R-5 | `tests/dispatch/test_pass_refuses.py::test_sc3_a_pass_while_another_process_holds_the_lock_lists_nothing` |
| SC-4 | R-6 | `tests/dispatch/test_issue.py::test_sc4_a_title_beyond_a_slug_and_a_task_id_is_refused`, `tests/dispatch/test_issue.py::test_sc4_only_the_matched_slug_and_task_id_come_from_the_title` |
| SC-5 | R-7 | `tests/worker/test_at_commit.py::test_sc5_the_brief_and_the_worktree_come_from_the_commit_not_the_working_files`, `tests/worker/test_at_commit.py::test_sc5_with_a_commit_nothing_is_fetched_and_the_tree_is_cut_there`, `tests/worker/test_at_commit.py::test_sc5_a_commit_without_the_spec_or_the_task_is_refused_before_any_worktree` |
| SC-6 | R-8 | *(pending)* |
| SC-7 | R-9 | *(pending)* |
| SC-8 | R-10 | *(pending)* |
| SC-9 | R-11, R-12 | `tests/dispatch/test_pass_refuses.py::test_sc9_each_refusal_leaves_one_comment_no_label_and_a_closed_issue`, `tests/dispatch/test_pass_refuses.py::test_sc9_marker_text_in_the_title_is_not_in_the_comment` |
| SC-10 | R-13 | *(pending)* |
| SC-11 | R-14 | `tests/worker/test_starting_again.py::test_sc11_a_stopped_run_resumes_in_its_worktree_with_the_note` |
| SC-12 | R-15 | *(pending)* |
| SC-13 | R-16 | `tests/worker/test_starting_again.py::test_sc13_a_pushed_branch_without_a_pr_gets_one_and_no_session`, `tests/worker/test_starting_again.py::test_sc13_with_no_worktree_left_the_pr_says_the_run_was_interrupted`, `tests/worker/test_starting_again.py::test_sc13_an_open_pr_is_named_and_no_session_starts` |
| SC-14 | R-17 | `tests/worker/test_starting_again.py::test_sc14_a_run_left_by_an_escalation_or_refusal_starts_afresh` |
| SC-15 | R-18 | *(pending)* |
| SC-16 | R-19 | *(pending)* |
| SC-17 | R-20 | *(pending)* |
| SC-18 | R-22 | `tests/worker/test_at_commit.py::test_sc18_with_no_commit_work_issues_the_commands_it_issued_before`, `tests/worker/test_at_commit.py::test_sc18_an_existing_worktree_or_branch_is_still_refused`, `tests/worker/test_starting_again.py::test_sc18_by_default_a_worktree_or_branch_left_behind_is_refused` |
