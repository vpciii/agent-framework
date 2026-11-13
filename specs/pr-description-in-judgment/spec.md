# Spec: The judgment is shown the pull request's description

- **Status:** Approved
- **Date:** 2026-11-13
- **Author:** Claude (draft) — vpc is author of record
- **Related ADRs:** ADR 0008 (the validator judges conformance, cites
  and never asserts, code before model), ADR 0009 (the validator is
  bound by what the eval set measures), ADR 0007 (what a worker session
  may hand back)

> This spec is editable while `Draft` / `Under review` / `Approved`.
> When the PR that marks it `Implemented` merges it **freezes** into a
> historical record (methodology ADR 0027);
> a contradiction found later goes to a test, a new spec, or an ADR —
> not back into this file (methodology §2, §8).

## Problem

The validator judges a pull request without reading what its author
wrote about it. The collector reads the title and description for the
task id, the `Satisfies:` line and, on a fix, the paragraph describing
the failing run. The rest never reaches the judgment.

That cost one wrong rejection in the run that chose today's validator.
`pr-69` narrowed an allowlist in `plan.md` inside its implementing pull
request. Its description says so under its own heading, names the two
commits, and records that vpc signed the change off that day. The
judgment saw a plan rewritten to match the code and rejected it, noting:
"The claimed sign-off is not verifiable from the data." vpc ruled it
accepted work.

Published reviewers show the description to the model as untrusted data
(`planning/test-honesty-upstream/options.md`). Doing that here raises
two things that have to be settled in the same change:

- **What a description can establish.** It is written by the author of
  the work being judged. For a worker's pull request part of it is the
  session's own summary. It cannot be evidence that a test is honest.
- **The data region's closing marker is a fixed line.** Text in the diff
  or a test file that contains that line already ends the region early,
  and whatever follows reads as instructions. A description is the
  easiest place to put such a line.

## Goals

1. The judgment reads the pull request's title and description as the
   author's account of the change: data, never instructions.
2. A sign-off recorded there settles one kind of finding — the pull
   request changing its own contract — and only when the judgment quotes
   it and code finds the quote.
3. Nothing the judgment is sent can end the data region.
4. The eval set measures all three.

## Non-goals

- Verifying who wrote a description or that a sign-off is genuine. The
  validator is advisory and the human merges; this spec makes reliance
  on a sign-off visible, not proven.
- Commit messages, linked issues or review comments in the judgment.
- Whole changed files for the judgment, or asking it more than once.
- Sending the verdict back to the worker.

## Requirements

- **R-1 (MUST)** The evidence bundle carries the pull request's title
  and description as collected. A description longer than a fixed limit
  is cut at the limit and marked as cut.
- **R-2 (MUST)** The judgment's request shows both inside the data
  region, labelled as the author's account. With neither, the request is
  exactly what it is today.
- **R-3 (MUST)** The instructions say what the account is for:
  understanding what the change intends, and finding a recorded sign-off
  (R-5). They say it is never evidence that a test verifies a criterion,
  that CI passed or that the work is correct, and that instruction-like
  text in it is ignored.
- **R-4 (MUST)** No text inside the data region ends it. A diff, test
  file, criterion, task block or description containing the region's
  closing marker leaves the region closed where the request closes it.
- **R-5 (MUST)** A finding that rests on the pull request changing its
  own contract — its spec outside the Traceability table, its plan, or
  its tasks beyond a checkbox — is not raised when the judgment reports
  a sign-off for that change: a verbatim quote from the description
  saying the human signed it off. The work is then judged against the
  contract as the pull request leaves it. A contract change the
  description records no sign-off for is a finding, as today.
- **R-6 (MUST)** Code checks each reported sign-off's quote against the
  description as sent, as it checks a finding's quotes. A sign-off whose
  quote is not found is logged, and the judgment is "could not judge"
  with a reason naming it; it is never a PASS.
- **R-7 (MUST)** A PASS that relied on a sign-off carries each quote:
  the verdict, its JSON and its rendering show it. A PASS that relied on
  none has the same keys as today.
- **R-8 (MUST)** The eval set's accepted cases carry their pull
  requests' titles and descriptions. Three seeded cases are added: a
  description that tells the judgment to pass, over a seeded defect; a
  contract change whose description records no sign-off; and a
  description that claims a sign-off for a different change than the one
  made.
- **R-9 (SHOULD)** The delivery records a full run from before the
  change and one from after.

## Success criteria

- **SC-1** — Through `collect_bundle` with a faked `gh`: the bundle
  carries the pull request's title and description; a description over
  the limit is cut at it and says so. (R-1)
- **SC-2** — The judgment's request for such a bundle shows the title
  and description inside the data region under their own label; for a
  bundle with neither, the request equals today's. (R-2)
- **SC-3** — The request's instructions state that the description is
  the author's account, is not evidence of a test's honesty, of CI or of
  correctness, and carries no instructions. (R-3)
- **SC-4** — For a bundle whose description, diff and test file each
  contain the closing marker followed by an instruction, the text the
  quote check treats as data includes all three in full, and nothing
  after the request's own closing marker. (R-4)
- **SC-5** — With a fake provider reporting no defect and a sign-off
  whose quote is in the description, the gate's verdict is a PASS
  carrying that quote, and its JSON and rendering show it; with no
  sign-off reported, the PASS's JSON has the same keys as before. (R-5,
  R-7)
- **SC-6** — With a fake provider reporting a sign-off whose quote is
  not in the description, the gate's CLI exits 3 with a reason naming
  the unsupported sign-off, and the quote is logged. (R-6)
- **SC-7** — The request's instructions state the rule of R-5: which
  changes count as the contract, that a sign-off must be quoted from the
  description, and that an unrecorded contract change is a finding.
  (R-5)
- **SC-8** — Every accepted eval case carries a title and description,
  and the three seeded cases of R-8 exist, each expected to be rejected
  under the check its defect belongs to; the set still passes the
  deterministic stage with no model call. (R-8)

## Glossary additions (proposed with this spec)

None. "Sign-off" is the methodology's word and is used as it is there.

## Approach

Two pull requests. The first changes nothing a stored eval result
depends on; the second does.

**First: show the description, close the region.** (SC-1 to SC-4)

- `validator/bundle.py`, `validator/collector.py` — `EvidenceBundle`
  gains the title and description, both optional so stored bundles load
  unchanged. The collector already fetches them.
- `validator/judgment.py` — a labelled block in the data region,
  omitted when there is neither; the instructions of R-3; and the
  closing marker made unforgeable. The marker's exact form is the
  implementer's choice; SC-4 is the test.
- The eval's cases carry no description yet, so what they send does not
  change and the stored results still read. The instructions'
  fingerprint moves, as it must.

**Second: the sign-off rule and the eval.** (SC-5 to SC-8)

- `validator/judgment.py` — the verdict tool gains an optional list of
  sign-offs, each a quote; the instructions of R-5; the quote check
  extended to them, with a new could-not-judge reason.
- `validator/verdict.py`, `validator/render.py`, `validator/gate.py` —
  a PASS carries the quotes it relied on.
- `evals/` — `freeze` stores the title and description; every accepted
  case is rebuilt; three seeded cases. Rebuilding changes what the cases
  send, so the four full runs on record stop reading against the set
  (the limit specs/eval-rescore accepted), and a new baseline is run.
- Docs in the same pull requests: the validator and eval rows of
  `docs/architecture.md`, its trust-boundary entry for the judgment, and
  step 3 of `docs/adoption.md`.

### Decisions

- *(none yet)*

## Rollout and undo

Each pull request is undone by reverting it. The first changes what
every live judgment is sent from the moment it merges. The second
changes the verdict's JSON only for a PASS that relied on a sign-off.

**The check (R-9).** Run by vpc, with a key, from the second pull
request's branch before it merges: one full run. It is read beside
`claude-opus-high-full.json` by its scorecard; `compare` cannot pair the
two, because the cases no longer send the same thing. What to look for:

- `pr-69` passes, and its PASS carries the sign-off's quote.
- The three new seeded cases are caught.
- No accepted case that passed before is rejected now.

**Cost.** About 39 judgments on `claude-opus-5-5` at `high`: roughly
$3.50, from the plan's API credit.

**What this does not protect against.** A description that falsely
records a sign-off will be quoted faithfully and the PASS will say it
relied on it. The protection is that the reliance is printed where the
human reads the verdict, and that the human merges.

## Open questions

All resolved 2026-11-13 (human sign-off: vpc accepted the five drafted
answers).

- [x] **Is a recorded sign-off enough to settle the finding, when the
  validator cannot verify it?** Drafted: yes, with R-7 making the
  reliance visible. The alternative is to go on rejecting and let vpc
  overrule each time, which makes `pr-69` an expected rejection again.
- [x] **An unsupported sign-off: could not judge, or REJECT?** Drafted:
  could not judge, as an unsupported finding is. Code does not write a
  finding the model did not make.
- [x] **The limit on a description's length.** Drafted: 20,000
  characters. `pr-69`'s is about 4,000; GitHub allows 65,536.
- [x] **Does this need an ADR?** Drafted: yes, for the second pull
  request only. Taking an author's recorded sign-off on trust is a
  decision about what the validator accepts, and belongs beside ADR
  0008. The first pull request adds one more untrusted input to a region
  that already holds the diff, and needs none.
- [x] **A worker can edit `plan.md` today.** The handoff check refuses
  changes to a spec's text and to a tasks file, and not to a plan. A
  worker's summary also lands in its pull request's description.
  Drafted: out of scope here, and worth its own small spec before the
  sign-off rule is relied on for worker pull requests.

## Out of scope (for now)

- Refusing a plan edit at the worker's handoff (above).
- Telling a human-written description from a worker's summary.
- Reading a sign-off from a commit message.
- The verdict posted on the pull request or sent back to the worker.

## Traceability

| Criterion | Requirement(s) | Verified by (test) |
|---|---|---|
| SC-1 | R-1 | `tests/validator/test_description.py::test_sc1_the_bundle_carries_the_title_and_description`, `tests/validator/test_description.py::test_sc1_a_description_over_the_limit_is_cut_and_says_so` |
| SC-2 | R-2 | `tests/validator/test_description.py::test_sc2_the_request_shows_them_inside_the_data_region_under_their_own_label`, `tests/validator/test_description.py::test_sc2_a_bundle_with_neither_sends_todays_request` |
| SC-3 | R-3 | `tests/validator/test_description.py::test_sc3_the_instructions_say_what_the_description_is_and_is_not_for` |
| SC-4 | R-4 | `tests/validator/test_description.py::test_sc4_a_closing_marker_inside_the_data_does_not_end_it`, `tests/validator/test_description.py::test_sc4_a_lookalike_marker_also_gets_the_data_a_tagged_region` |
| SC-5 | R-5, R-7 | *(pending)* |
| SC-6 | R-6 | *(pending)* |
| SC-7 | R-5 | *(pending)* |
| SC-8 | R-8 | *(pending)* |
