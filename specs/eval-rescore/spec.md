# Spec: A stored eval result is read against today's answers

- **Status:** Implemented
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
and #103), each time because the judgment found a real defect in accepted
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
- **SC-6** — Each of the three result files in the repository on
  2026-11-12 loads and carries one and the same inputs fingerprint; a
  result with no inputs fingerprint is refused with a message that says
  so. (R-5)
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

- *2026-11-12* — **SC-6 amended before the implementation merged, in its
  own PR (#106; signed off by vpc, 2026-11-12).** As first signed it read: "Each of the three result files in
  the repository loads, carries the case set's inputs fingerprint, and
  `show` prints a scorecard for it". That ties three records of past
  runs to the case set as it is on whatever day the test runs: the first
  time a case is added or a bundle rebuilt they no longer carry "the
  case set's" fingerprint, `show` rightly refuses them (R-2), and the
  criterion's test fails a legitimate change. The criterion now names
  the date and asks only what stays true of the files. That `show`
  prints a scorecard for a result on the current inputs is SC-2's, and
  that it refuses one that is not is SC-3's. No requirement changes.
- *2026-11-12* — **Implemented by #105; signed off by vpc.** The inputs
  fingerprint of the repository's case set, and the value added to the
  three stored results, is `1f427ab0b735`; it was computed from the case
  files at the commit that added each result (`013c1e3`, `e1a6912`,
  `4782d17`) and today, and is the same at all four.
- *2026-11-12* — **`show` and `compare` take `--cases DIR`**, defaulting
  to `evals/validator/cases` as `run` does; results made on another
  directory need it. When two results match each other but not the cases
  on disk, `compare` refuses as `show` does.
- *2026-11-12* — **Three tests cited by the frozen eval-set spec's SC-9
  changed with the rule and kept their names**: two in
  `tests/evals/test_scorecard.py` now tell results apart by inputs
  fingerprint, and the one in `tests/evals/test_cli.py` passes `--cases`.

## Rollout and undo

Additive for `show`; a change of rule for `compare`, which starts
accepting pairs it refused. Undo is reverting the PR; the added field
in the three results is ignored by the older code.

No model is called and no key is needed, for the change or its tests.

## Open questions

All resolved 2026-11-12 (human sign-off: vpc accepted the four drafted
answers).

- [x] **The three stored results are edited to add one field.** They are
  records of runs, and this adds to them what was true of the run but
  not written down. The alternative leaves them untouched and makes the
  current baseline unreadable by the new commands, which defeats the
  purpose.
- [x] **`compare` always uses today's answers.** There is no flag to
  compare under the answers recorded at each run; those remain in the
  files for anyone who wants them.
- [x] **A result on other inputs is refused, not partly read.** If one
  case's bundle is rebuilt, every earlier result stops being readable
  by `show`. Per-case fingerprints would allow a partial reading and
  are left until that happens.
- [x] **`show` moves here from specs/judgment-stability** (PR #100, not
  merged), which this and ADR 0008 between them replace.

## Out of scope (for now)

- Per-case tallies for multi-run results and the "rejected at least
  once" reading drafted in specs/judgment-stability.
- A fixed thinking level for the validator.
- Resuming an interrupted run, or merging results.

## Traceability

| Criterion | Requirement(s) | Verified by (test) |
|---|---|---|
| SC-1 | R-1 | `tests/evals/test_rescore.py::test_sc1_the_inputs_fingerprint_moves_with_what_is_sent_and_not_with_the_answers`, `tests/evals/test_rescore.py::test_sc1_a_new_result_carries_the_inputs_fingerprint` |
| SC-2 | R-2 | `tests/evals/test_rescore.py::test_sc2_show_classes_a_stored_result_against_the_answers_on_disk` |
| SC-3 | R-2 | `tests/evals/test_rescore.py::test_sc3_show_refuses_a_result_whose_cases_have_changed` |
| SC-4 | R-3 | `tests/evals/test_rescore.py::test_sc4_compare_classes_both_results_against_the_answers_on_disk` |
| SC-5 | R-4 | `tests/evals/test_rescore.py::test_sc5_show_and_compare_leave_the_result_files_as_they_were` |
| SC-6 | R-5 | `tests/evals/test_rescore.py::test_sc6_a_result_recorded_before_the_change_carries_its_inputs_fingerprint`, `tests/evals/test_rescore.py::test_sc6_a_result_with_no_inputs_fingerprint_is_refused_saying_so` |
| SC-7 | R-6 | `tests/evals/test_rescore.py::test_sc7_a_run_records_what_it_recorded_before_plus_the_inputs_fingerprint` |
