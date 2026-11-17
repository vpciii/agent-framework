# Plan: An eval for the worker

- **Status:** Approved
- **Date:** 2026-11-15
- **Approved:** 2026-11-17, signed off by vpc, accepting the two items
  flagged for sign-off: the gate and reference tests run the session's
  code outside its sandbox (see *Risks*), and the `ci` job checks out
  full history (`fetch-depth: 0`)
- **Author:** Claude (draft) — vpc is author of record
- **Spec:** ./spec.md
- **Related ADRs:** ADR 0001, ADR 0004, ADR 0007, ADR 0009

> This plan freezes with its spec: editable while `Draft` / `Under
> review` / `Approved`, and a historical record once the PR that marks
> the spec `Implemented` merges (methodology §2, ADR 0027). A
> contradiction found later goes to a test, a new spec, or an ADR — not
> back into this file.

## Approach

A worker half for `agent_framework.evals`, beside the validator's half,
in the same shape: a pure core (cases, classes, scorecard) and thin edges
(freeze, run, CLI).

1. **The run reuses the worker's parts, not its handoff.** It calls the
   worker's own `parse_task`, `build_brief`, `profile_args`,
   `session_env`, `run_session` and `check_handoff`, so the eval measures
   the worker as it is and cannot drift from it (spec R-4). It never
   calls `work()`: everything after the handoff check — pushing, the
   pull request, the escalation file, the alerts — is the part the eval
   must not do (R-5), so it is simply not reached.
2. **Two small seams in the worker, default unchanged.** The worker
   assumes every tree is cut from `origin/main`. The eval needs a tree
   cut from a past commit, and a handoff check measured against that
   commit. So `worktree.py` gains a function that adds a detached
   worktree at a given commit, and `check_handoff` (and the handoff
   note's commit list) take the base commit as a parameter whose default
   is today's `origin/main` merge base. A dispatch behaves exactly as
   before; the worker's existing tests prove it.
3. **A case is a JSON file; the set is a directory with one settings
   file.** `evals/worker/cases/pr-<n>.json` names the task, the reference
   pull request and its reference tests. `evals/worker/settings.toml`
   holds the one `[project]` table every case runs under — gate
   commands, conventions note, session paths, hosts and variable names —
   in the format `agent-framework.toml` already uses, loaded by the same
   `load_project_config` (spec R-4, decided 2026-11-15). It also holds
   the command that runs the reference tests.
4. **The brief is built at the start commit.** The run cuts the
   worktree first, then reads the task and spec from the worktree's own
   `specs/` and builds the brief from them, so the session gets the task
   exactly as it was written then.
5. **Scoring is code over what a run leaves.** After the session, the
   eval runs each gate command in the worktree, runs the handoff check,
   lays the reference test files over a copy of the tree and runs them,
   measures the diff, and reads cost and turns from the session record
   (`read_end`, from specs/worker-spend-and-record). No model is asked
   anything after the session ends.
6. **One command, a `worker` group.** `agent-framework-eval worker
   freeze|run|show|compare`, so the validator's commands are unchanged.

### What a run of one case does

```
cut   git worktree add --detach .worktrees/eval/<run>/<case>-<n> <start>
brief parse_task + build_brief from that worktree's specs/, settings.toml
run   run_session(...)  record: .worktrees/records/eval-<run>-<case>-<n>.jsonl
                        limits: the run's time budget and spend limit
score outcome; if completed:
        each gate command in the worktree → pass/fail, output to a log
        check_handoff(base=<start>) → findings
        copy the tree; lay the reference test files (at <head>) over it;
        run the reference-test command on them → pass/fail, output to a log
        git diff <start>..HEAD → a patch file and its size
      always: cost and turns from the record, elapsed time
keep  the patch, the logs, the record: .worktrees/eval/<run>/
drop  the worktree and its copy (unless --keep)
```

### The classes

| Session ended | Gate | Handoff check | Class |
|---|---|---|---|
| completed | every command passed | no finding | `ready` |
| completed | a command failed | — | `gate-failed` |
| completed | passed | a finding | `refused` |
| escalated | — | — | `escalated` |
| time budget | — | — | `timed-out` |
| spend limit | — | — | `spend-limit` |
| any other session error | — | — | `error` |
| the eval itself failed (checkout, setup) | — | — | `could-not-run` |

The reference tests are a second, separate column — `passed`, `failed`
or `not-run` (when the session did not complete) — never part of the
class (spec R-8, decided 2026-11-15). `could-not-run` is counted on its
own, never as the worker's success or failure (R-7). With several runs of
a case, the counts are of runs, and a case whose runs land in different
classes is marked unstable.

## Components touched

- `src/agent_framework/worker/worktree.py` — **add** `add_detached(path,
  commit)`, which records the result file in the repository's exclude
  file as `create_worktree` does, so no session can commit it;
  `create_worktree` unchanged.
- `src/agent_framework/worker/handoff_check.py`,
  `src/agent_framework/worker/handoff.py` — `check_handoff` and the
  handoff note take an optional base commit; the default is what it is
  today.
- `src/agent_framework/evals/worker/` — **new** subpackage:
  `case.py` (the case, the settings file, load, the case-set
  fingerprint), `freeze.py`, `run.py`, `scorecard.py` (classes, counts,
  the result, show, compare).
- `src/agent_framework/evals/__main__.py` — the `worker` subcommand
  group, delegating to the subpackage.
- `evals/worker/settings.toml`, `evals/worker/cases/*.json` — **new.**
- `evals/worker/results/*.json` — **new.** Recorded runs; the first is
  the baseline.
- `.github/workflows/ci.yml` — the `ci` job's checkout fetches the full
  history (`fetch-depth: 0`), so the CI test can read each case's start
  commit (spec SC-2). It still runs with no secret.
- `docs/glossary.md`, `docs/architecture.md` (components, the trust
  boundary below, the before-and-after rule of R-13), `docs/adoption.md`.
- **Not touched:** the roster, `providers/`, `validator/`, the worker's
  dispatch path, `confinement.py`.

## Data model changes

Nothing stored outside the repository except a run's working files under
`.worktrees/` (already ignored by git). Three file shapes.

A case, `evals/worker/cases/pr-31.json`:

```json
{
  "id": "pr-31",
  "task": {"spec": "verdict-rendering", "task": "T-1"},
  "reference": {"repo": "vpciii/agent-framework", "pr": 31,
                "start": "<commit>", "head": "<commit>"},
  "reference_tests": ["tests/validator/test_render.py"],
  "provenance": {"frozen": "2026-11-16", "by": "agent-framework-eval worker freeze"}
}
```

`start` is the merge base of the pull request's head and the commit its
merge landed on — where the work began. `reference_tests` are the test
files at `head` that the pull request changed and that cite one of the
task's claimed criteria.

The settings, `evals/worker/settings.toml`:

```toml
# Every worker eval case runs under this, not its start commit's
# agent-framework.toml (specs/worker-eval R-4).
[project]
gate_commands = ["uv run ruff check .", "uv run mypy --strict", "uv run pytest",
                 "uv run python scripts/check_spec_coverage.py --include-approved"]
conventions_note = "Read CLAUDE.md and docs/glossary.md; use the glossary's terms exactly."
session_write_paths = ["~/.cache/uv"]
session_read_paths  = ["~/.local/share/uv"]
session_network     = ["pypi.org", "files.pythonhosted.org"]

[eval]
reference_test_command = "uv run pytest {files}"
```

A result, `evals/worker/results/2026-11-20-claude-opus-5-5.json`:

```json
{
  "model": "anthropic:claude-opus-5-5", "claude_code": "2.1.325",
  "date": "2026-11-20", "runs": 1, "time_budget_s": 1800, "spend_limit_usd": 10.0,
  "case_set": "<12 hex>",
  "briefs": {"pr-31": "<12 hex>"},
  "results": [
    {"case": "pr-31", "run": 1, "class": "ready", "reference_tests": "passed",
     "gate": [{"command": "uv run pytest", "passed": true}],
     "handoff": [], "diff_lines": 94, "cost_usd": 1.84, "turns": 37,
     "elapsed_s": 612, "kept": ".worktrees/eval/2026-11-20-1/pr-31-1"}
  ],
  "scorecard": {"ready": 1, "gate-failed": 0, "refused": 0, "escalated": 0,
                "timed-out": 0, "spend-limit": 0, "error": 0, "could-not-run": 0,
                "reference_tests": {"passed": 1, "failed": 0, "not-run": 0},
                "cost_usd": {"total": 1.84, "median": 1.84},
                "elapsed_s": {"total": 612, "median": 612}}
}
```

`kept` points at the working files on the machine that made the run; the
committed result is the scorecard and the per-run facts. Data
sensitivity: case files are this public repository's own history; the
session records and patches stay under `.worktrees/` and are never
committed (they hold whatever a session read).

## API changes

One subcommand group on the existing command. Nothing existing changes.

```
agent-framework-eval worker freeze <pr> [--repo OWNER/NAME] [--cases DIR]
    Writes <DIR>/pr-<n>.json. Refuses a pull request that is not merged,
    names no T-n task, or whose task is not in tasks.md at its start
    commit — naming why. Exit 0 written, 2 refused.

agent-framework-eval worker run [--cases DIR] [--roster FILE] [--runs N]
        [--only ID ...] [--timeout SECONDS] [--spend-limit USD] [--keep] [--out FILE]
    Runs every case (or the named ones), one at a time, printing one line
    per run as it ends; prints the scorecard; writes the result file.
    Exit 0 when the run completed, whatever the score.

agent-framework-eval worker show <result>
agent-framework-eval worker compare <result> <result>
    The scorecard, the runs not ready for review and the reference-test
    failures with where their files are kept; for compare, the cases
    whose class or reference-test result changed. Results over different
    case sets are not comparable: compare says so and exits 2.
```

`--roster` defaults to `agent-framework.toml`, so trying another model is
a roster file, never a code change (ADR 0001). `--timeout` and
`--spend-limit` default to the worker's own defaults (1800 s, $10).

## Alternatives considered

- **Call `work()` with a "no handoff" flag.** One function to keep in
  step. Rejected: it puts an eval switch on the dispatch path, where a
  bug in the flag could push or alert from an eval run; composing the
  parts keeps the dispatch untouched.
- **Store the task text in the case file**, so nothing needs git
  history. Rejected: the session must work in the repository at the
  start commit anyway, and two copies of a spec drift. The cost is the
  CI checkout's full history (small for this repository).
- **Run each case under its start commit's own `agent-framework.toml`.**
  Truer to the past. Rejected by decision (2026-11-15): commits before
  the confinement fields cannot reach the package host, and runs should
  differ only in the task.
- **Score with the validator as well.** A ready-made judgment of the
  diff. Deferred (spec, out of scope): it puts a model in the score and
  costs a call per run.
- **Run cases in parallel.** Faster. Deferred: sessions would compete
  for the plan's rate limit, and the measurement of one run's cost comes
  first.

## Risks

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| **The gate and the reference tests run the session's code outside its sandbox**, with the user's own access | Certain | Medium — model-written code runs on vpc's machine unconfined | They run with the session's allowlisted environment (no secret in it), in the worktree, from a human's shell; the code is what a reviewer would run checking out the pull request. Recorded as a trust boundary in `architecture.md`. Confining them too is a follow-up |
| A run uses much of the Max plan's allowance, or hits its rate limit | Medium | Medium — a run stops part-way | One case at a time; the spend limit bounds each session; `--only` re-runs the rest; the baseline measures what a run costs (R-12) |
| Old start commits no longer build (a dependency yanked, a lockfile that no longer resolves) | Medium | Low — that case is could-not-run | R-7 keeps the run going; such a case is replaced in its own reviewed change |
| A correct result fails the reference tests | Medium | Low | Reported beside "ready for review", never in it; R-10 lists every failure with its patch for a human to read |
| One run per case is mostly noise | High | Medium — a comparison reads more than it shows | `--runs N`; the scorecard marks unstable cases and prints its run count beside every number; the spec claims no significance |
| A refactor of the worker breaks the two seams' defaults | Low | High — a dispatch cut from the wrong base | The worker's existing tests run unchanged, and each seam gets a test that its default is today's behavior |
| Full history in the CI checkout slows CI | Low | Low | The repository is small; measured in the PR that makes the change |

## Rollout

Six PRs (`tasks.md`), all additive:

1. The two worker seams, with no behavior change.
2. The case file, the settings file, loading and fingerprints, and the
   CI check that every case builds its brief at its start commit (with
   the `fetch-depth: 0` change).
3. `freeze`.
4. `run`: one case through worktree, session, gate, handoff check,
   reference tests and record, and could-not-run.
5. The scorecard, the result file, `show` and `compare`.
6. The cases, the docs, and the first baseline run by vpc (R-12).

Undo for any step is reverting its PR. No test in CI starts a session.

## Observability

The run prints one line per run of a case as it ends — case, class,
reference tests, cost, elapsed — so a run of hours is visibly alive,
then the scorecard. Each run's working files (session record, patch, gate
and reference-test output) are kept under `.worktrees/eval/<run>/`. The
result file is the durable record.

## Test strategy

- **Unit, pure:** case round-trip and every malformed shape (SC-1); the
  classes and counts, medians, unstable cases (SC-8); the result's
  fields, the fingerprints and the comparison (SC-9); the listing with
  kept paths (SC-10).
- **Integration, fake session and fake `gh`:** `freeze` writes a case
  that loads and refuses what it should (SC-3); a run over a small set in
  `tmp_path` builds each brief at the start commit and launches the
  session with the profile and limits (SC-4); no push, pull request or
  alert command is issued, nothing is written outside the run's files,
  and no workflow names the command (SC-5); a completed fake session's
  gate, handoff, reference-test and diff results are recorded, and every
  outcome's cost and time (SC-6); a start commit that cannot be checked
  out is could-not-run and the run goes on (SC-7). The gate commands in
  these tests are small scripts, not the repository's gate.
- **The worker's own suite, unchanged,** proves the seams' defaults.
- **Over the committed set, no session:** every case loads and builds its
  brief at its start commit (SC-2); the set meets R-11 (SC-11).
- **Live, cited not asserted:** the baseline run (R-12), quoted in the
  delivery PR.
