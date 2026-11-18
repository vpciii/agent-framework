# Tasks: An eval for the worker

- **Status:** In progress
- **Approved:** 2026-11-17, signed off by vpc, accepting the three
  departures from the plan's rollout described below (seven tasks; the
  `ci` checkout change in T-7; T-1 claiming SC-4 and SC-6 in part)
- **Spec:** ./spec.md
- **Plan:** ./plan.md

PR-sized tasks derived from the plan. Each task traces to ≥1 success
criterion — the tests it must make pass cite those ids — and replaces its
`*(pending)*` Traceability rows as its tests land. Mark a task `[x]` with
its merged PR number when done. Task PRs carry a `Satisfies:` declaration
and name `specs/worker-eval/` in their body.

**DAG:** T-1, T-2 start in parallel (different files). T-2 → T-3;
T-2 → T-4; T-5 after T-1 and T-4; T-5 → T-6; T-7 after T-3 and T-6.
T-3 and T-4 touch different files and can proceed in parallel once T-2
merges.

**Criterion coverage:** SC-1, SC-2 → T-2 · SC-3 → T-3 · SC-8, SC-9,
SC-10 → T-4 · SC-4 → T-1 (the worktree half), T-5 · SC-5, SC-7 → T-5 ·
SC-6 → T-1 (the handoff check's base), T-6 · SC-11 → T-7. A criterion
claimed by two tasks is complete when the later one merges; each adds
its own test to the criterion's Traceability row.

**Seven tasks where the plan's rollout lists six.** The plan's step 4
(`run`) is split in two — launching a case (T-5) and scoring a completed
session (T-6) — to keep each near 300 lines of diff. The plan's steps 3
and 5 keep their content; step 5 (the scorecard) comes before `run`
here because it is pure and `run` writes its result through it. One
change moves between steps: the `ci` job's `fetch-depth: 0` goes from
step 2 to T-7, because `.github/**` is a protected path a worker's
commits may not change, and no committed case needs the history until
T-7 adds the first.

**Dispatch.** T-1 to T-6 are code and tests with no network beyond the
package index, and are for dispatch to a worker session, one at a time
in DAG order. They are also the first end-to-end use of the worker
since #73: for each dispatch, note whether it reached an open pull
request, whether that pull request merged without an interactive
session reworking it, what the session record says it cost, and which
alert fired (planning/durable-autonomy/options-a.md, option A4). **T-7
is not for dispatch:** freezing reads GitHub, the workflow file is
protected, and the baseline is the human's run (R-12).

**Dispatch tally.** Cost is what the session record reports.

| Task | Pull request | Merged without rework | Cost | Alert |
|---|---|---|---|---|
| T-1, first run | none | — | $0.66 | escalation (#133): dispatched from a checkout inside another one, so the gate could not run (docs/adoption.md) |
| T-1 | #134 | yes | $0.58 | none |
| T-2 | #136 | yes | $0.86 | none |
| T-3 | #137 | yes | $0.79 | none |
| T-4 | #138 | yes, over the validator's REJECT (below) | $0.89 | none |
| T-5 | #140 | yes | $1.46 | none |
| T-6 | #141 | yes | $1.10 | none |

Six tasks, six pull requests merged with no interactive rework, $5.68
reported for those six sessions; one alert, on T-1's first run.

T-4's pull request was about 480 lines and kept `show` / `compare` rather
than splitting them as its *Done when* says; the validator rejected it on
that alone, and vpc merged it as it stood on 2026-11-17. Splitting would
have moved about 40 lines, so the task was too large as written.

**Found reading #141, open before the baseline (T-7).** Neither is
asked for by a task or a criterion:

- The gate commands and the reference-test command run with no time
  limit. They run the session's code, so a test that hangs would hang
  the whole run; only the session itself has the time budget.
- The gate runs on the session's working tree, not strictly its last
  commit: a file the session left uncommitted is tested by the gate but
  is absent from the diff and from the handoff check.

---

### [x] T-1 — Cut a worktree at a commit; check a handoff against a base (#134)
- **Satisfies:** SC-4, SC-6
- **Depends on:** —
- **Touches:** `src/agent_framework/worker/{worktree,handoff_check,handoff}.py`,
  `tests/worker/{test_worktree,test_handoff_check}.py`,
  `specs/worker-eval/spec.md` (Traceability rows SC-4, SC-6)
- **Brief:** The two seams of the plan's Approach §2, with a dispatch's
  behavior unchanged. Add `add_detached(path, commit)` to `worktree.py`:
  it adds a detached worktree at the given commit and records the result
  file in the repository's exclude file exactly as `create_worktree`
  does; `create_worktree` itself is not changed. Give `check_handoff`,
  and the handoff note's commit list in `handoff.py`, an optional base
  commit whose default is what they compute today (the merge base with
  `origin/main`). Nothing calls either with a non-default value yet.
  Follow the real-git fixture pattern in `tests/worker/test_worktree.py`.
- **Done when:** a test citing SC-4 shows a worktree added at a past
  commit of a real repository is at that commit, detached, with the
  result file excluded; a test citing SC-6 shows `check_handoff` given a
  base reports findings for changes since that base and none for changes
  before it; a test for each seam shows the default is today's behavior;
  the worker's existing tests pass unmodified.

### [x] T-2 — The worker eval case, the settings file, and the brief check (#136)
- **Satisfies:** SC-1, SC-2
- **Depends on:** —
- **Touches:** `src/agent_framework/evals/worker/{__init__,case}.py` (new),
  `evals/worker/settings.toml` (new), `evals/worker/cases/` (new, empty
  but for a `.gitkeep`), `tests/evals/worker/test_case.py` (new),
  `docs/glossary.md`, `specs/worker-eval/spec.md` (Traceability rows)
- **Brief:** `case.py` holds the worker eval case and the set's
  settings in the shapes the plan's *Data model changes* gives: load and
  write a case file; load `settings.toml` (its `[project]` table through
  the existing `load_project_config`, plus `[eval]
  reference_test_command`); load a case set from a directory; compute
  the case-set fingerprint (12 hex characters over the cases and the
  settings, independent of file order). A file missing its task,
  reference pull request, start or head commit, reference tests or
  provenance fails to load with an error naming the file and the field.
  Add a function that, for one case, reads `specs/<slug>/tasks.md` and
  `spec.md` **at the case's start commit** (`git show`, no checkout) and
  builds the brief with the worker's own `parse_task` and `build_brief`
  under the set's settings. Commit `evals/worker/settings.toml` as the
  plan words it. Add the spec's four glossary terms to
  `docs/glossary.md` as the spec words them.
- **Done when:** tests citing SC-1 show the round trip and each missing
  field's error; tests citing SC-2 show, in a real repository built in
  `tmp_path`, that the brief is built from the start commit's artifacts
  (not the working tree's) and that a case whose task is absent there
  fails naming the case; and one test citing SC-2 runs the same check
  over every case in `evals/worker/cases/`, passing while the directory
  is empty. No session is started.

### [x] T-3 — Freeze a merged task pull request into a case (#137)
- **Satisfies:** SC-3
- **Depends on:** T-2
- **Touches:** `src/agent_framework/evals/worker/freeze.py` (new),
  `src/agent_framework/evals/__main__.py`,
  `tests/evals/worker/test_freeze.py` (new),
  `specs/worker-eval/spec.md` (Traceability row SC-3)
- **Brief:** `agent-framework-eval worker freeze <pr> [--repo OWNER/NAME]
  [--cases DIR]`, as the plan's *API changes* gives it. Through a GitHub
  seam like the one `evals/freeze.py` already uses, read the pull
  request's state, title, body, head commit and merge commit. The task
  is the spec slug and `T-n` the pull request names; `start` is the
  merge base of the head and the commit the merge landed on;
  `reference_tests` are the test files the pull request changed that, at
  `head`, cite one of the task's claimed criteria. Refuse — writing
  nothing, exit 2, saying why — a pull request that is not merged, that
  names no task, or whose task is not in `tasks.md` at its start commit.
  Add the `worker` subcommand group to the eval command without changing
  the validator's commands. The tests use a fake GitHub seam and a real
  repository in `tmp_path`; nothing here reaches the network.
- **Done when:** tests citing SC-3 show a frozen case loads through
  T-2's loader with the right start and head commits and reference test
  files, and each of the three refusals writes no file and names its
  reason. The validator's eval CLI tests pass unmodified.

### [x] T-4 — The worker scorecard, the result, show and compare (#138)
- **Satisfies:** SC-8, SC-9, SC-10
- **Depends on:** T-2
- **Touches:** `src/agent_framework/evals/worker/scorecard.py` (new),
  `src/agent_framework/evals/__main__.py`,
  `tests/evals/worker/test_scorecard.py` (new),
  `specs/worker-eval/spec.md` (Traceability rows)
- **Brief:** Pure code over recorded runs, no session and no git. Define
  the record of one run of a case and the plan's eight classes with its
  class table (`ready`, `gate-failed`, `refused`, `escalated`,
  `timed-out`, `spend-limit`, `error`, `could-not-run`), with the
  reference tests as a separate `passed` / `failed` / `not-run` value
  that never changes the class. Compute the worker scorecard: counts per
  class, per case and in total; reference-test counts; total and median
  reported cost and elapsed time; a case whose runs land in different
  classes marked unstable; `could-not-run` in neither the successes nor
  the failures. Define the result file in the plan's shape (model,
  Claude Code version, date, runs, limits, case-set fingerprint, brief
  fingerprints, results, scorecard), written and read back. Add
  `worker show <result>` and `worker compare <result> <result>`: the
  scorecard, then every run that is not `ready` and every reference-test
  failure with the kept paths of its session record, diff and gate
  output; `compare` lists the cases whose class or reference-test result
  changed, and for two results with different case-set fingerprints says
  they are not comparable and exits 2.
- **Done when:** tests citing SC-8 show the counts, medians and the
  unstable mark are what a hand-built list of runs says; tests citing
  SC-9 show a result round-trips with every field and that comparing
  different case sets is refused; tests citing SC-10 show the listing
  names every run that is not ready and every reference-test failure
  with its three paths. If the diff passes about 300 lines, split
  `show` / `compare` into a follow-up task and say so in the pull
  request.

### [x] T-5 — Run a case: worktree, brief, session, and nothing after it (#140)
- **Satisfies:** SC-4, SC-5, SC-7
- **Depends on:** T-1, T-4
- **Touches:** `src/agent_framework/evals/worker/run.py` (new),
  `src/agent_framework/evals/__main__.py`,
  `tests/evals/worker/test_run.py` (new),
  `specs/worker-eval/spec.md` (Traceability rows)
- **Brief:** `agent-framework-eval worker run`, with the plan's options
  (`--cases`, `--roster`, `--runs`, `--only`, `--timeout`,
  `--spend-limit`, `--keep`, `--out`). For each run of each case, one at
  a time: cut a detached worktree at the case's start commit under
  `.worktrees/eval/<run>/` (T-1's `add_detached`); build the brief from
  that worktree's own `specs/` under the set's settings; launch the
  session through the worker's own `profile_args`, `session_env` and
  `run_session`, with the roster's worker model, the time budget, the
  spend limit and a session record under `.worktrees/records/`. **Never
  call `work()`**, and issue no push, pull request or alert command.
  Record every run's outcome with the cost and turns its session record
  reports (`read_end`) and the elapsed time, as T-4's run record. That
  record's `kept` is the three paths T-4 merged with (`Kept`: session
  record, diff, gate output), not the single directory string in the
  plan's example; set the session record's path here. A
  completed session is recorded as completed with its gate, handoff,
  reference-test and diff fields unset (T-6 fills them). A failure of
  the eval itself on a case — the start commit cannot be checked out —
  makes that run `could-not-run` and the next case still runs. Print one
  line per run as it ends, then the scorecard; write the result file;
  exit 0 when the run completed, whatever the score. Remove each
  worktree afterwards unless `--keep`.
- **Done when:** with a fake session seam and a real repository in
  `tmp_path`, tests citing SC-4 show each session is launched with the
  brief built at its case's start commit, the confinement profile, the
  time budget, the spend limit and the roster's worker model, in a
  worktree at that commit, and that three runs of a case start three
  sessions in three worktrees; tests citing SC-5 show that across
  completed, escalated, timed-out, spend-limit and refused fake
  sessions no `git push`, `gh pr` or alert call is made and nothing is
  written outside the run's worktrees, session records and result file,
  and that no file under `.github/workflows/` names the eval command;
  tests citing SC-7 show a case with an unknown start commit is
  `could-not-run`, the next case runs, and the scorecard counts it in
  neither successes nor failures.

### [x] T-6 — Score a completed session (#141)
- **Satisfies:** SC-6
- **Depends on:** T-5
- **Touches:** `src/agent_framework/evals/worker/run.py`,
  `tests/evals/worker/test_score.py` (new),
  `specs/worker-eval/spec.md` (Traceability row SC-6)
- **Brief:** After a completed session, and with no model call: run each
  of the settings' gate commands in the worktree at the session's last
  commit, pass or fail, output to a log; run `check_handoff` with the
  case's start commit as its base (T-1); copy the session's tree, lay
  the reference test files at the case's `head` commit over the copy,
  and run the settings' reference-test command on them, pass or fail,
  output to a log; write `git diff <start>..HEAD` to a patch file and
  record its size. The class follows the plan's table: every gate
  command passed and no finding is `ready`; a failed command is
  `gate-failed`; a finding is `refused`. The gate and the reference
  tests run with the session's allowlisted environment (`session_env`),
  not the caller's. Keep the patch, the logs and the session record
  under `.worktrees/eval/<run>/` and record their paths; a gate that
  cannot be set up makes the run `could-not-run`. In the tests the gate
  commands are small scripts, not this repository's gate.
- **Done when:** tests citing SC-6 show, for a completed fake session
  that commits a change, each gate command's outcome at its last commit,
  the handoff check's findings, the reference tests' outcome against the
  session's code (passing when the session's code satisfies them,
  failing when it does not, with the reference versions laid over the
  session's own test files), the diff size, and the cost, turns and
  elapsed time; and for every other outcome, the outcome, cost, turns
  and elapsed time with the reference tests `not-run`.

### [ ] T-7 — Delivery: the cases, CI's history, the docs, the baseline
- **Satisfies:** SC-11
- **Depends on:** T-3, T-6
- **Touches:** `evals/worker/cases/*.json`, `evals/worker/results/*.json`,
  `.github/workflows/ci.yml`, `tests/evals/worker/test_case_set.py`
  (new), `docs/architecture.md`, `docs/adoption.md`,
  `specs/worker-eval/{spec,tasks}.md`
- **Brief:** Not for dispatch. Freeze #31, #38, #73, #88 and two more
  medium tasks from the validator's eval set (chosen here, and named in
  the pull request with why). Set `fetch-depth: 0` on the `ci` job's
  checkout so T-2's check can read every start commit, and cite the
  job's time before and after. In `docs/architecture.md`: the new
  components, the trust boundary the plan's *Risks* names (the gate and
  the reference tests run the session's code outside its sandbox), and
  R-13's before-and-after rule. In `docs/adoption.md`: the four
  commands. vpc runs the first baseline — one run of every case under
  the roster's current worker binding — and its result file is
  committed and quoted in the pull request with its total reported cost
  (R-12). Confirm the Traceability table has no pending row. Marking
  the spec `Implemented` is the human's sign-off, in its own PR.
- **Done when:** a test citing SC-11 shows the committed set holds at
  least 6 cases, among them #31, #38, #73 and #88; T-2's check passes
  over the committed set in CI; the pull request quotes the baseline;
  spec coverage passes with zero pending rows.
