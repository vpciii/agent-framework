# Spec: Worker confinement — a confined session, an allowlisted environment, a checked handoff

- **Status:** Approved
- **Date:** 2026-11-09
- **Author:** Claude (draft) — vpc is author of record
- **Related ADRs:** ADR 0007 (worker session confinement — this spec
  implements it), ADR 0004 (the worker is headless Claude Code),
  ADR 0001 (the profile sits behind the session seam), methodology
  ADR 0027 (an AI agent is an actor at a trust boundary)

> This spec is editable while `Draft` / `Under review` / `Approved`.
> When the PR that marks it `Implemented` merges it **freezes** into a
> historical record (methodology ADR 0027);
> a contradiction found later goes to a test, a new spec, or an ADR —
> not back into this file (methodology §2, §8).

## Problem

A worker session runs with everything the dispatching user has. The
framework passes it no limits, it inherits the shell's environment, and
the adoption document's dispatch command hands it
`--dangerously-skip-permissions`. Everything that keeps a session inside
its task — do not push, do not merge, do not edit the spec — is a sentence
in its brief.

That is noticed today only in the trust-boundaries section of
`docs/architecture.md`, written on 2026-11-09, which had to say so. It has
not yet gone wrong: every live session has complied. But the framework's
own claim is that the human is author of record, and with this repo's
ruleset (a green `ci` check, zero approvals) a session holding the user's
token could merge its own pull request. A session also reads whatever a
target repository contains, and whatever it can read it can commit — and
the orchestrator pushes its commits to a public repository.

ADR 0007 records the measurements and the decision. This spec is the
*what* of building it.

## Goals

1. A worker session cannot push, merge, reach an undeclared host, write
   outside its worktree, or read the user's credentials or other
   repositories — because the operating system refuses, not because the
   brief asks.
2. A session can still do its job: edit, run the project's gate, commit.
3. What a project's toolchain needs beyond the default is declared in the
   project's own config, in one place, reviewed like any change.
4. Nothing a session produces is pushed until code has checked that it
   left the contract, the CI configuration and the existing tests alone.
5. When the handoff is refused, the human hears about it.

## Non-goals

- Confining the **orchestrator** or narrowing the token it pushes with
  (ADR 0007, alternatives).
- Container or VM isolation (ADR 0007, alternatives).
- Scanning a diff for secrets.
- Linux support. On a platform where the sandbox is unavailable or
  unverified the worker refuses to start; making it work there is later
  work.
- Recording a session's transcript, cost or turn count, and alerting on a
  crashed session — real gaps from the same review, each its own change.
- Changing the validator, the brief's task content, or the result
  contract (`.worker-result.json`).

## Requirements

RFC 2119 keywords. Every `MUST` / `MUST NOT` is reflected in a success
criterion.

- **R-1 (MUST)** Every worker session is launched under the
  **confinement profile**: restricted mode; exactly the tools needed to
  read, edit and run commands in the worktree; nothing prompts (what would
  prompt is denied); the user's and the project's Claude settings, hooks,
  plugins and MCP servers are not loaded; every command runs in the OS
  sandbox; a command cannot opt out of the sandbox; and if the sandbox is
  unavailable the session does not start.
- **R-2 (MUST)** Under the profile a command may write only inside the
  session's worktree (and what the sandbox itself grants a linked worktree
  and a temporary directory), plus the paths the project declares in
  `session_write_paths`.
- **R-3 (MUST)** Under the profile a command may read nothing under the
  user's home directory except: the repository, git's user configuration,
  the project's `session_read_paths`, and its `session_write_paths`.
- **R-4 (MUST)** Under the profile a command may reach no network host
  except those the project declares in `session_network`; an undeclared
  host is refused, never prompted for.
- **R-5 (MUST NOT)** No caller of the worker — its CLI or its Python
  entry point — can pass arguments to the session or otherwise widen the
  profile at dispatch. The `--session-arg` option is removed.
- **R-6 (MUST)** The session's process environment is an allowlist: a
  fixed base the session tool and ordinary commands need, plus the
  variable names the project declares in `session_env`. Every other
  variable in the dispatching environment is absent.
- **R-7 (MUST)** Before pushing, the orchestrator runs the **handoff
  check** on the session's diff against the commit its worktree was cut
  from, and refuses the handoff if any of these hold:
  (a) a `spec.md` under the specs directory differs anywhere outside its
  Traceability section, or a `tasks.md` differs in anything but a task's
  checkbox mark;
  (b) a changed path matches the project's `protected_paths` (default:
  `.github/**` and `agent-framework.toml`);
  (c) a file matching the project's `test_paths` was deleted.
- **R-8 (MUST)** A refused handoff pushes nothing and opens no pull
  request; the worktree is kept; the outcome names every finding with its
  path; and an alert is raised the same way an escalation's is — one issue
  per task, labelled `refused`, with the phone push — and the resume card
  counts it among alert issues.
- **R-9 (MUST)** The git commands the orchestrator itself runs for a
  session's worktree never execute a repository hook.
- **R-10 (MUST)** The four new `[project]` fields (`session_write_paths`,
  `session_read_paths`, `session_network`, `session_env`) and
  `protected_paths` are validated when config is loaded; a malformed value
  fails loudly, naming the field. Absent, each is empty except
  `protected_paths`, which takes its default.
- **R-11 (MUST)** The brief tells the session what it cannot do — push,
  reach undeclared hosts, write outside its worktree, change the contract
  or a protected path — and that a task needing any of these is an
  escalation, not something to work around.
- **R-12 (SHOULD)** The delivery PR cites a live run: one real task
  completed in this repository under the profile, and the probe in *Live
  check* below showing each forbidden action blocked.
- **R-13 (SHOULD)** `docs/adoption.md` replaces the
  `--dangerously-skip-permissions` dispatch command with the confined one
  and a worked example of the new fields; `docs/architecture.md`'s worker
  entry under Trust boundaries is rewritten; both in the implementing PR.

## Success criteria

- **SC-1** — The session seam, faked, records a launch that carries the
  whole profile: restricted mode, the fixed tool list, no prompting, no
  user/project settings or MCP servers, and sandbox settings with the
  sandbox enabled, opt-out forbidden and fail-if-unavailable set. (R-1)
- **SC-2** — The sandbox settings rendered for a project: with no
  declarations, no extra writable path, the home directory unreadable
  except the repository and git's user configuration, and no reachable
  host with strict refusal; with declarations, exactly the declared write
  paths, read paths and hosts are added. (R-2, R-3, R-4)
- **SC-3** — The worker CLI rejects `--session-arg`, and the Python entry
  point accepts no parameter that reaches the session's argument list.
  (R-5)
- **SC-4** — With secret-looking variables set in the dispatching
  environment, the environment the session seam receives contains none of
  them; a name declared in `session_env` is passed through; the fixed base
  is present. (R-6)
- **SC-5** — Against a real git repository, the handoff check refuses each
  of: a reworded success criterion; a changed requirement; a `tasks.md`
  edit beyond a checkbox; a change under a protected path; a deleted test
  file — naming the path each time. It passes a diff that only fills in a
  Traceability row, ticks a task's checkbox, and changes source and tests.
  (R-7)
- **SC-6** — On a refused handoff: no push and no pull request are
  attempted, the worktree still exists, the outcome carries every finding,
  an alert labelled `refused` is raised once per task, and the resume card
  lists it. (R-8)
- **SC-7** — Against a real git repository with a `pre-push` hook planted
  in it, a successful handoff's push does not run the hook. (R-9)
- **SC-8** — Each new field parses when well-formed, takes its documented
  default when absent, and raises `ProjectConfigError` naming the field
  when malformed (a non-list, an empty entry, a host given as a URL).
  (R-10)
- **SC-9** — The brief contains the statement of limits and the
  instruction to escalate rather than work around them. (R-11)

## Glossary additions (proposed with this spec)

Added to `docs/glossary.md` in this spec's implementing PR.

- **Confinement profile** — the fixed limits the orchestrator launches
  every worker session under: its tools, and what its commands may read,
  write and reach on the network. Owned by the framework; a project widens
  it only by declaring paths, hosts and variable names in
  `agent-framework.toml`. No caller can widen it at dispatch.
- **Handoff check** — the orchestrator's deterministic check of a
  completed session's diff, run before anything is pushed: the contract
  text unchanged, protected paths untouched, no test file deleted. A
  finding refuses the handoff.

## Live check

The probe ADR 0007's measurements came from, kept here so it can be re-run
after a Claude Code update. In a throwaway repository with a linked
worktree and a local bare remote **outside any temporary directory** (the
sandbox lets commands write to the temp directory, which hides the
result), launch a session under the profile and have it run, one command
at a time: an edit in the tree; running the edited code; a commit; a write
to a path outside the tree; a write to the main repository's
`.git/hooks/pre-push`; a `git push`; an HTTPS request to an undeclared
host; `gh auth token > /dev/null`. Then inspect the disk, not the
session's report. Expected: the first three succeed; nothing exists
outside the tree; no hook; the remote has no new branch; the request and
the token read fail.

## Open questions

All resolved 2026-11-09 (human sign-off: vpc accepted ADR 0007 and every
answer below as drafted).

- [x] **Deny the whole home directory, or only credential locations?**
  The whole home directory except the repository, git's user
  configuration and declared paths (R-3). It follows "what it can read it
  can publish" and measured as workable, at the cost of each project
  declaring where its toolchain lives. Rejected: denying only `~/.ssh`,
  `~/.config/gh`, `~/.aws` and similar, which leaves every other
  repository on the machine readable.
- [x] **Remove `--session-arg`, or keep an explicit unconfined escape
  hatch?** Removed (R-5). An escape hatch is one flag away from the old
  behavior; a project that cannot run confined is better surfaced than
  bypassed.
- [x] **A refused handoff: its own outcome and `refused` alert, or a plain
  worker error?** Its own outcome and alert (R-8): a refusal needs a human
  decision, and a worker error raises no alert today.
- [x] **The default `protected_paths`.** `.github/**` and
  `agent-framework.toml`. Left to each project: `CLAUDE.md`,
  `docs/adr/**`, `docs/glossary.md` — a signed-off task can legitimately
  add a glossary term or an ADR file.
- [x] **The fixed environment base (R-6).** Listed exactly in `plan.md`;
  it keeps the session tool's own `ANTHROPIC_*` / `CLAUDE_*` variables, so
  ADR 0004's API-key fallback works and the residual ADR 0007 names
  remains.
- [x] **ADR 0007** — accepted 2026-11-09.

## Out of scope (for now)

- This repository's own advisory `validator` CI job runs the validator
  from the pull request's head with the `GEMINI_API_KEY` secret in its
  environment, so a PR that changes the validator's code runs that code
  with the key. Protected paths do not cover it (the code under test *is*
  the task here). A separate fix: run the gate from `main`. Adopting
  repositories install the framework from `main` and are not affected.
- A narrower GitHub identity for the orchestrator's push.
- A session run record (transcript, cost, turns, sandbox denials) and an
  alert on a crashed session.
- Passing the brief on standard input rather than as an argument.

## Traceability

| Criterion | Requirement(s) | Verified by (test) |
|---|---|---|
| SC-1 | R-1 | `tests/worker/test_confinement.py::test_sc1_every_launch_carries_the_whole_profile` |
| SC-2 | R-2, R-3, R-4 | `tests/worker/test_confinement.py::test_sc2_nothing_is_widened_unless_the_project_declares_it`, `tests/worker/test_confinement.py::test_sc2_exactly_the_declared_paths_and_hosts_are_added` |
| SC-3 | R-5 | `tests/worker/test_confinement.py::test_sc3_no_caller_can_pass_arguments_to_the_session` |
| SC-4 | R-6 | `tests/worker/test_confinement.py::test_sc4_the_session_environment_is_an_allowlist` |
| SC-5 | R-7 | *(pending)* |
| SC-6 | R-8 | *(pending)* |
| SC-7 | R-9 | *(pending)* |
| SC-8 | R-10 | `tests/test_project_config.py::test_sc8_confinement_fields_parse_when_well_formed`, `tests/test_project_config.py::test_sc8_absent_confinement_fields_take_their_documented_defaults`, `tests/test_project_config.py::test_sc8_malformed_confinement_field_fails_loudly_naming_it`, `tests/test_project_config.py::test_sc8_an_invalid_config_is_unconstructible_directly` |
| SC-9 | R-11 | `tests/worker/test_brief.py::test_sc9_brief_states_the_limits_and_says_to_escalate` |
