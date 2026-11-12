# Spec: A stored eval result is read against today's answers

- **Status:** Draft
- **Date:** 2026-11-12
- **Author:** Claude (draft) — vpc is author of record
- **Related ADRs:** ADR 0008 (what the judgment is for)

> This spec is editable while `Draft` / `Under review` / `Approved`.
> When the PR that marks it `Implemented` merges it **freezes** into a
> historical record (methodology ADR 0027);
> a contradiction found later goes to a test, a new spec, or an ADR —
> not back into this file (methodology §2, §8).

## Problem

Correcting a case's expected answer throws away the baseline, although
nothing the model saw has changed.

A result is tied to a fingerprint of the whole case set, answers
included, and `compare` refuses two results whose fingerprints differ.
The answers have been corrected three times in three days (#99, #102,
and #103, open as this is written), each time because the judgment found a real defect in accepted
work. Each time the stored result stopped being comparable with
anything, and the choice was a fresh run — 33 minutes with vpc's key —
or a re-reading by hand in a PR body.

The judgments themselves were never in question. What each case sends
the judgment was byte-for-byte the same at all three recorded runs and
is the same today; only answers, checklist items and reasons moved. A
judgment's class — passed, caught, missed — is computed by code from
its outcome and the case's answer, so it can be computed again.

There is also no way to read a stored result at all: the scorecard is
printed once, by the run that made it.

## Goals

1. Correcting an answer never calls for a new run.
2. Two results are comparable when the model was shown the same cases,
   whatever the answers were at the time.
3. A stored result can be read again, against the answers as they are
   now.

## Non-goals

- Re-scoring across a change to what a case sends. If a bundle or a
  seeded edit changes, the judgments are of something else.
- Comparing across a change to the judgment's instructions any
  differently than today: that is what `compare` is for, and it already
  shows both fingerprints.
- Reading multi-run results more finely, or steadying the judgment.
- Rewriting what a result file records about its run.

## Requirements

- **R-1 (MUST)** A result records an **inputs fingerprint**: a short
  hash of what every case sends the judgment — its id and its evidence
  bundle, after a seeded edit is applied — and of nothing else. A case's
  expected answer, checklist item and reason do not move it; a change to
  a bundle or an edit, or a case added or removed, does.
- **R-2 (MUST)** `agent-framework-eval show <result>` prints the
  scorecard of a stored result with each judgment classed against the
  answers in the case set on disk. It names every case whose answer
  differs from the one recorded at the run. It refuses, exit 2, when the
  result's inputs fingerprint is not the case set's.
- **R-3 (MUST)** `compare` accepts two results whose inputs fingerprints
  match and the case set's, and classes both against the answers on
  disk before comparing. It refuses on the inputs fingerprint, not on
  the case-set fingerprint.
- **R-4 (MUST)** Reading a result never changes it. `show` and `compare`
  write no file.
- **R-5 (MUST)** The three results in the repository gain their inputs
  fingerprint in the implementing PR, and nothing else in them changes.
  A result with no inputs fingerprint is refused by `show` and
  `compare`, saying why.
- **R-6 (MUST NOT)** The change MUST NOT alter the gate, the judgment's
  request, how a run is made, or how a judgment is classed.

## Success criteria

- **SC-1** — The inputs fingerprint of a case set is unchanged when a
  case's expected answer, checklist item or reason changes, and changes
  when a bundle changes, a seeded edit changes, or a case is added or
  removed. A new result carries it. (R-1)
- **SC-2** — Given a stored result and a case set in which one case's
  answer has since changed from `pass` to `reject`, `show` prints that
  case as caught, not wrongly rejected, counts it so, and names it as
  re-scored. (R-2)
- **SC-3** — `show` on a result whose inputs fingerprint is not the case
  set's exits 2 and says the cases have changed since the run. (R-2)
- **SC-4** — `compare` on two results with the same inputs fingerprint
  and different case-set fingerprints compares them, each classed
  against the answers on disk; on two with different inputs fingerprints
  it exits 2. (R-3)
- **SC-5** — After `show` and `compare`, the result files are
  byte-for-byte what they were. (R-4)
- **SC-6** — Each of the three result files in the repository loads,
  carries the case set's inputs fingerprint, and `show` prints a
  scorecard for it; a result with no inputs fingerprint is refused with
  a message that says so. (R-5)
- **SC-7** — For the same cases and the same provider answers, a run
  records the judgments and classes it recorded before the change; its
  result differs only in carrying the inputs fingerprint. (R-6)

## Glossary additions (proposed with this spec)

Added to `docs/glossary.md` in the implementing PR.

- **Inputs fingerprint** — a short hash of what every case in the eval
  set sends the judgment. Two results with the same inputs fingerprint
  judged the same cases, whatever answers were expected at the time.

## Approach

One PR.

- `evals/case.py` — `inputs_fingerprint(directory)`, beside
  `set_fingerprint`, hashing each loaded case's id and bundle.
- `evals/scorecard.py` — `Result` gains `inputs`; a pure `rescore(result,
  cases)` returns the result with every judgment's expected answer,
  checklist item and class recomputed by the existing `classify`, and
  the list of cases whose answer changed. `compare` takes results
  already re-scored.
- `evals/__main__.py` — `run` records the inputs fingerprint; `show` is
  new; `show` and `compare` take `--cases DIR` and re-score before
  rendering.
- The case-set fingerprint stays in the result as the record of which
  answers were in force at the run. It no longer gates anything.
- The three stored results get one new field, `inputs`, by hand in the
  implementing PR. The value is checked, not assumed: the case files at
  the commit that added each result (`013c1e3`, `e1a6912`, `4782d17`)
  send the same thing as today's — verified on 2026-11-12, and the
  check is repeated and cited in that PR.
- Docs in the same PR: the eval section of `docs/adoption.md`, the eval
  rows and the before-and-after paragraph of `docs/architecture.md`,
  the glossary entry.

### Decisions

- *(none yet)*

## Rollout and undo

Additive for `show`; a change of rule for `compare`, which starts
accepting pairs it refused. Undo is reverting the PR; the added field
in the three results is ignored by the older code.

No model is called and no key is needed, for the change or its tests.

## Open questions

Each has a drafted answer; all are vpc's to accept or change.

- [ ] **The three stored results are edited to add one field.** They are
  records of runs, and this adds to them what was true of the run but
  not written down. The alternative leaves them untouched and makes the
  current baseline unreadable by the new commands, which defeats the
  purpose.
- [ ] **`compare` always uses today's answers.** There is no flag to
  compare under the answers recorded at each run; those remain in the
  files for anyone who wants them.
- [ ] **A result on other inputs is refused, not partly read.** If one
  case's bundle is rebuilt, every earlier result stops being readable
  by `show`. Per-case fingerprints would allow a partial reading and
  are left until that happens.
- [ ] **`show` moves here from specs/judgment-stability** (PR #100, not
  merged), which this and ADR 0008 between them replace.

## Out of scope (for now)

- Per-case tallies for multi-run results and the "rejected at least
  once" reading drafted in specs/judgment-stability.
- A fixed thinking level for the validator.
- Resuming an interrupted run, or merging results.

## Traceability

| Criterion | Requirement(s) | Verified by (test) |
|---|---|---|
| SC-1 | R-1 | *(pending)* |
| SC-2 | R-2 | *(pending)* |
| SC-3 | R-2 | *(pending)* |
| SC-4 | R-3 | *(pending)* |
| SC-5 | R-4 | *(pending)* |
| SC-6 | R-5 | *(pending)* |
| SC-7 | R-6 | *(pending)* |
