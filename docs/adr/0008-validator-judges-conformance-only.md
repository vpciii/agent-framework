# ADR 0008: The validator judges conformance to the contract; it does not hunt for unstated defects

- **Status:** Accepted
- **Date:** 2026-11-12
- **Deciders:** vpc

Supersedes ADR 0005 (accepted by vpc, 2026-11-12). Decisions 2–5 below are ADR 0005's,
carried over unchanged; decision 1 is narrowed and decision 6 is new.

## Context

ADR 0005 gave each PR one model gate, the validator, and put two jobs in
its single judgment: checking conformance to the contract — test honesty,
no scope creep, criteria not silently reworded — "plus an active hunt for
an unstated edge case". The checklist's fourth item asks the model to
construct one plausible edge case nobody stated and check the diff
against it.

The eval set (specs/validator-eval-set) has now measured that judgment
twice on identical input, on 2026-11-10 and 2026-11-12:

- **Conformance was steady.** All nine seeded defects — three each for
  test honesty, spec conformance and criteria integrity — were caught in
  both runs. `pr-89`, real work that changed a file its brief put out of
  bounds, was rejected in both. No accepted work was wrongly rejected in
  either.
- **The hunt was not.** Three cases were rejected in the first run and
  passed in the second. Two of them, `pr-18` and `pr-37`, were edge-case
  findings. The bugs were real and were fixed in #98 — and the gate
  reported them one time in two.

That is what the fourth item asks for. "Construct one edge case" has no
right answer: which case the model constructs differs from run to run,
so whether a PR passes depends on the run. The usual way to pin a model
down is not available either: both providers on the roster have
withdrawn the sampling parameters. Google ignores `temperature`, `top_p`
and `top_k` from Gemini 3.6 Flash onward and is making them an error
(<https://aistudio.google.com/docs/whats-new-gemini-3.6>); Anthropic's
current models refuse a request that sets them (both read 2026-11-12).

A gate's PASS has to mean the same thing each time it is given. And the
validator's purpose, as vpc put it on 2026-11-12, is to validate that
the returned work matches what was asked — not to be a second bug
finder.

## Decision

1. **Per PR, there is exactly one model gate: the validator. It judges
   conformance to the contract, and nothing else.** In a single judgment,
   with a refutation mindset, it asks: is each cited test honest — would
   it fail if the behavior it claims to verify were broken? Does the
   diff do the task, and only the task? Were any success criteria
   reworded or weakened rather than met? A defect is a departure from
   the task or from the criteria the PR claims. We will not add a
   separate per-PR adversarial reviewer.
2. **The validator cites; it never asserts.** A `PASS` names, per claimed
   criterion, the passing test and green CI, and an uncited `PASS` is
   unconstructible. A `REJECT` names a specific finding with evidence.
3. **Deterministic before model.** Whatever is machine-checkable is code
   and runs first; its failure rejects without a model call. The model
   judges only what code cannot.
4. **Challenging the contract happens upstream, not per PR.** A
   selective, different-lineage, design-mode adversarial review at the
   spec gate is a separate future slice. The validator trusts the
   criteria as the contract.
5. **Cross-model is a roster obligation.** The validator role should be
   bound to a different lineage than the worker it gates.
6. **A possible bug the contract does not speak to is not grounds for a
   REJECT.** The validator does not search for one, and its instructions
   say so. Such bugs are the business of the spec's criteria, the tests
   and the human's review.

## Alternatives considered

- **Keep the hunt and ask several times, rejecting on any REJECT** — it
  would catch more of what the hunt can find. Rejected: it multiplies
  the cost and time of every judgment, and the hunt stays a draw from an
  open-ended space — more draws, no definition of done.
- **Keep the hunt as advisory notes outside the verdict** — the real
  bugs it found argue for it. Rejected for now: the judgment would still
  be doing two jobs in one prompt, and the notes have no reader — the
  verdict is not yet posted on the PR. Worth revisiting when it is.
- **Make the hunt systematic** — a fixed list of input classes to try
  (empty, missing, deleted, …) instead of "construct one". Rejected: it
  turns the gate into the per-PR reviewer ADR 0005 already declined, and
  nothing measures what it would do to the rate of wrong REJECTs.
- **Leave the scope and fix the model's depth of thinking** — in the run
  that missed, the judgment spent far fewer tokens on two of the three
  cases. Not rejected: it is a separate lever for whatever instability
  remains on conformance, and it does not answer what the gate is for.

## Consequences

- A PASS means one thing: this work conforms to what was asked, with
  each claim cited. The part of the judgment the eval showed to be
  steady is the part that stays.
- **Accepted risk:** a bug the criteria do not cover passes the gate by
  design. This widens the risk ADR 0005 already accepted (a wrong
  criterion passes). Two real bugs the hunt once found would not be
  reported by this gate. The weight moves to the spec's criteria and to
  the human's review.
- The eval set changes with the scope: a case whose expected REJECT
  rests on an edge-case finding no longer has one.
- ADR 0005's escalation path stands: if the single gate is shown to miss
  real defects at rate, the answer is a selective second reviewer on
  high-risk tasks, by a further ADR — not a quiet widening of this gate.
- One job in the prompt instead of two. Whether that makes the judgment
  steadier on the conformance items is to be measured, not assumed.

## Adoption impact

Project ADR. specs/conformance-only-judgment implements it: the
checklist loses its fourth item, a finding's `check` loses `edge-case`,
and two eval cases are relabelled. On acceptance ADR 0005 is marked
`Superseded by ADR 0008`. The future chief spec routes every worker PR
through this gate, as before.

## References

- ADR 0005 — superseded by this ADR.
- `specs/validator-eval-set/` and the two results under
  `evals/validator/results/` — the measurement.
- `specs/conformance-only-judgment/spec.md` — the implementing spec.
- `docs/design/orchestration-design.md`, "Two review stages" — the
  design note ADR 0005 graduated; its "construct an unstated edge case"
  is what this ADR withdraws.
