# Spec: An eval set for the validator's judgment

- **Status:** Approved
- **Date:** 2026-11-10
- **Author:** Claude (draft) — vpc is author of record
- **Related ADRs:** ADR 0005 (one per-PR gate; its judgment is one model
  call), ADR 0001 (roles are bound by the roster), ADR 0004 (which surface
  each role runs on)

> This spec is editable while `Draft` / `Under review` / `Approved`.
> When the PR that marks it `Implemented` merges it **freezes** into a
> historical record (methodology ADR 0027);
> a contradiction found later goes to a test, a new spec, or an ADR —
> not back into this file (methodology §2, §8).

## Problem

Nobody knows how often the validator's judgment is right.

The gate's deterministic stage is covered by tests. Its judgment is one
model call whose quality "is a prompt-engineering concern" (ADR 0005),
and nothing measures it. What is known comes from two runs on the same
merged pull request, #77: on 2026-11-09 the judgment returned a REJECT
resting on invented code; on 2026-11-10, after the finding-evidence
change, it returned a PASS. One of each is an anecdote. It does not say
whether the change helped, or whether the second run was luck.

Three things are waiting on a measurement:

- **Trust.** The gate is advisory "until its judgment has earned trust"
  (`docs/adoption.md`). There is no definition of earned.
- **Every change to the judgment.** Its instructions, its tool schema
  and what it is sent have each changed since 2026-11-09, none with a
  measurement of what it did to the judgment's answers.
- **Deferred decisions.** Showing the judge whole changed files instead
  of diff hunks (finding-evidence, non-goal) and a per-role effort
  setting (judgment-reliability, open question) were both put off "until
  the eval set can measure it".

The material for a measurement already exists. This repository has 19
merged task pull requests with a real `Satisfies:` declaration, each
accepted by the human. On 2026-11-10, 18 of them still collect into a
bundle that passes the deterministic stage with today's code — 8,000 to
83,000 characters of data each, about 770,000 in all.

## Goals

1. One command says how often the judgment is right on a fixed set of
   cases whose answers are known: how often it wrongly rejects accepted
   work, how often it misses a defect that was put there on purpose, and
   how often it cannot judge at all.
2. Two runs on the same cases can be compared, so a change to the
   judgment — or to the model behind it — is shown to help, not asserted
   to.
3. The cases are durable artifacts: reviewed like code, frozen, and
   runnable without GitHub.
4. A first baseline is on record.

## Non-goals

- **Gating anything on the score.** No CI check, no merge rule. The eval
  set measures; what to do with the number is a later decision.
- **Changing the judgment.** Not its instructions, its schema, what it is
  sent, or the roster. This spec builds the instrument only.
- Evaluating the deterministic stage (its tests do that), the worker, or
  the chief.
- Having a model write the defects or grade the findings. Every expected
  answer is a human's, and every score is computed by code.
- Claims of statistical significance. A few dozen cases show large
  effects and regressions; they do not resolve small ones.
- Cases from an adopting repository. The tooling takes a directory, so a
  project can build its own; this spec ships this repository's set.

## Requirements

- **R-1 (MUST)** An **eval case** is a file in this repository holding: a
  frozen evidence bundle — everything the judgment would be sent; the
  expected outcome, `pass` or `reject`; for `reject`, the one checklist
  item the defect falls under; a one-line reason; and its provenance (the
  pull request, its head commit, the date it was frozen).
- **R-2 (MUST)** There are two kinds of case. An **accepted case** is
  frozen from a merged pull request whose claims the human accepted; its
  expected outcome is `pass`. A **seeded-defect case** is an accepted case
  plus one named, exact edit to its diff or its tests that introduces one
  defect; its expected outcome is `reject`. The edit is stored as the
  edit, not as a second copy of the bundle, and one that does not apply
  exactly once is an error.
- **R-3 (MUST)** Every case, as stored, passes the gate's deterministic
  stage. This is checked in CI with no model call, so every case is one
  the judgment would really be asked about, and a case that rots is
  caught.
- **R-4 (MUST)** One command freezes a merged pull request into an
  accepted case.
- **R-5 (MUST)** One command runs the eval: for each case it makes the
  judgment exactly as the gate does — the same request, the same tool,
  the same parsing and quote check, through the roster's validator role —
  and records the outcome: pass, reject with its findings, or could not
  judge with its reason. A case may be run more than once.
- **R-6 (MUST)** A provider failure or rate limit on one case does not
  end the run. That case is "could not judge" and the run continues.
- **R-7 (MUST)** The run produces a **scorecard**:
  - accepted cases: passed, wrongly rejected, could not judge;
  - seeded-defect cases: caught (rejected with a finding under the
    seeded checklist item), rejected for another reason, missed (passed),
    could not judge;
  - the number of unsupported findings dropped, and the tokens used.

  "Could not judge" is never counted as right or as wrong.
- **R-8 (MUST)** Every wrongly rejected, missed and rejected-for-another-
  reason case is listed with the findings the model gave, so a human can
  decide whether the judgment was wrong or the case's expected answer is.
  A case's expected answer changes only as its own reviewed change.
- **R-9 (MUST)** A run's result says what was measured: the model, the
  date, a fingerprint of the judgment's instructions and tool schema, and
  a fingerprint of the case set. Two results are comparable when their
  case-set fingerprints match; the result says so when asked to compare
  two that do not.
- **R-10 (MUST NOT)** The eval MUST NOT run in a CI job, need a key for
  any test, or change what the gate does. Its own tests use a fake
  provider.
- **R-11 (MUST)** The initial set holds at least 12 accepted cases from
  this repository's merged task pull requests — #77 among them — and at
  least 9 seeded-defect cases: at least 3 each for test honesty, spec
  conformance and criteria integrity.
- **R-12 (SHOULD)** The delivery PR records a first baseline: one full
  run by the human, with a key, committed as a result file and cited.
- **R-13 (SHOULD)** From then on, a change to the judgment's
  instructions, its tool schema, what it is sent or the validator's model
  cites a run from before and after. Stated in `docs/architecture.md`;
  not enforced by code.

## Success criteria

- **SC-1** — A case file round-trips: frozen, written, read back and
  rebuilt into the same evidence bundle, with its expected outcome,
  checklist item, reason and provenance. A file missing any of them, or
  a `reject` case with no checklist item, fails to load naming the file.
  (R-1)
- **SC-2** — A seeded-defect case's bundle is its accepted case's bundle
  with exactly the named edit applied; an edit whose text is absent, or
  present twice, fails to load. (R-2)
- **SC-3** — Every case in the repository's set loads and passes the
  deterministic stage; a case that would be rejected there fails the
  test, naming the case and the check. (R-3)
- **SC-4** — The freeze command, given a pull request through a faked
  `gh`, writes an accepted case that loads. (R-4)
- **SC-5** — The run sends, for each case, the request the gate would
  send for that bundle, through the roster's validator role, and records
  pass, reject with findings, and could-not-judge with its reason — each
  demonstrated with a fake provider. (R-5)
- **SC-6** — A provider error on one case is recorded as could not judge
  and the remaining cases still run. (R-6)
- **SC-7** — The scorecard's counts are right for a run that contains
  one of each outcome for each kind of case; a seeded-defect case
  rejected under a different checklist item is counted as "another
  reason", not as caught; could-not-judge appears in neither the right
  nor the wrong count. (R-7)
- **SC-8** — The result lists each wrongly rejected, missed and
  other-reason case with the model's findings. (R-8)
- **SC-9** — The result carries the model, the date and both
  fingerprints; the instructions' fingerprint changes when the
  instructions or the schema change and not when the data does; the
  case-set fingerprint changes when a case is added, removed or edited;
  comparing two results with different case sets says they are not
  comparable. (R-9)
- **SC-10** — No CI job runs the eval, and the eval's tests pass with no
  provider key set. (R-10)
- **SC-11** — The repository's set meets the counts in R-11. (R-11)

## Glossary additions (proposed with this spec)

Added to `docs/glossary.md` in this spec's first implementing PR.

- **Eval set** — the fixed collection of eval cases the validator's
  judgment is measured on.
- **Eval case** — one frozen evidence bundle with the outcome a human
  expects of the judgment, `pass` or `reject`. Either an **accepted
  case** (a merged pull request as it was) or a **seeded-defect case**
  (an accepted case with one deliberate defect).
- **Scorecard** — the result of running the judgment over the eval set:
  how many accepted cases it passed or wrongly rejected, how many seeded
  defects it caught or missed, and how many it could not judge.

## Rollout and undo

Additive: new files and a new command; the gate is untouched. Undo is
reverting the PRs. Nothing is stored outside the repository.

It will take more than one PR — the tooling, the cases, the baseline —
so `plan.md` and `tasks.md` follow this spec's sign-off.

Cost of a full run, estimated from the measured #77 judgment (about 3
characters per input token): roughly 400,000 input tokens for the
initial set, plus the model's output. On the roster's validator that is
small in money; whether the free tier's daily limit allows a full run in
one sitting has not been measured.

## Open questions

All resolved 2026-11-10 (human sign-off: vpc accepted the six drafted
answers).

- [x] **Catching a seeded defect** is a REJECT with a finding under the
  seeded checklist item (R-7); a REJECT under another item is shown
  separately. Not chosen: requiring the finding's quotes to overlap the
  seeded text — more exact, and it needs the judgment to hand its quotes
  to the eval, which it does not do today.
- [x] **Runs per case: one by default, more on request** (R-5). A
  model's answer varies between runs; three runs per case triples the
  cost and shows which cases are unstable.
- [x] **Accepted cases: every merged task pull request that still passes
  the deterministic stage** — 18 on 2026-11-10 — rather than a
  hand-picked dozen. About 770,000 characters of frozen data in the
  repository.
- [x] **No seeded cases for the fourth checklist item** (the unstated
  edge case) at first. An edge case nobody stated has no mechanical
  ground truth; that item is measured only by how often it wrongly
  rejects accepted work — which is exactly what it did to #77.
- [x] **"Accepted by the human" is the answer key**, with R-8 as the
  correction path. An accepted pull request can hold a real defect; when
  the judgment finds one, the case's expected answer is changed by a
  reviewed edit, not argued with.
- [x] **No planning stage first.** The problem is already shown by two
  live runs and three deferred decisions, and the appetite is a few PRs.

Recorded at sign-off, 2026-11-10 — what the implementation found:

- **The set holds 27 accepted cases, not the 18 estimated above**, and
  about 1.16 million characters. Five older task pull requests that
  predate the `Satisfies:` line also pass the deterministic stage, and
  four more merged during the work. Three that pass were left out: #41
  (it declares `Satisfies: —`; the id the collector reads is in its
  explanation), #85 (a sign-off, not a task; its ids are prose mentions)
  and #92 (its diff is the set itself).
- **Freezing a pull request that already has a case** rebuilds the
  bundle and keeps the expected answer in the file, so rebuilding the
  set never resets an answer a human corrected (R-8).
- **The first baseline** (R-12) is
  `evals/validator/results/2026-11-10-gemini-3.8-flash.json`: 23 of 27
  accepted cases passed and 4 were wrongly rejected (`pr-18`, `pr-37`,
  `pr-59`, `pr-89`); 9 of 9 seeded defects were caught under the seeded
  item; nothing could not be judged. The four are not yet decided, and
  no expected answer has been changed.
- **Two defects the first runs showed**, each fixed in its own pull
  request: a run did not say why a case could not be judged (#94), and
  `compare` listed a case only one result had judged as changed (#96).

## Out of scope (for now)

- Running the eval on a schedule or from a manually triggered workflow.
- A merge rule or required check built on the score.
- Whole-file context for the judgment, a per-role effort setting, a
  per-request data fence and filtering what is sent as the diff — the
  changes this instrument exists to measure.
- Seeded cases drawn from real defects that escaped (the worktree base
  fixed by #63, the zero-claim crash fixed by #22).
- An eval for the worker or the chief.

## Traceability

| Criterion | Requirement(s) | Verified by (test) |
|---|---|---|
| SC-1 | R-1 | `tests/evals/test_case.py::test_sc1_an_accepted_case_round_trips_to_an_equal_bundle`, `tests/evals/test_case.py::test_sc1_an_accepted_case_can_carry_a_corrected_answer`, `tests/evals/test_case.py::test_sc1_a_malformed_case_fails_to_load_naming_the_file`, `tests/evals/test_case.py::test_sc1_a_file_that_is_not_json_fails_naming_the_file` |
| SC-2 | R-2 | `tests/evals/test_case.py::test_sc2_a_seeded_case_is_its_base_with_exactly_the_edit_applied`, `tests/evals/test_case.py::test_sc2_an_edit_that_does_not_apply_exactly_once_fails_to_load`, `tests/evals/test_case.py::test_sc2_a_seeded_case_needs_an_accepted_base_and_a_reject`, `tests/evals/test_case.py::test_sc2_the_set_loads_every_case_of_both_kinds` |
| SC-3 | R-3 | `tests/evals/test_set.py::test_sc3_every_case_in_the_set_loads_and_passes_the_deterministic_stage`, `tests/evals/test_set.py::test_sc3_a_case_the_stage_would_reject_is_named_with_its_check` |
| SC-4 | R-4 | `tests/evals/test_freeze.py::test_sc4_freeze_writes_an_accepted_case_that_loads_as_the_collected_bundle`, `tests/evals/test_freeze.py::test_sc4_freeze_refuses_what_is_not_an_accepted_case_and_writes_nothing`, `tests/evals/test_freeze.py::test_sc4_the_freeze_command_writes_the_case_and_says_where`, `tests/evals/test_freeze.py::test_sc4_the_freeze_command_exits_2_when_it_refuses` |
| SC-5 | R-5 | `tests/evals/test_run.py::test_sc5_each_case_is_sent_the_gates_own_request_through_the_validator_role`, `tests/evals/test_run.py::test_sc5_a_pass_and_a_reject_are_recorded_as_such`, `tests/evals/test_run.py::test_sc5_could_not_judge_is_recorded_with_its_reason`, `tests/evals/test_run.py::test_sc5_findings_dropped_before_no_verdict_are_counted`, `tests/evals/test_run.py::test_sc5_a_case_may_be_run_more_than_once`, `tests/evals/test_run.py::test_sc5_each_judgment_is_reported_as_it_is_made`, `tests/evals/test_cli.py::test_sc5_only_and_runs_choose_what_is_judged`, `tests/evals/test_cli.py::test_sc5_a_run_that_cannot_start_says_why_and_judges_nothing`, `tests/evals/test_cli.py::test_sc5_an_empty_or_malformed_set_is_refused`, `tests/evals/test_cli.py::test_sc5_a_recorded_result_is_never_overwritten` |
| SC-6 | R-6 | `tests/evals/test_run.py::test_sc6_a_provider_error_on_one_case_leaves_the_others_judged`, `tests/evals/test_run.py::test_sc6_the_pause_falls_between_judgments_and_not_after_the_last` |
| SC-7 | R-7 | `tests/evals/test_scorecard.py::test_sc7_each_outcome_of_each_kind_of_case_has_its_class`, `tests/evals/test_scorecard.py::test_sc7_an_accepted_case_with_a_corrected_answer_is_scored_as_a_defect`, `tests/evals/test_scorecard.py::test_sc7_the_scorecard_counts_one_of_each`, `tests/evals/test_scorecard.py::test_sc7_dropped_findings_and_tokens_are_summed`, `tests/evals/test_scorecard.py::test_sc7_a_case_whose_runs_disagree_is_marked_unstable` |
| SC-8 | R-8 | `tests/evals/test_scorecard.py::test_sc8_the_rendering_lists_each_wrong_case_with_its_findings`, `tests/evals/test_scorecard.py::test_sc8_the_rendering_puts_the_case_count_beside_every_rate`, `tests/evals/test_scorecard.py::test_sc8_a_run_with_nothing_judged_shows_no_rate` |
| SC-9 | R-9 | `tests/evals/test_scorecard.py::test_sc9_a_result_round_trips_with_what_was_measured`, `tests/evals/test_scorecard.py::test_sc9_a_malformed_result_file_is_a_typed_error`, `tests/evals/test_scorecard.py::test_sc9_the_instructions_fingerprint_moves_with_the_instructions_and_the_schema`, `tests/evals/test_scorecard.py::test_sc9_the_instructions_fingerprint_does_not_move_with_the_data`, `tests/evals/test_scorecard.py::test_sc9_results_on_different_case_sets_are_not_comparable`, `tests/evals/test_scorecard.py::test_sc9_comparable_results_show_the_cases_whose_class_changed`, `tests/evals/test_case.py::test_the_case_sets_fingerprint_moves_only_when_a_case_does`, `tests/evals/test_cli.py::test_sc9_compare_names_what_changed_and_refuses_different_case_sets` |
| SC-10 | R-10 | `tests/evals/test_cli.py::test_sc10_a_whole_run_needs_no_provider_key`, `tests/evals/test_cli.py::test_sc10_the_command_is_installed_as_agent_framework_eval`, `tests/test_ci_workflow.py::test_sc10_no_workflow_runs_the_eval` |
| SC-11 | R-11 | `tests/evals/test_set.py::test_sc11_the_set_has_enough_cases_of_each_kind` |
