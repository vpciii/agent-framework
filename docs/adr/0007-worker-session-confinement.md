# ADR 0007: The worker session is confined; the orchestrator holds the credentials and checks what comes back

- **Status:** Proposed
- **Date:** 2026-11-09
- **Deciders:** vpc

## Context

ADR 0004 made the worker a headless Claude Code session and left its
permissions to "Claude Code's own permission config". The worker spec
repeated that as a non-goal. In practice the framework passes the session
no limits at all: it inherits the dispatching shell's environment and
credentials, and `docs/adoption.md` tells adopters to pass
`--dangerously-skip-permissions`. The brief says "never push, never merge,
do not edit spec files" — an instruction, not a boundary.

Methodology ADR 0027 (0.15.0) now states the rule this breaks: an AI agent
is an actor at a trust boundary — least privilege; what it reads is data;
**what it can read, it can publish**. For the worker that last clause is
concrete: its commits become a pull request, on a public repository, pushed
by the orchestrator. The session reads a target repository's files,
dependencies and task text, any of which can carry instructions it was
never meant to follow, and it makes ordinary mistakes.

What an unconfined session can do today, with the dispatching user's own
access: push to any branch and merge its own PR (this repo's ruleset
requires a green `ci` check and **zero** approvals, so the user's token is
enough); read SSH keys, the `gh` token and every other repository under
the home directory; reach any host; plant a git hook the orchestrator then
runs; rewrite the spec's criteria or the CI workflow inside its own PR.

### What was measured (spike, 2026-11-09)

Claude Code 2.1.319 on macOS, a throwaway repository with a linked
worktree and a local bare remote, the same nine probe commands under each
profile. Results are what was found **on disk afterwards**, not what the
session reported.

| Profile | Work in the tree (edit, run, commit) | Write outside the tree | Plant a git hook | Push | Network | `gh` token |
|---|---|---|---|---|---|---|
| Restricted mode, Bash allowed, deny rules for `git push` / `gh` / `curl` — commands issued directly | works | **written** | denied | denied | denied | denied |
| Same profile — the same actions from inside a Python script | works | — | **written** | **pushed, and the planted hook ran** | **reached** | **readable** |
| Restricted mode + OS sandbox, no network, unsandboxed commands forbidden | works | blocked | blocked | blocked | blocked | blocked |

Further runs under the sandbox profile, in a worktree of this repository:

- This repo's whole gate (`uv sync`, ruff, `mypy --strict`, 147 tests,
  spec coverage) **fails** until two things are declared — `~/.cache/uv`
  writable, and `pypi.org` + `files.pythonhosted.org` reachable — and
  **passes** once they are.
- With reads of the home directory denied except the repository and the
  toolchain's own directories, the gate still runs; `git commit` needs
  `~/.gitconfig` readable; other repositories under `~/Developer` are
  unreadable; the `gh` keychain item is not visible to a command.
- The session's commands inherit the dispatching shell's environment,
  which held five variables with secret-like names.
- A linked worktree needs nothing special: the sandbox lets `git commit`
  write the shared object store while keeping `hooks/` and `config`
  write-protected.

The push probe used a local bare remote, so it tested the filesystem
limit; that a push to a network remote is blocked follows from the network
result and was not separately run. Linux (bubblewrap) was not tested.

Claude Code's own documentation says the same about pattern rules: a deny
rule "covers the invocation Claude usually produces and isn't a security
boundary around the program", and directs enforcement to the sandbox.

## Decision

We will confine every worker session by construction, keep credentials
with the orchestrator, and check by code what a session hands back.

1. **The framework owns the session's permissions — the confinement
   profile.** The orchestrator launches every session in restricted mode
   with a fixed tool list, no prompting (anything that would prompt is
   denied), none of the user's or project's Claude settings, hooks,
   plugins or MCP servers, and an OS sandbox on every command. The sandbox
   fails closed: if it is unavailable the session does not start, and a
   command may not opt out of it.
2. **What the sandbox permits is least privilege, widened only by the
   project's declaration.** By default a command may write only inside its
   worktree, reach no network host, and read nothing under the home
   directory except the repository and git's user configuration. A project
   widens this in `agent-framework.toml` — the paths its toolchain needs
   and the hosts its package index lives on — where the widening is
   reviewed like any other change.
3. **No caller can widen the profile at dispatch.** The `--session-arg`
   pass-through is removed. The session's environment is an allowlist, not
   the dispatching shell's.
4. **Only the orchestrator pushes, and only after a handoff check.**
   Before anything leaves the machine, code checks the session's diff: the
   contract text of every spec is unchanged, protected paths (CI
   workflows, the framework's config) are untouched, and no test file was
   deleted. A finding means nothing is pushed and the human is alerted.
   The orchestrator's own git commands never run repository hooks.
5. **The profile lives behind the session seam; the handoff check does
   not.** The profile is Claude Code's mechanism and belongs to the one
   module that launches it (ADR 0001, ADR 0004): another session tool
   brings its own. The handoff check is tool-independent and applies to
   any session.

## Alternatives considered

- **Keep instructing the session** (today) — nothing to build, and the
  session has complied in every live run so far. Rejected: compliance is
  not a boundary, and ADR 0027 asks for one.
- **Permission rules only** (allow and deny patterns for Bash) — no
  sandbox dependency, works on any platform. Rejected on the evidence
  above: a script walks through every rule, and the vendor documents the
  rules as not a security boundary. Kept only as a second layer the
  sandbox makes unnecessary.
- **A container or VM per session** — the strongest isolation and the
  same on macOS and Linux. Rejected for now: an image per target project,
  slower sessions on macOS, and Max-plan authentication to carry into the
  container (ADR 0004). It is the natural next step if workers move to an
  unattended server, and decision 5 keeps the door open.
- **A separate, narrower GitHub identity for the orchestrator** (a bot
  account or fine-grained token that can push a branch and open a PR but
  not merge) — limits what the *orchestrator's* credential can do if the
  machine is compromised. Complementary rather than alternative: it does
  nothing about what the session can read or reach, and on a solo
  repository a ruleset cannot require an approval the owner could give.
  Not taken now; no decision here closes it off.
- **Give the session a disposable clone instead of a linked worktree, or
  have the orchestrator make the commits** — would keep the session out of
  the shared `.git` entirely. Rejected as unnecessary: the sandbox already
  protects `hooks/` and `config` there while letting commits through.

## Consequences

- "Never push, never merge" becomes true by construction for a confined
  session, and "the human is author of record" stops depending on the
  session's good behavior.
- **Adoption gets a new step.** A target project must declare its
  toolchain's cache paths and package hosts or its gate cannot run inside
  the session. The failure is loud and names the path or host, but it is
  friction the first dispatch will hit. `docs/adoption.md` carries a
  worked example.
- **A breaking change to the worker CLI:** `--session-arg` goes away. The
  framework is pre-1.0 and has one adopter; undo is re-adding the flag.
- **macOS only until Linux is verified.** The sandbox fails closed, so on
  an unverified platform the worker refuses to start rather than run
  unconfined.
- **A dependency on Claude Code's restricted mode and sandbox.** A CLI
  update could change either (the durable-autonomy pre-mortem already
  lists `-p` behavior changing under us). The spike's probe is recorded in
  the spec as the check to re-run after an update.
- **Residual exposure, named rather than hidden:**
  - Declared hosts are reachable. A package index is a small channel, but
    it is one.
  - Everything the session *can* read — the repository, and whatever the
    project declares — can end up in its diff, and the orchestrator
    pushes that diff. The handoff check does not scan for secrets.
  - If the session authenticates with `ANTHROPIC_API_KEY` (ADR 0004's
    fallback) rather than the Max plan, that key is in the session's
    environment and visible to its commands.
  - The orchestrator still pushes with the user's full token.
- Tasks that legitimately change a protected path (a CI workflow) are no
  longer worker tasks; the human does them. That is the intended reading
  of least privilege, and the list is the project's to edit.

## Adoption impact

Project ADR. Rollout it forces:

- `specs/worker-confinement/` implements it (profile, environment,
  handoff check, config fields, brief text, docs).
- Every adopting repo adds its toolchain's paths and hosts to
  `agent-framework.toml` before its next dispatch, and drops
  `--session-arg=--dangerously-skip-permissions` from its dispatch
  command.
- `docs/architecture.md` — the worker's Trust boundaries entry is
  rewritten in the implementing PR.
- Revisit trigger: workers running unattended on another machine, or on
  Linux — reopen the container alternative.

## References

- Methodology ADR 0027 — out-of-repo settings, AI agents as actors, the
  freeze point.
- ADR 0001 — model-agnostic roles (why the profile sits behind the session
  seam); ADR 0004 — role execution surfaces (the worker is headless Claude
  Code); ADR 0005 — one per-PR gate (unchanged).
- `specs/worker-agent/spec.md` — the non-goal this supersedes
  ("Sandboxing beyond the worktree … is Claude Code's own permission
  config"). That spec is frozen; this ADR and the new spec carry the
  change.
- Claude Code documentation: sandboxing, permissions ("Bash rule limits"),
  headless mode, CLI reference (`--restricted`, `--permission-prompts`).
- `planning/durable-autonomy/premortem.md` — CLI-update risk.

---

> Following the format proposed by Michael Nygard in
> [Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).
