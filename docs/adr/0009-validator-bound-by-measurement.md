# ADR 0009: The validator is bound by what the eval set measures; lineage is a preference and a paid API is allowed

- **Status:** Proposed
- **Date:** 2026-11-13
- **Deciders:** vpc

Replaces three earlier decisions in part, and leaves the rest of each ADR
standing: ADR 0001 decision 4 and ADR 0008 decision 5 (the validator is a
different lineage than the worker), and the validator's row in ADR 0004's
table (direct API on the Gemini free tier).

## Context

The validator's job is conformance (ADR 0008). The eval set shows it
doing most of that job steadily and one part of it badly: a cited test
that verifies less than its criterion says. Five of the 27 accepted pull
requests in the set carry that defect.

Two rules have fixed which model the validator may be. ADR 0001 says it
should be a different lineage than the worker, on the argument that a
same-lineage reviewer shares the worker's blind spots. ADR 0004 puts it
on the Gemini free tier, on cost. Both were decided before anything had
been measured.

Measured on 2026-11-12, on four of the five cases, five runs each:

| Validator | Caught | Per judgment | Cost |
|---|---|---|---|
| `gemini-3.8-flash`, default effort (the roster today) | 5 of 20 | about 1 minute | free tier |
| `gemini-3.8-flash`, effort high | 18 of 20 | about 4 minutes | free tier |
| `claude-sonnet-5-5`, default effort | 8 of 20 | about 15 seconds | 6 cents |
| `claude-opus-5-5`, effort high | 16 of 20 | about 20 seconds | 13 cents |

And over the whole set (20 expected pass, 16 expected reject):

| Validator | Accepted work passed | Expected rejects caught |
|---|---|---|
| `gemini-3.8-flash`, default effort | 20 of 20 | 12 of 16 |
| `claude-opus-5-5`, effort high | 19 of 20 | 14 of 16 |

The Opus run found two real defects no earlier run had (`pr-27`,
`pr-39`). Its one wrong rejection, `pr-69`, turns on a sign-off recorded
in the pull request description, which the validator is not shown.

vpc's judgment on the second row: about four minutes a judgment is
borderline unacceptable for a gate.

Three more things bear on the choice, all recorded in
`planning/test-honesty-upstream/options.md`:

- **Published work does not support lineage as a rule.** The evidence
  found is that a reviewer's strength and a fresh context matter more
  than a different vendor, and that a weaker reviewer from another
  vendor can lower quality. It is thin evidence, on tasks unlike ours.
- **The same-lineage worry was tested here, a little.** The set's pull
  requests were written by Claude models, and a Claude validator found
  more of their defects than the Gemini one did.
- **The other ways to catch this defect are not ready.** A hand spike of
  a hostile review before the pull request found two of the five known
  cases squarely and missed two, and about half of what it flagged was
  not a thin test. The clause ledger is unmeasured.

The measurements are small. 16 and 18 of 20 cannot be told apart; the
move from 5 can.

## Decision

1. **The validator role is bound by measurement.** We will bind it to
   the model and effort whose scorecard on the eval set is best at a
   latency and cost vpc accepts, and change the binding when a later
   scorecard says so. The scorecard that justifies a binding is
   committed under `evals/validator/results/`.
2. **Lineage is a preference, not an obligation.** Between candidates
   whose scorecards cannot be told apart, we prefer the one of a
   different lineage than the worker. The validator still never shares a
   session or context with the worker it gates.
3. **The validator may run on a metered API.** A spend cap is set on the
   account before the first live run, as ADR 0004 requires of any
   metered surface. The previous binding stays one roster line away as
   the fallback.
4. **Today's binding, as the first use of this rule:**
   `anthropic:claude-opus-5-5` at effort `high`.
5. **Nothing else about the gate changes.** One model gate per pull
   request, advisory, judging conformance only, deterministic checks
   first (ADR 0008 decisions 1 to 4 and 6).

## Alternatives considered

- **Keep `gemini-3.8-flash` and raise its effort.** It measured as well
  as Opus on the four cases and stays free and of another lineage.
  Rejected on latency: about four minutes a judgment, one judgment
  within 600 tokens of the output limit, and no full run to show whether
  it wrongly rejects accepted work.
- **Keep today's binding and sweep merged work offline at high effort.**
  Costs nothing and is how the defects were found. Rejected as the
  whole answer: the gate would go on passing this defect about three
  times in four. Kept as a habit at spec close-out.
- **A stronger model of another lineage.** It would keep ADR 0001's
  rule. Not measured, so not chosen; under decision 1 it is one eval run
  and a roster line if someone wants to try it.
- **`claude-sonnet-5-5`.** Cheaper and as fast, but it caught 8 of 20.
- **A clause ledger in the verdict.** Unmeasured. It does not compete
  with this decision and can be tried on whatever model is bound.
- **A hostile review before the pull request, or falsifiable clauses in
  the spec.** The spike says its flags need a judge before they can
  reject anything. That is a larger build than a roster line, and ADR
  0008 already names a selective second reviewer as the path if the
  single gate proves not enough.
- **Mutation testing on changed lines.** Reaches little of this defect.
- **A yes/no decision model as the judge.** Cheaper still, but the one
  independent study has such models falling behind where the verdict
  must be worked out, and they return no quotes, which the gate
  requires.

## Consequences

- The gate should catch most thin tests, in about 20 seconds.
- The validator costs money: 9 to 13 cents a judgment as measured. The
  repository's 107 pull requests to date would have cost about $10 to
  $14. The eval's full run costs about $3.
- The validator and the worker are now the same vendor's models. If
  they do share blind spots, this gate will not see them, and nothing in
  the pipeline covers that today.
- The choice rests on a small sample. Opus still missed 4 of 20 on the
  check and two of the five thin tests in its full run. The gate will go
  on missing some.
- A model change is now expected, not exceptional: each needs a full
  eval run by vpc with a key before the roster line moves.
- The roster currency check already watches both providers; nothing
  changes there.
- Undo is one roster line.

## Adoption impact

Project ADR. On acceptance: `CLAUDE.md`'s project rule on lineage is
reworded to match decision 2, and ADR 0001, 0004 and 0008 each get a
note on their status line naming the decision this replaces.

Work it forces, each its own pull request:

1. **The effort setting** (`specs/role-effort`, draft pull request 108).
   Its check was written for Gemini and its third step was not run. The
   spec is amended to say what was run and on which model, for vpc's
   sign-off, before the implementation merges.
2. **The roster line**, with the Opus full run committed to main as the
   new baseline, the CI job given a way to reach Anthropic (the
   federation the roster currency check already uses, if its scope
   allows a model call; otherwise an Actions secret), a spend cap on the
   account, and `docs/architecture.md`'s settings table brought up to
   date.
3. **Showing the validator the pull request description**, as data and
   not as instructions. Not part of this decision, but it is what
   wrongly rejected `pr-69`.

## References

- ADR 0001, ADR 0004, ADR 0008 — the decisions replaced in part.
- `planning/test-honesty-upstream/options.md` — the options, the
  measurements, the published work and the spike's findings.
- `specs/role-effort/spec.md` — the effort setting this binding uses.
- `evals/validator/results/` — the scorecards. The Opus results are on
  the `feat/role-effort` branch until that work merges.

---

> Following the format proposed by Michael Nygard in
> [Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).
