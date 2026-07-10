# Working notes for AI agents in this repo

This file orients an AI coding agent for **agent-framework** — a
hierarchical agent-orchestration layer (a **chief** agent plans and
dispatches, **worker** agents code, a **validator** agent gates their
output) that coordinates agents **through the methodology's artifacts**,
not through chat. It is intentionally short. The global practices live in
`$METHODOLOGY_HOME/methodology.md` (default `~/Developer/methodology`); the
durable project-specific rules live in `docs/adr/` and `docs/glossary.md`.

> **The load-bearing idea:** the methodology is the *contract* the agents
> coordinate on; this repo is the disposable *orchestration* over it. The
> artifacts (`spec.md` → `tasks.md` → PRs → the Traceability table) are the
> API between agents. See `docs/design/orchestration-design.md`.

## Read first, every session

1. `$METHODOLOGY_HOME/methodology.md` — the practices and why (global;
   read once if unfamiliar; see its "Using this methodology" section for
   the decision guide and agent operating rules).
2. `docs/architecture.md` — the current shape of the system (added once
   the first component lands); the ADRs say *why*.
3. `docs/glossary.md` — this project's ubiquitous language. Use these
   terms exactly (chief, worker, validator, task, success criterion…).
4. `docs/adr/` — every numbered ADR is binding unless `superseded`.
5. `docs/design/` — design sketches ahead of the specs they feed.
6. The `specs/<feature>/` folder for the work at hand, if one was named.

## Hard rules

- **No code without a spec for non-trivial work.** Larger than a single
  function or bugfix → draft `specs/<slug>/spec.md` first and confirm
  before implementing. Templates: `$METHODOLOGY_HOME/templates/spec/`. For
  an uncertain or expensive bet, plan it first in `planning/<slug>/`.
- **Never invent a domain term.** If a concept needs a name and it isn't
  in `docs/glossary.md`, stop and propose it.
- **Decisions get ADRs** — expensive to reverse, multi-component, or
  future-constraining. Template: `$METHODOLOGY_HOME/templates/adr/_template.md`.
- **One PR-sized change per task.** Split past ~300 lines of diff.
- **Reversible by default.** Flags / expand-contract / backward-compatible
  APIs; call out and ADR anything truly irreversible.
- **Tests before merge.** New behavior ships with tests; fixes ship a
  regression test with the failing-before run cited. Test behavior, not
  implementation. A test verifying a spec success criterion cites its id.
- **Specs freeze; keep the shape doc honest.** A spec freezes at
  `Implemented`; update `docs/architecture.md` in the same PR as any
  structural change.
- **Secrets never in the repo.** Env / secret manager only.
- **Dependencies are decisions.** Weigh before adding; commit lockfiles;
  ADR non-trivial deps.
- **Docs change in the same PR as the behavior.** Conventional Commits.
- **Don't silently rewrite an agreed contract.** Show "done" by citing the
  passing test; surface drift; re-read before editing.

### Project-specific (the ones this repo exists to enforce)

- **Agents coordinate through artifacts, never freeform.** A handoff is a
  durable artifact the receiver acts on without the sender's context
  (`tasks.md` items traced to `SC-` ids; PRs whose tests cite those ids;
  validator verdicts that cite evidence).
- **The validator cites, it does not assert.** "Show done, don't assert
  it" is the gate — a PASS names the passing test per criterion (see the
  cite-the-test gate in the design doc). This will get its own ADR when
  built.
- **The human is author of record — above the chief.** No agent, chief
  included, is the final acceptance authority.
- **Model-agnostic — no hardcoded vendor.** Roles (chief / worker /
  validator) are slots bound to models by the **roster**; models are
  reached through provider adapters. Swapping a model is a roster edit,
  never a code change. The validator should be a different lineage than the
  worker it gates (ADR 0001).

## What this file is not

A pointer, not the methodology. If something here contradicts
`$METHODOLOGY_HOME/methodology.md` or a project ADR, the ADR wins and this
file should be updated.
