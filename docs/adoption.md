# Adopting agent-framework in a project

How a repo goes from zero to a gated worker PR. The framework coordinates
through the methodology's artifacts (ADR 0001) — most of adoption is the
target project having them; the framework-specific surface is one config
file, one CI job, one secret. Kept honest by the opn-mcp pilot
(project-portability R-5/R-6): every step below was actually required
there.

## Prerequisites (the target repo)

1. **Methodology artifacts** — `specs/<slug>/spec.md` with `R-n`/`SC-n`
   ids and a Traceability table, `tasks.md` with `T-n` tasks tracing to
   criteria, and a spec-coverage check in CI (adapt the methodology's
   reference checker, its ADR 0017). An existing codebase adopts these
   forward-only per the methodology's `adopting.md`.
2. **Deterministic CI** on every PR (the validator judges CI evidence,
   never re-runs tests), with a required status check.
3. On the dispatching machine: the `claude` CLI (worker sessions;
   auth per ADR 0004 — Max subscription or `ANTHROPIC_API_KEY`), `gh`
   authenticated for the repo, and `git`.

## Target-side changes (the adoption PR)

1. **`agent-framework.toml`** at the repo root:

   ```toml
   [roles]
   worker    = { provider = "anthropic", model = "<anthropic-model-id>" }
   validator = { provider = "google",    model = "<gemini-model-id>" }

   [project]
   gate_commands = [ ... this repo's real gate, in order ... ]
   conventions_note = "Read CLAUDE.md; <project-specific rules workers must know>."
   test_pattern = '...'   # omit for the Python default: ^(?:async\s+)?def\s+(test_\w+)
   test_paths = ["..."]   # omit for the Python default: ["tests/**/*.py"]
   ignore_checks = ["validator", "<any conditional advisory checks>"]
   ```

   Use each provider's current model IDs; this repo's own
   `agent-framework.toml` is a working example. No secrets here, ever.
   A role's binding may also set `effort = "low"`, `"medium"` or
   `"high"` — how much reasoning its model is asked to spend; each
   provider adapter translates it (Google: the thinking level; Anthropic:
   the output effort). Leave it out for the provider's default. More
   effort is more tokens and time on every call, and on some models it
   is the most the model may think, not what it must — measure it with
   the eval before keeping it. It applies to roles reached through an
   adapter (the validator); the worker session does not take it, and a
   `worker` binding that sets it is refused. `gate_commands` are what a worker must run
   green before committing; `test_pattern` needs exactly one capture
   group (the test name) — non-Python projects set their own.
   `test_paths` says which changed files are test files (`**/` spans
   directories, `*` stays within one); a non-Python project sets it
   together with `test_pattern`, e.g. `["src/**/*.test.js"]`, or the
   validator finds no tests to cite.
   `ignore_checks` entries are **check names** (the job name GitHub
   reports, e.g. `review`), not workflow filenames — the pilot's first
   worker PR was REJECTed on exactly this confusion (opn-mcp#22).
2. **`.worktrees/`** in `.gitignore`.
3. **The advisory validator CI job** — copy the `validator` job from this
   repo's `.github/workflows/ci.yml`, adjusting: `needs:` to the target's
   required check name, and the install line. Keep `continue-on-error:
   true` and do **not** add it to required checks until its judgment has
   earned trust on your PRs.
   The validator exits 0 on PASS, 1 on REJECT, and **3 when it could not
   judge** — the model's answer was cut off or declined, the provider
   was rate-limited or down, or the model reported a defect but every
   finding quoted something that is not in what it was sent (each dropped
   finding is in the log, with the quote that was not found). Exit 3 is
   not a verdict on the pull request; its output names the reason. On the
   free tier, expect it occasionally. A REJECT's findings are the ones
   whose quoted evidence was found; `check` is one of `test-honesty`,
   `spec-conformance`, `criteria-integrity` for a judgment finding.
   The judgment checks that the work matches its task and the criteria
   it claims, and nothing else: a bug they do not state is not grounds
   for a REJECT (ADR 0008).
   The job holds a secret, so it must not run the pull request's code:
   keep its checkout on your **default branch** (`ref:` as in this repo's
   job), so `agent-framework.toml` — the roster and the gate's settings —
   is the merged one, and install the framework from its own `main` with
   `uvx`. The PR reaches the validator only as data, through the API —
   its title and description included, which the judgment reads as the
   author's account and never as instructions.
4. **A credential for your validator's provider** on the repo. For a
   Google model, the `GEMINI_API_KEY` secret (a free-tier AI Studio key
   is enough): `gh secret set GEMINI_API_KEY --repo <owner/name> --body ...`
   from a shell holding it. For an Anthropic model, an
   `ANTHROPIC_API_KEY` secret, or Workload Identity Federation as this
   repo's job does — never both, since a key outranks federation. Set a
   spend cap on a metered account first. Without a credential the job
   skips politely — as it also does on fork PRs, which receive none.

## Installing the framework

- **In CI**: `uvx --from git+https://github.com/vpciii/agent-framework
  agent-framework-validate ...` — requires this repo to be readable from
  the target's CI (public, or a read PAT).
- **Locally** (for dispatching workers): `uv tool install
  ~/Developer/agent-framework` or add it as a dev dependency; both
  console commands (`agent-framework-worker`, `agent-framework-validate`)
  and the `python -m` forms work. Run them **from the target repo's
  root** — config, specs, and worktrees resolve from cwd.

## The first task

A PR's `SC-` claims are judged against the spec's own text, so the PR
must say which spec it belongs to: name a `specs/<slug>/` path in the PR
body (worker PRs always do), or change exactly one spec's files. A claim
the validator cannot tie to a spec is REJECTed without a model call.

The validator takes each criterion's citation from the spec's
**Traceability table as the PR leaves it** — so the PR that adds a test
must also fill in that criterion's row with the test's full
`path::test_name`. A claimed criterion whose row is empty or `*(pending)*`,
or names a test that is not there or does not mention the id, is REJECTed
without a model call. A test the PR did not change can be cited.

Worker tasks come from the target's own artifacts: draft a small
`specs/<slug>/` (spec + tasks) under the target's methodology, get it
signed off, then from the target root:

```
agent-framework-worker <slug> <task-id>
```

The task must name what it satisfies: its section in `tasks.md` needs a
`- **Satisfies:** SC-…` line with at least one criterion the spec
defines. A task that claims none is refused before any session starts —
without a criterion there is nothing for the validator to check.

Every session runs **confined** (ADR 0007): its commands can write only
inside the worktree, reach no network host, and read nothing under your
home directory except the repository and git's user configuration. There
is no flag to turn this off. What your toolchain needs beyond that, declare
in `[project]`:

```toml
session_write_paths = ["~/.cache/uv"]         # caches the gate writes
session_read_paths  = ["~/.local/share/uv"]   # toolchains installed under ~
session_network     = ["pypi.org", "files.pythonhosted.org"]
session_env         = []                      # extra variable names to pass through
```

Each field, and what it must look like:

| Field | Widens | Entries |
|---|---|---|
| `session_write_paths` | where a command may write (and read) | absolute, or starting `~/` |
| `session_read_paths` | what a command may read under your home directory | absolute, or starting `~/` |
| `session_network` | which hosts a command may reach | bare host names — no scheme, path, port or wildcard |
| `session_env` | which of your shell's variables the session sees | variable names |
| `protected_paths` | (narrows) what a session's commits may not touch | path patterns, as for `test_paths`; default `.github/**`, `agent-framework.toml` |

The example above is this repo's own (uv), and its whole gate runs under
it. For another toolchain, declare the same three things — its cache, its
installed runtimes if they live under your home directory, and its package
host. An npm project, for instance (illustrative; not yet run under the
profile):

```toml
session_write_paths = ["~/.npm"]
session_read_paths  = ["~/.nvm"]
session_network     = ["registry.npmjs.org"]
```

The session's environment is an allowlist: `PATH`, `HOME`, `USER`,
`LOGNAME`, `SHELL`, `LANG`, `LC_*`, `TERM`, `TMPDIR`, the session tool's
own `ANTHROPIC_*` variables and four named `CLAUDE_*` ones. A token your
shell holds (`GH_TOKEN`, a cloud key) does not reach it unless you name it
in `session_env` — and anything you name, the session can read.

**When a gate command is refused.** The first confined dispatch in a new
project usually finds a path or host nobody declared. The refusal is loud
and names it (`Operation not permitted … <path>`, or `host is not on the
allow list`); the session is told to escalate with that text rather than
work around it. Add what it names and dispatch again. A gate step that
needs something a session should not have — a Docker socket, a deploy
credential — is better left to CI than declared.

**Dispatch from a checkout that is not inside another one.** A session
may read the checkout it was dispatched from and that repository's git
directory, and nothing above them. A toolchain that looks for project
files in parent directories then fails when a parent holds one: on
2026-11-17 a task dispatched from a git worktree kept under the main
checkout (`<repo>/.claude/worktrees/<name>`) had every `uv run …` gate
command refused with `failed to open file <repo>/pyproject.toml:
Operation not permitted`, and the session escalated with its work
committed and unpushed. The same task dispatched from the main checkout
ran its gate and opened its pull request. Dispatch from the main
checkout, or from a clone with no project above it; do not declare the
parent in `session_read_paths` to get past it — that hands the session
a second working copy to read.

**Platform.** macOS only for now. The profile depends on Claude Code's
restricted mode and OS sandbox and fails closed: where the sandbox is
unavailable, the session does not start.

Outcomes: exit 0 = PR opened (with its `Satisfies:` declaration, facing
the advisory gate); 2 = the worker escalated (read
`specs/<slug>/escalations/`); 3 = timeout, spend limit reached, or error
(worktree preserved; `--spend-limit USD` sets a session's limit, $10 at
list price by default, and on the Max plan it measures the plan's
allowance, not money); every session's output is kept locally as a
session record in `.worktrees/records/` — read it to see what a session
did and what it cost;
4 = handoff refused — the session finished but its commits changed a
spec's contract, a path in `protected_paths` (default `.github/**` and
`agent-framework.toml`), or deleted a test file. Nothing was pushed; the
outcome and a `refused` issue name each finding, and the worktree is kept.

Task-brief authoring lessons (paid for in this framework's own repo):
put **all** expected file changes in `Touches` — including the spec's
Traceability row — or the worker won't make them; name the test-harness
pattern to follow; state what must NOT be modified; for tests-only
tasks, say that behavioral surprises are escalation material, not fixes.

## Measuring the validator's judgment (the eval)

The gate's judgment is a model call. The eval measures how well it
judges on a fixed set of cases with known answers, so a change to its
instructions or its model can be compared before and after. It is run by
hand, with a provider key in your shell; no CI job runs it and its tests
need no key.

**Run it.** From the repository root, with the validator's key set in the
shell only (never in `agent-framework.toml`):

```bash
uv run agent-framework-eval run --pause 5
```

It judges every case in `evals/validator/cases/` through the roster's
validator role, prints one line per judgment on stderr and the scorecard
on stdout, and writes `evals/validator/results/<date>-<model>.json`. It
never writes over an existing result; name another file with `--out`.
`--only <id> ...` judges just the named cases, `--runs N` judges each
case N times, and `--pause SECONDS` spaces the calls to stay under a
rate limit. A provider error or an unreadable answer on one case is
recorded as could-not-judge and the run goes on. Exit 0 means the run
completed, whatever the score; 2 means it could not start.

**Read the scorecard.** Accepted cases should pass; seeded-defect cases
should be rejected with a finding under the checklist item that was
seeded. The scorecard counts each, lists every case judged wrongly with
the model's findings, and never counts could-not-judge as right or wrong.
A wrongly judged case is for a human to decide: either the judgment was
wrong, or the case's expected answer is, and that answer changes only in
its own reviewed change.

**Compare two runs.**

```bash
uv run agent-framework-eval compare <before>.json <after>.json
```

It prints the cases whose class changed. Both results are read against
the answers in the case set as it is now (`--cases DIR`, the same default
as `run`), so a corrected answer never makes two results incomparable;
the cases whose answer changed since each run are named. Two results are
comparable when their cases sent the judgment the same thing — the same
inputs fingerprint; otherwise it says so and exits 2. A run made with
`--only` judged some of the set: only the cases both results judged are
compared, and the rest are listed as judged in one result only.

**Read a stored result.**

```bash
uv run agent-framework-eval show <result>.json
```

It prints the scorecard of a result made earlier, classed against
today's answers, and writes nothing. When a wrongly judged case turns out
to be a real defect, correct the case's answer and run `show` again: no
new run is needed, because nothing the model was sent has changed. If a
case's bundle or a seeded edit has changed since the run, or a case was
added or removed, the result is of something else and `show` and
`compare` refuse it with exit 2.

**Build your own set.** The cases in this repository are its own pull
requests; a target repository freezes its own:

```bash
uv run agent-framework-eval freeze <pr>
```

This writes `evals/validator/cases/pr-<n>.json` — an accepted case — from
a merged pull request, collected as the gate collects it. It refuses a
pull request that is not merged, that claims no criteria, or that the
deterministic stage rejects, naming the check. Freezing a pull request
again rebuilds its bundle and keeps the expected answer already in the
file.

A seeded-defect case is a small hand-written file beside its accepted
case, `pr-<n>--<name>.json`: the accepted case's id, the checklist item
(`test-honesty`, `spec-conformance` or `criteria-integrity`), a
one-line reason, and an edit of exact replacements in
the diff or in a test file. Each replacement must match exactly once.
Copy one of this repository's as a pattern, and keep a test like
`tests/evals/test_set.py`, which loads every case and puts it through the
deterministic stage with no model call.

## Measuring the worker (the worker eval)

The worker is a model session too. The worker eval measures what it
produces for tasks the repository has already merged, so a change to its
model, brief, confinement profile, time budget or spend limit can be
compared before and after. It is run by hand; no CI job runs it. Unlike
the validator's eval it starts real worker sessions, so a run takes
minutes per case and costs what those sessions cost.

**Run it.** From a checkout that is not inside another one (see above),
on `main`:

```bash
uv run agent-framework-eval worker run
```

For each case in `evals/worker/cases/` it cuts a worktree at the case's
start commit, builds the brief there, and runs one worker session under
the confinement profile with the roster's worker model. Nothing is
pushed, no pull request is opened and no alert is raised. A completed
session is then scored by code at its last commit: the gate commands,
the handoff check, the reference tests, and its diff. It prints one line
per run on stderr and the scorecard on stdout, and writes
`evals/worker/results/<date>-<model>.json`; it never writes over an
existing result. `--only <id> ...` runs just the named cases, `--runs N`
runs each case N times, `--timeout` and `--spend-limit` set each
session's limits (1800 s and $10 by default), `--roster FILE` tries
another model without a code change, and `--keep` leaves the worktrees
in place. Exit 0 means the run completed, whatever the score; 2 means it
could not start.

The gate commands and the reference tests run the session's code on
your machine, outside the session's sandbox. Read
`docs/architecture.md`'s trust boundaries before running it on a
repository whose tasks you did not write.

**Read the scorecard.** A run is *ready for review* when the session
completed, every gate command passed and the handoff check found
nothing — what a dispatch would have opened a pull request for. The
reference tests are reported beside that, never in it: a correct result
can fail them. A run the eval itself could not make is *could not run*
and is counted on its own. A case whose runs land in different classes
is marked unstable.

**Read a stored result, and compare two.**

```bash
uv run agent-framework-eval worker show <result>.json
```

```bash
uv run agent-framework-eval worker compare <before>.json <after>.json
```

`show` prints the scorecard, then every run that is not ready for review
and every reference-test failure, with where its session record, patch
and gate output are kept on the machine that made the run. `compare`
prints the cases whose class or reference-test result changed; results
over different case sets are not comparable, and it says so and exits 2.

**Build your own set.**

```bash
uv run agent-framework-eval worker freeze <pr>
```

This writes `evals/worker/cases/pr-<n>.json` from a merged task pull
request: the task it names, its start and head commits, and the test
files it changed that cite the task's criteria. It refuses a pull
request that is not merged, that names no task, whose task is not in
`tasks.md` at its start commit, or that changed no such test. The set's
`evals/worker/settings.toml` holds the gate commands and session
settings every case runs under.

## What stays framework-side

The framework repo owns the gate semantics (its ADR 0005), the brief
format, the verdict schema, and these docs. A target repo owns its
config, its CI wiring, its specs, and every merge decision — the human
is author of record in both places.
