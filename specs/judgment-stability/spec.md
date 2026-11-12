# Spec: Reading the judgment's stability from the eval

- **Status:** Draft
- **Date:** 2026-11-12
- **Author:** Claude (draft) — vpc is author of record
- **Related ADRs:** ADR 0005 (one per-PR gate; its judgment is one model
  call), ADR 0001 (roles are bound by the roster)

> This spec is editable while `Draft` / `Under review` / `Approved`.
> When the PR that marks it `Implemented` merges it **freezes** into a
> historical record (methodology ADR 0027);
> a contradiction found later goes to a test, a new spec, or an ADR —
> not back into this file (methodology §2, §8).

## Problem

The judgment does not give the same verdict twice on the same input.

The eval set was run in full on 2026-11-10 and again on 2026-11-12: the
same model, the same instructions (`e6614c584085`) and the same 36
bundles. 33 cases got the same verdict both times. Three did not —
`pr-18`, `pr-37` and `pr-59` were rejected in the first run and passed in
the second. They are three of the four real defects the judgment found in
accepted work, the ones nobody planted. All nine seeded defects were
caught both times, and no case now expected to pass was rejected in
either run.

So a PASS from one judgment means "this run found nothing". On a subtle
defect, whether the gate catches it depends on which run it was.

**The eval cannot yet say how much.** The finding above was made by
reading two result files side by side:

- `compare` refuses the two results, correctly: four expected answers
  changed between them, so their case sets differ.
- `--runs N` exists and the scorecard names the cases whose runs
  disagree. But its counts are of judgments, not cases; it does not say
  how a case's runs fell (caught once in three, or twice); and `compare`
  sets a case's classes side by side in run order, so an unstable case
  shows as "changed" between two results whenever its runs happen to
  fall in a different order.
- A stored result cannot be read again. The scorecard is printed once,
  at the end of the run that made it.

The last two matter beyond this finding. Every change to the judgment is
meant to cite a run from before and after (`docs/architecture.md`). On a
case that varies by itself, one run each side cannot tell a change from
that variation.

**The usual setting is not available.** The first idea was to turn the
sampling temperature down to zero. Neither provider offers it any more:

- Google: `temperature`, `top_p` and `top_k` are deprecated and ignored
  from Gemini 3.6 Flash onward, and are to become an error
  (<https://aistudio.google.com/docs/whats-new-gemini-3.6>, read
  2026-11-12).
  Its advice for determinism is explicit rules in the instructions.
- Anthropic: the same three parameters are removed on its current
  models, and a request that sets them is refused with a 400; from API
  version `2026-10-21` that holds on every model (Anthropic's API
  reference as shipped with Claude Code, read 2026-11-12; no public
  page was found that states it).

The judgment's request sets none of them today, so there is nothing to
turn down.

What is left — asking more than once, a higher effort setting, showing
the judge whole files, rewording the checklist — each costs something
and each is a guess until it is measured. The measurement comes first.

## Goals

1. One multi-run result says, for every case, how its runs fell, and
   which cases are steady and which are not.
2. The same result says what a gate that asked several times and
   rejected on any REJECT would have returned on these cases — the
   defects it would catch and the accepted work it would wrongly reject.
3. Comparing two results separates a case that changed from a case that
   varies.
4. A stored result can be read again.
5. A three-run baseline is on record.

## Non-goals

- **Reducing the instability.** Nothing about the judgment changes: not
  its instructions, its schema, what it is sent, the roster, or how many
  times the gate asks. This spec makes the choice between those
  measurable; it does not make it.
- Sampling parameters, on any provider (see *Problem*).
- Claims of statistical significance. Three runs separate "always" from
  "sometimes"; they do not separate one time in three from one in two.
- Gating anything on the result.

## Requirements

- **R-1 (MUST)** For a result with more than one run per case, the
  scorecard counts **cases** as well as judgments. A case is **steady**
  when every one of its judged runs fell in the same class, and
  **unstable** otherwise. For each kind of case the scorecard gives the
  number steady in each class and the number unstable. A run that could
  not be judged is left out of that decision; a case with no judged run
  is counted as could not judge, and as neither steady nor unstable.
- **R-2 (MUST)** Every unstable case is listed with how its runs fell —
  for example `pr-18 — caught 1 of 3, missed 2 of 3`.
- **R-3 (MUST)** For a result with more than one run per case, the
  scorecard states how many cases expected to be rejected were rejected
  in at least one run, and how many expected to pass were rejected in at
  least one run, naming every case rejected in some of its runs but not
  all. A REJECT under any checklist item counts. The line says what it is: what
  a gate asking that many times, and rejecting on any REJECT, would have
  returned.
- **R-4 (MUST)** `compare` reports a case as **changed** only when it is
  steady in both results and its class differs. A case unstable in
  either result is listed apart, with how its runs fell in each, and is
  not counted as changed. The order of a case's runs never makes a
  difference.
- **R-5 (MUST)** When either result compared has one run per case, the
  comparison says so: a single run cannot tell a change from the
  judgment's own variation.
- **R-6 (MUST)** `agent-framework-eval show <result>` prints the
  scorecard of a stored result, as `run` printed it. A file that is not
  a result is refused with exit 2.
- **R-7 (MUST NOT)** This change MUST NOT alter the gate, the judgment's
  request, or the judgments a result file records. Result files already
  in the repository still load, and a one-run result reads as it does
  today.
- **R-8 (SHOULD)** The delivery PR records a three-run baseline, run by
  the human with a key and committed as a result file.
  `docs/architecture.md` names it as the record of which cases are
  unstable.

## Success criteria

- **SC-1** — Given a three-run result holding a steady case of each
  class and an unstable case of each kind, the scorecard's case counts
  are right. A case with one run that could not be judged and two that
  agree is steady; a case with no judged run is counted as could not
  judge. (R-1)
- **SC-2** — The rendering names each unstable case with how its runs
  fell. (R-2)
- **SC-3** — The rendering states, for each kind of case, how many were
  rejected in at least one run and names those rejected in some runs
  but not all; a rejection under another checklist item counts. A one-run result
  carries no such line. (R-3)
- **SC-4** — Comparing two three-run results: a case steady in both
  with different classes is reported as changed; a case whose runs fall
  in the same classes in a different order is not; a case unstable in
  either is listed apart with both tallies and is not among the changed.
  (R-4)
- **SC-5** — A comparison in which either result has one run per case
  says a single run cannot tell a change from variation. (R-5)
- **SC-6** — `show` on a stored result prints what `run` printed for it
  and exits 0; on a file that is not a result it exits 2 and names the
  file. (R-6)
- **SC-7** — The two result files in the repository today load and
  render, and a one-run result's rendering has no steady or unstable
  section. (R-7)

## Glossary additions (proposed with this spec)

Added to `docs/glossary.md` in the implementing PR.

- **Steady case / unstable case** — in one eval result with more than
  one run per case: a case whose judged runs all fell in the same class
  is steady; one whose runs disagree is unstable.

## Approach

One PR. Everything is in the eval's reading of judgments it already
records; nothing is asked of a model that is not asked today.

- `evals/scorecard.py` — a pure function from a result's judgments to
  each case's tally of classes. `Scorecard` gains the case counts and
  the rejected-at-least-once lists; `render` prints them when the result
  has more than one run. `Comparison` gains the list of cases unstable
  in either result; `compare` compares tallies, not run-ordered tuples.
- `evals/__main__.py` — the `show` command, reusing `_read` and
  `render`.
- The result file's `judgments` are unchanged. Its `scorecard` block is
  derived and already recomputed on read, so it gains fields and older
  files need no migration.
- Not touched: `evals/run.py`, `evals/case.py`, `validator/`,
  `providers/`, the roster.
- Tests in `tests/evals/test_scorecard.py` and `tests/evals/test_cli.py`,
  with a fake provider and hand-built results; no key.
- Docs in the same PR: the eval section of `docs/adoption.md`, the eval
  rows and the before-and-after paragraph of `docs/architecture.md`, and
  the glossary entry.

If the diff passes about 300 lines, `show` moves to a second PR.

### Decisions

- *(none yet)*

## Rollout and undo

Additive, and it reads only what is already recorded. Undo is reverting
the PR. Nothing is stored outside the repository.

The baseline (R-8) is 108 judgments. At the pace of the two full runs so
far — 36 judgments in about 33 minutes — that is about 100 minutes, and
about 1.36 million input and 0.7 million output tokens. A rate limit
part-way through does not end the run: the cases it hits are recorded as
could not judge, and the result has holes.

## Open questions

Each has a drafted answer; all are vpc's to accept or change.

- [ ] **Three runs for the baseline, not five.** Three is about 100
  minutes and separates "always" from "sometimes". Five is nearly three
  hours for a finer reading nobody has asked for yet.
- [ ] **"Rejected at least once" counts a REJECT under any checklist
  item** (R-3), not only under the item the case names. The gate rejects
  whatever the item; the per-item reading is already in the class
  counts.
- [ ] **The before-and-after rule becomes: the same number of runs on
  both sides, and three when the change is to the judgment.** One run
  each side stays fine for a smoke check. This raises the cost of
  changing the judgment to about 100 minutes a side, and is why R-5
  only warns rather than refuses.
- [ ] **`show` is in this spec.** It is small, and without it the new
  reading reaches only results made after the change.
- [ ] **What to do about the instability is decided after the
  baseline,** not here (see *Out of scope*).

## Out of scope (for now)

Each is a candidate for the next spec. The baseline says what the first
would buy before anything is built; the others each need a three-run
result of their own to compare against it.

- **Asking the judgment more than once at the gate and rejecting on any
  REJECT.** ADR 0005 fixes the gate at one model call per PR, so this
  needs an ADR that supersedes that part of it, and it multiplies the
  judgment's cost and time. R-3's line is its predicted effect.
- **A per-role effort setting in the roster** — more thinking for the
  validator. Deferred by specs/judgment-reliability until the eval could
  measure it.
- **Whole changed files for the judge instead of diff hunks**, and
  rewording the checklist.
- Resuming an interrupted run, or merging several results into one.
- A merge rule or required check built on the result.

## Traceability

| Criterion | Requirement(s) | Verified by (test) |
|---|---|---|
| SC-1 | R-1 | *(pending)* |
| SC-2 | R-2 | *(pending)* |
| SC-3 | R-3 | *(pending)* |
| SC-4 | R-4 | *(pending)* |
| SC-5 | R-5 | *(pending)* |
| SC-6 | R-6 | *(pending)* |
| SC-7 | R-7 | *(pending)* |
