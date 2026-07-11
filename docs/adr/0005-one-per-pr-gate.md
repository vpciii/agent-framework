# ADR 0005: One per-PR gate — conformance and refutation in a single validator

- **Status:** Accepted
- **Date:** 2026-07-11
- **Deciders:** vpc

## Context

The orchestration design (2026-06-25 two-stage review note) identified two
review jobs that must not be collapsed *and* must not be duplicated:

- **Challenging the contract** — are the spec's criteria and requirements
  *right*? A flawed criterion poisons every task built against it: a worker
  will perfectly satisfy a wrong spec and sail through any conformance
  check.
- **Checking conformance to the contract** — does this PR meet its claimed
  criteria, with cited evidence, and are its tests honest?

The cross-model adversarial-review trial
(`$METHODOLOGY_HOME/experiments/adversarial-review/`) showed a different
model catches what the author's model misses — and that adversarial review
earns its keep on *design decisions*, becoming an effort-sink when run on
every routine change. The validator-gate spec (now Approved) builds the
per-PR gate; this ADR fixes the review topology it assumes, so the decision
outlives the design note it came from.

## Decision

1. **Per PR, there is exactly one model gate: the validator.** It performs
   conformance checking *with a refutation mindset* — the ADR-0015-style
   checklist (test honesty, no scope creep, criteria not silently reworded)
   plus an active hunt for an unstated edge case — in a single judgment.
   We will not add a separate per-PR adversarial reviewer.
2. **The validator cites; it never asserts.** A `PASS` names, per claimed
   criterion, the passing test and green CI — and the implementation makes
   an uncited `PASS` unconstructible, not merely discouraged. A `REJECT`
   names a specific finding with evidence.
3. **Deterministic before model.** Whatever is machine-checkable
   (criterion→test citation, CI status, red→green presence) is code and
   runs first; its failure rejects without a model call. The model judges
   only what code cannot.
4. **Challenging the contract happens upstream, not per PR.** A selective,
   different-lineage, design-mode adversarial review at the *spec* gate —
   for substantial or risky specs — is a separate future slice. The
   validator trusts the criteria as the contract; that trust is this ADR's
   explicit, recorded limitation.
5. **Cross-model is a roster obligation.** The validator role should be
   bound to a different lineage than the worker it gates (ADR 0001 makes
   this a config choice; ADR 0004 currently binds it to Gemini while
   workers run Claude).

## Alternatives considered

- **A second, adversarial reviewer on every PR** — attractive as
  belt-and-braces; rejected: redundant with a validator that already
  carries the refutation checklist cross-model, doubles per-PR model cost,
  and is precisely the run-on-everything mode the adversarial-review trial
  found to be an effort-sink.
- **One combined reviewer that also challenges the spec per PR** —
  rejected: fifty downstream PRs is the most expensive place to discover a
  bad criterion, and a per-PR gate lacks the standing to change the
  contract anyway (a contract change is its own signed-off diff,
  methodology guardrail). Upstream is where that challenge pays.
- **Deterministic checks inside the model prompt** ("also verify each SC
  has a test") — rejected: methodology §5 says machine-checkable rules are
  enforced, not asked; code is free and deterministic, model calls are
  neither.

## Consequences

- Per-PR review cost stays one model call (often zero, when the
  deterministic stage rejects) — compatible with ADR 0004's free-tier
  budget.
- "Done" becomes a cited fact for every gated PR; the #1 multi-agent
  failure (asserted success) is structurally blocked at the gate.
- **Accepted risk:** a wrong criterion passes the gate by design. The
  mitigation is the upstream spec-stage adversarial review (future slice)
  plus the human's spec sign-off — not more per-PR machinery.
- The refutation mindset lives in a prompt, so its quality is a prompt-
  engineering concern; the checklist is versioned in code where tests pin
  its presence (validator-gate SC-5).
- If evidence someday shows the single gate missing real defects at rate,
  the recorded escalation path is a *selective* second reviewer on
  high-risk tasks — superseding this ADR, not quietly adding a reviewer.

## Adoption impact

Project ADR. Rollout: the validator-gate spec implements it (its `plan.md`
references this ADR); the future chief spec must route every worker PR
through the validator and must not add per-PR review stages; the future
spec-adversary slice owns decision 4.

## References

- `docs/design/orchestration-design.md` — Part 2 and the two-stage review
  note this ADR graduates.
- ADR 0001 (roles/roster), ADR 0003 (deterministic CI), ADR 0004 (validator
  surface & budget).
- `specs/validator-gate/spec.md` (Approved) and `plan.md`.
- `$METHODOLOGY_HOME/experiments/adversarial-review/` — the cross-model
  trial evidence.
