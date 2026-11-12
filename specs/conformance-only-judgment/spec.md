# Spec: The judgment checks conformance only

- **Status:** Draft
- **Date:** 2026-11-12
- **Author:** Claude (draft) — vpc is author of record
- **Related ADRs:** ADR 0008 (proposed with this spec; supersedes
  ADR 0005), ADR 0001 (roles are bound by the roster)

> This spec is editable while `Draft` / `Under review` / `Approved`.
> When the PR that marks it `Implemented` merges it **freezes** into a
> historical record (methodology ADR 0027);
> a contradiction found later goes to a test, a new spec, or an ADR —
> not back into this file (methodology §2, §8).

## Problem

The validator's judgment is asked to do two jobs: check that the work
matches what was asked, and hunt for an edge case nobody stated. The
second makes a PASS depend on which run it was.

The eval set was run in full on 2026-11-10 and 2026-11-12 on identical
input. Every conformance case came out the same both times: nine of
nine seeded defects caught, `pr-89` rejected for changing a file outside
its brief, and no accepted work wrongly rejected. Three cases flipped
from REJECT to PASS. Two of them, `pr-18` and `pr-37`, were findings
under the checklist's fourth item — "construct one plausible unstated
edge case". Which case the model constructs is different each run.

ADR 0008 decides that the hunt is not the validator's job. This spec
makes the judgment match that decision.

## Goals

1. The judgment asks only whether the work conforms to its contract:
   honest tests, the task and only the task, criteria not weakened.
2. A finding can no longer be filed as an edge case.
3. The eval set's answers agree with the narrower scope.
4. A new baseline is on record for the changed judgment.

## Non-goals

- Making the judgment steadier by other means — a fixed thinking level,
  asking more than once, whole changed files. One conformance case,
  `pr-59`, also flipped; this spec does not claim to fix it.
- Keeping edge-case findings as advisory notes (ADR 0008, alternatives).
- Changing the deterministic stage, the quote check, the verdict's JSON
  shape, the roster, or the number of model calls.

## Requirements

- **R-1 (MUST)** The judgment's checklist has three items — test
  honesty, spec conformance, criteria integrity — and no longer asks the
  model to construct an unstated edge case.
- **R-2 (MUST)** The instructions state the scope: a defect is a
  departure from the task or from the criteria the PR claims, as the
  contract in the data gives them; a possible bug the contract does not
  speak to is not a defect for this verdict.
- **R-3 (MUST)** A finding's `check` is one of three names:
  `test-honesty`, `spec-conformance`, `criteria-integrity`. The tool's
  schema allows no other, and a response that names `edge-case` is
  malformed, as any name outside the list is today.
- **R-4 (MUST)** No eval case names `edge-case`, and a case file that
  does fails to load, naming the file. The two cases that name it today
  are relabelled in the same change (see *Open questions* for which
  way).
- **R-5 (MUST NOT)** The change MUST NOT alter what a result file
  records. The two results in the repository, which hold `edge-case`
  findings, still load and render.
- **R-6 (SHOULD)** The delivery PR cites one full eval run made after
  the change, sets it beside the 2026-11-12 baseline, and
  `docs/architecture.md` names it as the baseline for the changed
  judgment.

## Success criteria

- **SC-1** — The request the judgment sends carries the three-item
  checklist and nowhere asks for an edge case. (R-1)
- **SC-2** — The request states that only a departure from the task or
  the claimed criteria is a defect. (R-2)
- **SC-3** — The verdict tool's schema restricts `check` to the three
  names, and a response whose finding names `edge-case` is reported as
  malformed, not as a verdict. (R-3)
- **SC-4** — A case file whose `check` is `edge-case` fails to load,
  naming the file, and every case in the repository's set loads. (R-4)
- **SC-5** — Both result files in the repository on 2026-11-12 load and
  render with their `edge-case` findings shown. (R-5)

## Approach

One PR.

- `validator/judgment.py` — `REFUTATION_CHECKLIST` loses item 4;
  `CHECK_NAMES` loses `edge-case`, and the schema's enumeration and the
  parser follow from it. One sentence of scope is added beside the
  checklist. Drafted wording: *"Judge only against the task and criteria
  given in the data. A possible bug they do not speak to is not a defect
  for this verdict; do not report one."*
- `evals/validator/cases/pr-18.json` and `pr-37.json` — the expected
  answer, checklist item and reason only; the frozen bundles are
  untouched. The case loader already refuses a name outside
  `CHECK_NAMES`, so R-4 needs no new code.
- Tests: the judgment's own tests and `tests/evals/`. Tests that frozen
  specs cite (specs/validator-gate SC-5, specs/finding-evidence SC-1)
  keep their names and are updated to three items; those specs are not
  edited. specs/finding-evidence R-7 says "four fixed names" — ADR 0008
  and this spec are the record of why it is now three.
- Docs in the same PR: `docs/adoption.md` (the list of `check` names,
  twice), `docs/architecture.md` (the judgment row, the eval set's
  counts, the baseline), the ADR index. ADR 0005 is marked superseded
  when ADR 0008 is accepted.
- Both fingerprints move, as they should: the instructions change and
  two answers change.

### Decisions

- *(none yet)*

## Rollout and undo

The instructions change is two constants and a sentence; undo is
reverting the PR, and the previous baseline stays in the repository to
compare against. Reversing the decision itself is a further ADR.

The gate is advisory today, so a judgment that reports less cannot block
or unblock a merge by itself.

The after-run (R-6) is one ordinary full run: 36 judgments, about 33
minutes with vpc's key — the size already run twice.

## Open questions

Each has a drafted answer; all are vpc's to accept or change.

- [ ] **`pr-37` goes back to expected `pass`.** Its only finding was an
  edge case — an empty `test_pattern` — that its task never mentioned.
- [ ] **`pr-18` stays expected `reject`, now under `test-honesty`.** The
  first run reported two findings; the second one is a conformance
  finding and it is true. specs/validator-gate SC-4 says the *verdict*
  is a REJECT carrying the model's finding; the one test cited for it,
  `test_sc4_defect_from_return_verdict_is_carried_verbatim`, calls
  `judge()` and checks the judgment it returns, never the gate's
  verdict. If the gate dropped a defect judgment, that test would still
  pass. This is still so on main today. The alternative is to return
  `pr-18` to `pass`.
- [ ] **One eval run, after the change.** The before is the 2026-11-12
  result. `compare` will refuse the pair, correctly, because two answers
  change; the delivery PR sets the two results side by side by hand for
  the 34 cases whose answers do not change and reports the other two
  apart. The alternative keeps `compare` usable: relabel the two cases
  in a PR of their own, run, then change the instructions and run again
  — two runs, about 66 minutes.
- [ ] **A single run cannot show that `pr-59` or `pr-18` is now
  steady.** It can show that no accepted work is newly rejected and
  that the nine seeded defects are still caught. Steadiness on the real
  defects is a five-run check of three cases, left to the next step.
- [ ] **No planning stage.** The decision is ADR 0008's; this is its
  one-PR consequence.

## Out of scope (for now)

- **A fixed thinking level for the validator**, as a roster setting —
  the next lever if the conformance cases still flip. Checked with
  `agent-framework-eval run --only pr-18 pr-59 pr-89 --runs 5`.
- **A gate-level test for specs/validator-gate SC-4** — the gap the
  `pr-18` finding names. Its own small PR.
- Posting the verdict on the PR, and with it a home for advisory notes.
- The reading of multi-run results drafted in specs/judgment-stability
  (PR #100, not merged).

## Traceability

| Criterion | Requirement(s) | Verified by (test) |
|---|---|---|
| SC-1 | R-1 | *(pending)* |
| SC-2 | R-2 | *(pending)* |
| SC-3 | R-3 | *(pending)* |
| SC-4 | R-4 | *(pending)* |
| SC-5 | R-5 | *(pending)* |
