# Plan: Worker confinement

- **Status:** Approved
- **Date:** 2026-11-09
- **Author:** Claude (draft) — vpc is author of record
- **Spec:** ./spec.md
- **Related ADRs:** ADR 0007 (the decision), ADR 0004, ADR 0001

> This plan freezes with its spec: editable while `Draft` / `Under
> review` / `Approved`, and a historical record once the PR that marks
> the spec `Implemented` merges (methodology §2, ADR 0027). A
> contradiction found later goes to a test, a new spec, or an ADR — not
> back into this file.

## Approach

Three pure pieces and one wiring change, in the shape the worker already
has (pure core, injectable seams).

1. **The profile is a value computed from project config**, in a new
   `worker/confinement.py`: the session's argument list, its sandbox
   settings, and its environment. Nothing in it touches the disk or the
   network, so every limit is asserted in a unit test by reading the value.
   The session seam gains one parameter — the environment — and loses
   `session_args`.
2. **The handoff check is a function over git**, in a new
   `worker/handoff_check.py`: given a worktree and the commit it was cut
   from, it returns findings. It reads the diff through the existing
   runner seam and is tested against real repositories built in
   `tmp_path`, the way the worktree regression tests are.
3. **A refused handoff is a fourth worker outcome**, `HandoffRefused`,
   beside `PrOpened`, `Escalated` and `TimedOut`. The orchestrator runs
   the check between "session completed" and "push"; a finding raises a
   `refused` alert through the existing `notify` and returns the outcome.
4. **Config** gains five `[project]` fields, validated in `ProjectConfig`
   like `test_pattern` and `test_paths`.

### The profile, exactly

Verified live on 2026-11-09 (Claude Code 2.1.319, macOS, Max-plan
authentication, launched with a scrubbed environment): edits and commits
work; a write outside the tree, a read of a home-directory file, a listing
of `~/Developer` and an HTTPS request to an undeclared host are all
refused; the commit takes its author from `~/.gitconfig`.

Arguments, after `claude -p <brief> --model <roster's worker model>`:

```
--restricted
--tools Bash,Read,Edit,Write,Glob,Grep
--permission-mode acceptEdits
--permission-prompts none
--strict-mcp-config
--settings <the JSON below, inline>
```

`acceptEdits` rather than `dontAsk`: under `dontAsk` the file tools are
refused unless separately allowed; `acceptEdits` allows edits inside the
working directory only, and `--permission-prompts none` denies everything
else that would prompt. The settings are passed inline, not as a file, so
there is no settings file in the worktree for a session to edit.

```json
{
  "sandbox": {
    "enabled": true,
    "failIfUnavailable": true,
    "autoAllowBashIfSandboxed": true,
    "allowUnsandboxedCommands": false,
    "network": { "allowedDomains": ["<session_network…>"], "strictAllowlist": true },
    "filesystem": {
      "denyRead": ["~/"],
      "allowRead": ["<repository root>", "<git common dir>", "~/.gitconfig",
                    "~/.config/git", "<session_read_paths…>", "<session_write_paths…>"],
      "allowWrite": ["<session_write_paths…>"]
    }
  }
}
```

### The environment, exactly (spec R-6)

Passed through from the dispatching environment when set, and nothing
else: `PATH`, `HOME`, `USER`, `LOGNAME`, `SHELL`, `LANG`, `TERM`,
`TMPDIR`; any name beginning `LC_`; any name beginning `ANTHROPIC_` or
`CLAUDE_` (the session tool's own authentication and configuration); and
the names in the project's `session_env`. Standard input is closed.

Measured: with that base, a sandboxed command sees only the base plus the
sandbox's own proxy and `GIT_CONFIG_*` variables — no credential the
dispatching shell held.

### The handoff check, exactly (spec R-7)

Base = `git merge-base origin/main HEAD` in the worktree. Changed paths
from `git diff --name-status --no-renames <base> HEAD` (a rename is a
delete plus an add, so neither side escapes a rule). Only committed
changes are checked, because only commits are pushed.

| Rule | Finding when |
|---|---|
| Contract — `spec.md` | a `<specs_dir>/<slug>/spec.md` is added, deleted, or differs from the base once its `## Traceability` section is removed from both sides |
| Contract — `tasks.md` | a `<specs_dir>/<slug>/tasks.md` is added, deleted, or differs from the base once every checkbox mark (`[ ]`, `[~]`, `[x]`) is normalized on both sides |
| Protected path | any changed path matches a `protected_paths` pattern |
| Deleted test | a deleted path matches a `test_paths` pattern |

Every post-session git command the orchestrator runs for the worktree
(the check's reads, the push, the removal) carries
`-c core.hooksPath=/dev/null` (spec R-9).

## Components touched

- `src/agent_framework/project.py` — five fields (`session_write_paths`,
  `session_read_paths`, `session_network`, `session_env`,
  `protected_paths`); validation; the path matcher added for `test_paths`
  is reused under a general name.
- `src/agent_framework/worker/confinement.py` — **new.** `session_env`,
  `sandbox_settings`, `profile_args`: pure functions of `ProjectConfig`,
  the repository root and a mapping of the dispatching environment.
- `src/agent_framework/worker/session.py` — the seam takes an environment
  and closes standard input; `session_args` removed; the profile's
  arguments appended.
- `src/agent_framework/worker/handoff_check.py` — **new.**
  `check_handoff(...) -> tuple[HandoffFinding, ...]`.
- `src/agent_framework/artifacts.py` — two text helpers the check needs
  (a spec without one section; a tasks file with checkbox marks
  normalized), beside the existing parser.
- `src/agent_framework/worker/types.py` — `HandoffRefused` outcome.
- `src/agent_framework/worker/orchestrator.py` — builds the profile; runs
  the check; raises the alert; returns the outcome. `session_args`
  parameter removed.
- `src/agent_framework/worker/handoff.py` — push without hooks.
- `src/agent_framework/worker/worktree.py` — removal without hooks.
- `src/agent_framework/worker/__main__.py` — `--session-arg` removed;
  exit code 4 for a refused handoff.
- `src/agent_framework/worker/brief.py` — the statement of limits.
- `src/agent_framework/status/card.py` — `refused` joins the alert labels.
- `agent-framework.toml` — this repo's own declarations.
- `docs/glossary.md`, `docs/adoption.md`, `docs/architecture.md`.

## Data model changes

None stored. In memory:

```
ProjectConfig += session_write_paths: tuple[str, ...] = ()
                 session_read_paths:  tuple[str, ...] = ()
                 session_network:     tuple[str, ...] = ()
                 session_env:         tuple[str, ...] = ()
                 protected_paths:     tuple[str, ...] = (".github/**", "agent-framework.toml")

HandoffFinding(rule: "contract" | "protected-path" | "deleted-test", path: str, detail: str)
HandoffRefused(worktree_path: str, findings: tuple[HandoffFinding, ...], alerts: tuple[str, ...])
WorkerOutcome = PrOpened | Escalated | TimedOut | HandoffRefused
```

Validation: paths are absolute or begin `~/`; a network entry is a bare
host name (no scheme, no path, no port); an environment entry is a
variable name; `protected_paths` entries are non-empty patterns.

## API changes

- **Worker CLI (breaking):** `--session-arg` is removed; passing it is an
  argument error. New exit code **4** = handoff refused (0 PR opened,
  2 escalated, 3 timeout or error — unchanged). The outcome JSON gains
  `"outcome": "handoff_refused"` with `worktree_path`, `findings`,
  `alerts`.
- **`work()` (breaking):** the `session_args` parameter is removed.
- **`agent-framework.toml`:** five optional `[project]` fields. This
  repo's own:

  ```toml
  session_write_paths = ["~/.cache/uv"]
  session_read_paths  = ["~/.local/share/uv"]
  session_network     = ["pypi.org", "files.pythonhosted.org"]
  ```

## Alternatives considered

The decision-level alternatives are in ADR 0007. At plan level:

- **Settings as a file in the worktree** — easier to read in a debugger.
  Rejected: a file the session can see is a file it can try to edit;
  inline leaves nothing to protect.
- **`dontAsk` plus allow rules for the file tools** — the stricter mode by
  name. Rejected: it needs a rule list to keep in step with the tool list,
  and measured no tighter than `acceptEdits` with prompts denied.
- **The handoff check inside `open_pr`** — one fewer module. Rejected:
  the check is the tool-independent half of ADR 0007 (decision 5) and
  should be testable, and reusable by a future chief, without a push.
- **Checking the working tree as well as the commits** — would catch a
  spec edit left uncommitted. Rejected: uncommitted changes are never
  pushed, and the worktree of a refused or completed session is not
  reused.

## Risks

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| A project's gate needs a path or host nobody declared, so the first confined dispatch fails | High | Low — loud, names the path or host | The brief tells the session to escalate rather than thrash; `docs/adoption.md` carries worked examples; this repo's own declarations ship in T-2 |
| A Claude Code update changes restricted mode, the sandbox schema or a flag | Medium | High — sessions fail to start, or a limit silently weakens | Unknown flags and an unavailable sandbox fail closed; the spec's *Live check* is re-run after an update; the pre-mortem already tracks CLI drift |
| The session burns its time budget retrying refused commands | Medium | Medium | R-11 brief text; the existing timeout and handoff note bound it |
| The handoff check refuses legitimate work (a task whose Touches include a workflow file) | Low | Medium | `protected_paths` is the project's to edit; the refusal names the path and keeps the worktree |
| The check's section and checkbox normalization is too loose and lets a contract edit through | Low | High | SC-5 tests each contract edit against a real repository; the validator's judgment now also sees the criteria read at the base commit (validator-evidence) |
| Removing `--session-arg` breaks the one adopter's dispatch command | Certain | Low | Called out in the PR and `docs/adoption.md`; undo is re-adding the flag |

## Rollout

Five PRs (tasks.md), no flag — ADR 0007 rejected an unconfined escape
hatch. T-1 is additive. **T-2 is the switch**: from its merge every
dispatch is confined, `--session-arg` is gone, and this repo's
declarations are in its config. T-3 and T-4 add the handoff check; until
T-4 merges, a confined session's diff is pushed unchecked, as today. T-5
is the delivery edge and cites the live run. Undo for any step is
reverting its PR; nothing is migrated or stored.

The adopting repository (opn-mcp) adds its declarations and drops
`--session-arg` from its dispatch command before its next dispatch.

## Observability

One log line when a session starts, naming the profile's declared hosts
and paths by count; one per handoff finding; the outcome JSON carries the
findings. A refused handoff is an alert issue and a phone push.

## Test strategy

- **Unit, pure:** the profile's arguments, settings and environment are
  values — SC-1, SC-2 and SC-4 assert on them directly; SC-8 on config
  loading; SC-9 on the brief's text; SC-3 on the argument parser and the
  entry point's signature.
- **Integration, real git, no network:** SC-5 and SC-7 build a repository
  and remote in `tmp_path`, commit each kind of change, and run the check
  and the push for real. SC-6 drives the orchestrator with a faked session
  and a faked alert tracker over that same real repository.
- **Live, cited not asserted (R-12):** one real task dispatched in this
  repository under the profile, and the spec's *Live check* probe, both
  quoted in the delivery PR. No test in CI invokes a model.
