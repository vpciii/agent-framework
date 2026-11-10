# Spec: A finding's evidence is checked against what was sent

- **Status:** Approved
- **Date:** 2026-11-09
- **Author:** Claude (draft) — vpc is author of record
- **Related ADRs:** ADR 0005 (one per-PR gate; "cite, never assert"),
  ADR 0001 (no vendor in the gate)

> This spec is editable while `Draft` / `Under review` / `Approved`.
> When the PR that marks it `Implemented` merges it **freezes** into a
> historical record (methodology ADR 0027);
> a contradiction found later goes to a test, a new spec, or an ADR —
> not back into this file (methodology §2, §8).

## Problem

The gate's rule is that a verdict cites and never asserts. A PASS is held
to it by code: every citation is a test the spec's Traceability table
names, confirmed to exist and to mention the criterion. A REJECT is not.
Its findings carry an `evidence` string the model wrote, and nothing
checks it.

On 2026-11-09 a live judgment of the merged PR #77 came back REJECT with
one finding: that `run_checks` calls `table_citations` when no spec was
resolved and so crashes on an assertion. It quoted three pieces of code
as evidence. Two were real. The third — the one the finding rests on —
does not exist:

```python
if bundle.contract is not None:
    if bundle.contract.problem:
        findings.append(...)
```

The real code guards exactly that case, on a line the PR did not change
and the diff therefore did not show. The model could not see the guard,
and filled the gap. The finding was false, the evidence was invented, and
the gate reported it as a REJECT like any other.

A wrong REJECT costs more than it looks. To a human it is an hour spent
disproving a bug that is not there. To a worker session, once verdicts
are fed back, it is an instruction to "fix" correct code.

**Replayed after the fact.** Checking each quoted excerpt against the
data that was actually sent to the model separates them cleanly — the two
real excerpts are found, the invented one is not — provided the diff is
read one side at a time. A first attempt against the raw diff text also
failed to find one of the *real* excerpts, because a diff interleaves
removed lines among the added ones.

## Goals

1. A finding reaches a REJECT only if every piece of code or text it
   quotes as evidence is actually in what the model was sent.
2. A judgment whose findings are all unsupported is reported as "could
   not judge" — never as a REJECT, and never as a PASS.
3. The model knows the rule, so it quotes what it can see and says so
   when a defect would depend on something it cannot.
4. A finding names which of the gate's checks it comes from, in a fixed
   vocabulary.

## Non-goals

- Showing the model more than it sees today (whole changed files rather
  than diff hunks). It would likely reduce invented evidence, and it
  costs tokens on every judgment; it wants the eval set to measure it.
- Judging whether a *supported* finding is correct. Evidence that exists
  can still be misread; that is the eval set's question.
- Changing a PASS, or the verdict's JSON shape.
- A retry when findings are unsupported (ADR 0005: one judgment call).

## Requirements

- **R-1 (MUST)** The verdict tool asks, for every finding, for one or
  more **quotes**: verbatim, contiguous excerpts of the data the model
  was sent that the finding rests on. A finding with no quote is
  malformed.
- **R-2 (MUST)** A quote is **found** when, ignoring differences in
  whitespace, it appears in the data region of the request that was
  sent: in the tests, the contract or the other evidence as written, or
  in the diff read as its new side (unchanged and added lines) or as its
  old side (unchanged and removed lines). A quote shorter than a minimum
  length is not accepted as evidence.
- **R-3 (MUST)** A finding is **supported** only when every one of its
  quotes is found. An unsupported finding never appears in a verdict.
- **R-4 (MUST)** When the model reports a defect and at least one
  finding is supported, the verdict is REJECT carrying exactly the
  supported findings. When it reports a defect and none is supported,
  there is no verdict: the gate reports "could not judge" with the reason
  `unsupported-finding`.
- **R-5 (MUST)** Every unsupported finding is logged with the quote that
  was not found, so a human can see what was dropped and why.
- **R-6 (MUST)** The judgment's instructions tell the model that its
  quotes are checked against the data, that it sees only part of each
  changed file, and that it must not quote or describe code it was not
  shown.
- **R-7 (MUST)** A finding's `check` is one of four fixed names — one per
  item of the refutation checklist — enforced by the tool's schema.
- **R-8 (MUST NOT)** A judgment that reports no defect MUST NOT be
  affected; the verdict JSON's shape, and the exit codes for PASS and
  REJECT, MUST NOT change.

## Success criteria

- **SC-1** — The verdict tool's schema requires, per finding, a
  non-empty list of quotes, and restricts `check` to the four names; a
  finding without quotes raises the existing malformed-judgment error.
  (R-1, R-7)
- **SC-2** — Quote matching: an excerpt of added code is found in a diff
  where removed lines are interleaved among the added ones; an excerpt of
  removed code is found; an excerpt of a test file or of the contract is
  found; differences in indentation and line breaks do not matter; an
  excerpt that appears nowhere is not found; an excerpt below the minimum
  length is not accepted. (R-2)
- **SC-3** — The 2026-11-09 case, as a fixture: a finding with two real
  quotes and one invented one is unsupported; the judgment that carries
  only that finding raises "could not judge" with reason
  `unsupported-finding`, and the gate's CLI exits 3. (R-3, R-4)
- **SC-4** — A judgment with one supported and one unsupported finding
  yields a REJECT carrying only the supported one. (R-3, R-4)
- **SC-5** — Each unsupported finding is logged with the quote that was
  not found. (R-5)
- **SC-6** — The request's instructions state that quotes are checked,
  that only part of each changed file is shown, and that unseen code must
  not be quoted; the text is pinned by a test. (R-6)
- **SC-7** — A no-defect judgment yields the same PASS as before; a
  REJECT's JSON has the same keys as before; PASS still exits 0 and
  REJECT 1. (R-8)

## Approach

One PR, in the judgment and nowhere else.

- **Tool schema.** Each finding gains `quotes` (array of strings, at
  least one). `check` becomes an enumeration: `test-honesty`,
  `spec-conformance`, `criteria-integrity`, `edge-case`. The schema is
  already closed, so both are enforced by the provider (judgment-
  reliability).
- **Matching.** Pure functions over the request's own data region — the
  text between the data markers, exactly as sent. Whitespace runs are
  collapsed on both sides. The data is prepared three ways: as written;
  with removed diff lines dropped and markers stripped (the new side);
  with added diff lines dropped and markers stripped (the old side). A
  quote is found if it is a substring of any of the three. Minimum
  length: 12 non-whitespace characters.
- **Judgment.** After parsing the call: partition findings into
  supported and unsupported, log the unsupported, and either return the
  supported findings or raise `NoVerdictError("unsupported-finding", …)`.
  `Finding` itself — `check`, `finding`, `evidence` — is unchanged; the
  quotes are how a finding is admitted, not part of the verdict.
- **Instructions.** Two sentences added to the instruction boundary; the
  refutation checklist's wording is unchanged.

### Decisions

- *2026-11-10* — vpc accepted all five open questions as drafted.

## Rollout and undo

The gate is advisory (ADR 0005). Undo is reverting the PR. Visible
changes: some judgments that today come back REJECT will come back as
"could not judge" (exit 3) or as a REJECT with fewer findings; `check`
values become the four fixed names. The failure direction is deliberate:
a real defect whose evidence the model quoted inexactly is reported as
"could not judge", never as a PASS.

The roster's validator is reached through its own adapter, so the closed
schema's new fields need the same live confirmation the last change did:
one judgment with a key, before merge.

## Open questions

All resolved 2026-11-10 (human sign-off).

- [x] **Every quote must be found** (R-3), not most of them. In the case
  that prompted this, two of three quotes were real and the finding was
  still false — the invented one was the one that mattered.
- [x] **All findings unsupported: "could not judge"** (R-4), not PASS.
  The model said there is a defect; that it could not show one is not
  evidence there is none.
- [x] **Unsupported findings go to the log only** (R-5), so the
  verdict's JSON shape is untouched.
- [x] **`check` is fixed to four names in the same change** (R-7). The
  live run put a whole checklist sentence in that field; the schema is
  being edited anyway.
- [x] **Whole changed files instead of hunks: not here** (non-goal).
  This spec makes invented evidence harmless; that change would make it
  rarer, at a token cost that should be measured.

## Out of scope (for now)

- An eval set for the judgment — the next thing this points at: with it,
  "how often is a finding unsupported" and "does more context help"
  become measurements.
- Whole-file context for the judgment.
- A per-request data fence and filtering what is sent as the diff.

## Traceability

| Criterion | Requirement(s) | Verified by (test) |
|---|---|---|
| SC-1 | R-1, R-7 | `tests/validator/test_finding_evidence.py::test_sc1_the_schema_requires_quotes_and_fixes_the_check_names`, `tests/validator/test_finding_evidence.py::test_sc1_a_finding_without_quotes_is_malformed`, `tests/validator/test_finding_evidence.py::test_sc1_a_check_outside_the_four_names_is_malformed` |
| SC-2 | R-2 | `tests/validator/test_finding_evidence.py::test_sc2_an_excerpt_of_what_was_sent_is_found`, `tests/validator/test_finding_evidence.py::test_sc2_an_excerpt_that_was_not_sent_is_not_found`, `tests/validator/test_finding_evidence.py::test_sc2_an_excerpt_below_the_minimum_length_is_not_accepted`, `tests/validator/test_finding_evidence.py::test_sc2_the_data_searched_is_exactly_the_data_sent` |
| SC-3 | R-3, R-4 | `tests/validator/test_finding_evidence.py::test_sc3_the_false_finding_is_unsupported_and_there_is_no_verdict`, `tests/validator/test_finding_evidence.py::test_sc3_the_cli_reports_could_not_judge_and_exits_three` |
| SC-4 | R-3, R-4 | `tests/validator/test_finding_evidence.py::test_sc4_a_reject_carries_only_the_supported_finding`, `tests/validator/test_finding_evidence.py::test_sc4_a_finding_with_one_short_quote_is_unsupported` |
| SC-5 | R-5 | `tests/validator/test_finding_evidence.py::test_sc5_an_unsupported_finding_is_logged_with_the_quote_not_found`, `tests/validator/test_finding_evidence.py::test_sc5_it_is_logged_before_could_not_judge_is_raised` |
| SC-6 | R-6 | `tests/validator/test_finding_evidence.py::test_sc6_the_instructions_state_the_quote_rule` |
| SC-7 | R-8 | `tests/validator/test_finding_evidence.py::test_sc7_a_no_defect_judgment_is_the_same_pass`, `tests/validator/test_finding_evidence.py::test_sc7_pass_and_reject_keep_their_codes_and_a_reject_its_keys` |
