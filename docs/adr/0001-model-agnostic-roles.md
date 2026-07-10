# ADR 0001: Model-agnostic roles, bound by a roster

- **Status:** Accepted
- **Date:** 2026-06-25
- **Deciders:** vpc

## Context

The framework orchestrates a **chief / worker / validator** team. Different
models suit different roles: a high-end model (e.g. Claude Fable) as the
**chief** for planning and decomposition; cheaper models (e.g. Claude Sonnet)
as **workers** doing the bulk coding; and — per the cross-model
adversarial-review finding — a **different-lineage** model (e.g. a Google
model) as the **validator**, because a same-model reviewer shares the worker's
blind spots.

Two things make this clean rather than messy:

- The shared methodology is itself **model-agnostic** (it expresses AI *roles*,
  never vendors), and its artifacts (`spec.md` → `tasks.md` → PRs → the
  Traceability table) are a **model-neutral coordination substrate**. Any model
  can read and write them.
- So the framework should hardcode **no vendor**. Which model fills which role
  is a configuration choice, not a code change.

## Decision

1. **Roles are model-agnostic slots.** `chief`, `worker`, `validator` are
   roles, not vendors. Each role is bound to a concrete model in **one
   swappable place — the roster** (config), e.g.:

   ```
   chief:     claude-fable-5
   worker:    claude-sonnet-5      # or a pool
   validator: gemini-3-pro         # different lineage than worker
   ```

2. **Models are reached through a thin provider abstraction.** One adapter per
   provider (Anthropic, Google, …) behind a common interface (send a
   prompt + tools, get a response). Adding or swapping a provider is a new
   adapter + a roster edit; the orchestration logic is untouched.

3. **Coordination is through the methodology's artifacts, which are
   model-neutral.** A chief (any model) writes `spec.md` / `tasks.md`; a worker
   (any model) produces PRs whose tests cite `SC-` ids; a validator (any model)
   runs the cite-the-test gate. **The practices are followed regardless of
   which model fills a role** — the artifact, not the model, carries the
   contract.

4. **The validator should be a different model/lineage than the worker it
   gates** (blind-spot coverage). The roster makes that a config choice, not a
   code change.

## Alternatives considered

- **Hardcode one vendor** (all-Claude, all-Google) — rejected: vendor lock-in,
  loses the cross-model validation benefit, and contradicts the model-agnostic
  methodology this framework runs on.
- **Per-role models hardcoded in the orchestration code** (no roster) —
  rejected: swapping a model would be a code edit. The roster is the single
  swappable binding (one source of truth for the mapping, ADR-0022-style).
- **One large model doing every role** (no team) — a different product; this
  framework exists precisely to run *heterogeneous* roles cost-effectively
  (expensive chief, cheap workers, distinct validator).

## Consequences

- Any model in any role; retune cost/quality by editing the roster (expensive
  chief, cheap worker pool, distinct-lineage validator).
- Cross-model validation is a configuration choice, not a rebuild.
- **Cost:** a provider-adapter layer to build and maintain — each provider's
  API and tool-calling differ. Kept deliberately thin (prompt + tools in,
  response out); that thinness is load-bearing and worth guarding.
- The framework depends on the methodology's artifacts being the coordination
  medium — which they are by the methodology's durable-semantic-interface
  design. If a role ever coordinates out-of-band (chat, hidden state) instead
  of through artifacts, model-agnosticism breaks.

## Adoption impact

Founding architectural constraint — every component honors it from the start.
No rollout; there is no prior code to migrate.

## References

- The shared methodology (`$METHODOLOGY_HOME/methodology.md`) — model-agnostic
  stance, the "artifacts as a durable semantic interface" section.
- The cross-model adversarial-review finding (a different model catches what
  the author's model misses) — motivates a distinct-lineage validator.
- `docs/design/orchestration-design.md`; `docs/glossary.md` (role, roster,
  provider adapter).

---

> Following the format proposed by Michael Nygard in
> [Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).
