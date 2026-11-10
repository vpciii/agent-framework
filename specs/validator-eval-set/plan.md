# Plan: An eval set for the validator's judgment

- **Status:** Approved
- **Date:** 2026-11-10
- **Author:** Claude (draft) — vpc is author of record
- **Spec:** ./spec.md
- **Related ADRs:** ADR 0005, ADR 0001, ADR 0004

> This plan freezes with its spec: editable while `Draft` / `Under
> review` / `Approved`, and a historical record once the PR that marks
> the spec `Implemented` merges (methodology §2, ADR 0027). A
> contradiction found later goes to a test, a new spec, or an ADR — not
> back into this file.

## Approach

A new package, `agent_framework.evals`, in the shape the validator and
the worker already have: a pure core and thin edges.

1. **A case is a JSON file; the set is a directory.** An accepted case
   holds the whole frozen bundle. A seeded-defect case holds no bundle:
   it names its accepted case and carries the edit, and its bundle is
   computed at load. Loading is pure and strict — a malformed file fails
   naming itself.
2. **The run calls the gate's own `judge`.** Nothing about the judgment
   is copied or re-implemented, so the eval cannot drift from the gate
   (spec R-5). What `judge` does not return — token counts, and how many
   findings the model reported before the quote check dropped some — the
   run reads from the provider's response by wrapping the roster's
   validator adapter in a recorder inside a registry of its own. **No
   line of the gate changes** (spec R-10).
3. **Scoring is a pure function** from (case, outcome) to a class,
   and the scorecard is counts of those. No model grades
   anything.
4. **Two fingerprints make results comparable.** The instructions'
   fingerprint is a hash of the request `build_request` produces for one
   fixed placeholder bundle, plus the tool schema — it moves when the
   wording, the layout of what is sent or the schema moves, and not with
   the data. The case set's fingerprint is a hash over every case file.
5. **The CLI is the only edge**: `freeze` (reads GitHub through the
   collector's existing `gh` seam), `run` (the one place a key is used)
   and `compare`.

### An edit is one or more exact replacements

The spec's R-2 calls a seeded defect "one named, exact edit to its diff
or its tests". A weakened test appears in a real pull request twice: in
the diff, and in the test file's source at the head. A seeded defect has
to change both or the case contradicts itself. So one edit is a short
list of replacements, each naming where it applies (`diff`, or a test
file's path), the exact text to find and the text to put there — and
each must match exactly once in its target (spec SC-2).

*Signed off by vpc, 2026-11-10, with the plan.*

### The classes

| Kind of case | Outcome | Class |
|---|---|---|
| accepted | PASS | `passed` |
| accepted | REJECT | `wrongly-rejected` |
| seeded defect | REJECT, a finding under the seeded checklist item | `caught` |
| seeded defect | REJECT, no finding under it | `other-reason` |
| seeded defect | PASS | `missed` |
| accepted | could not judge | `could-not-judge` (with its reason) |
| seeded defect | could not judge | `could-not-judge` (with its reason) |

Could-not-judge is counted per kind and never as right or wrong. With
more than one run per case, the counts are of judgments (case × run) and
the scorecard marks a case whose runs disagree as unstable.

## Components touched

- `src/agent_framework/evals/case.py` — **new.** `EvalCase`, the edit,
  bundle ⇄ JSON, `load_case`, `load_set`, the case set's fingerprint.
- `src/agent_framework/evals/scorecard.py` — **new.** The classes, the
  counts, the result record and its two fingerprints, the comparison,
  and the rendering of a scorecard as text.
- `src/agent_framework/evals/run.py` — **new.** The recorder around the
  validator's adapter; the loop over cases; could-not-judge on a
  provider error; the pause between judgments.
- `src/agent_framework/evals/freeze.py` — **new.** A merged pull request
  → an accepted case, through `collect_bundle` and the `gh` seam.
- `src/agent_framework/evals/__main__.py` — **new.** The CLI.
- `pyproject.toml` — one console entry point, `agent-framework-eval`.
- `evals/validator/cases/*.json` — **new.** The set.
- `evals/validator/results/*.json` — **new.** Recorded runs; the first
  is the baseline.
- `.gitattributes` — marks the case files as generated, so a review
  shows a frozen bundle collapsed and a seeded edit in full.
- `docs/glossary.md`, `docs/architecture.md`, `docs/adoption.md`.
- **Not touched:** anything under `validator/`, `providers/`, the
  roster, or `.github/workflows/`.

## Data model changes

Nothing stored outside the repository. Two file shapes.

An accepted case, `evals/validator/cases/pr-77.json`:

```json
{
  "id": "pr-77",
  "kind": "accepted",
  "expected": "pass",
  "reason": "Merged 2026-11-09; accepted by vpc.",
  "provenance": {"repo": "vpciii/agent-framework", "pr": 77,
                 "head": "<commit>", "frozen": "2026-11-10"},
  "bundle": {"task": {}, "diff": "…", "tests": {}, "ci": {},
             "red_evidence": null, "contract": {}}
}
```

A seeded-defect case, `evals/validator/cases/pr-77--tautology.json`:

```json
{
  "id": "pr-77--tautology",
  "kind": "seeded-defect",
  "base": "pr-77",
  "expected": "reject",
  "check": "test-honesty",
  "reason": "SC-2's test asserts a value against itself.",
  "edit": [
    {"in": "diff", "replace": "+    assert …", "with": "+    assert …"},
    {"in": "tests/validator/test_citations.py",
     "replace": "    assert …", "with": "    assert …"}
  ]
}
```

A result, `evals/validator/results/2026-11-10-gemini-3.8-flash.json`:

```json
{
  "model": "google:gemini-3.8-flash", "date": "2026-11-10", "runs": 1,
  "instructions": "<12 hex>", "case_set": "<12 hex>",
  "judgments": [
    {"case": "pr-77", "run": 1, "class": "passed", "outcome": "pass",
     "reason": null, "findings": [], "reported": 0, "dropped": 0,
     "input_tokens": 18185, "output_tokens": 6193}
  ],
  "scorecard": {"accepted": {"passed": 0, "wrongly-rejected": 0,
                             "could-not-judge": 0},
                "seeded": {"caught": 0, "other-reason": 0, "missed": 0,
                           "could-not-judge": 0},
                "dropped": 0, "input_tokens": 0, "output_tokens": 0}
}
```

Data sensitivity: the cases are this public repository's own merged
diffs, tests and spec text. Nothing personal; nothing secret.

## API changes

One new command, three subcommands. Nothing existing changes.

```
agent-framework-eval freeze <pr> [--repo OWNER/NAME] [--cases DIR]
    Writes <DIR>/pr-<n>.json. Refuses a pull request that is not merged,
    claims no criteria, or does not pass the deterministic stage — naming
    the check. Exit 0 written, 2 refused.

agent-framework-eval run [--cases DIR] [--roster FILE] [--runs N]
                         [--only ID ...] [--pause SECONDS] [--out FILE]
    Judges every case (or the named ones), prints the scorecard, writes
    the result file. Exit 0 when the run completed, whatever the score.

agent-framework-eval compare <result> <result>
    Prints the two scorecards and the cases whose class changed. When
    the case sets differ it says the results are not comparable, and
    exits 2.
```

`--cases` defaults to `evals/validator/cases`; `--roster` to
`agent-framework.toml`, so a different model is a different roster file
and never a code change (ADR 0001).

## Alternatives considered

- **Return the token counts and the dropped findings from `judge`** —
  simpler to read than a recorder. Rejected: it changes the gate's
  interface for the eval's benefit, against R-10, and the response
  already carries both.
- **Store a seeded-defect case as a second full bundle** — nothing to
  compute at load. Rejected: it doubles the data, and the defect — the
  one thing a reviewer must read — would be lost in 50,000 characters.
- **A directory per case** (`diff.patch`, the test files, metadata) —
  readable in review. Rejected: an accepted case is a frozen copy of a
  pull request that was already reviewed; its value is its provenance
  and that `freeze` reproduces it. One file per case keeps the loader
  small.
- **Store only a pull request number and collect at run time** — no data
  in the repository. Rejected: the eval would need GitHub and a token to
  run, and a case would change whenever the collector does, silently
  (spec goal 3).
- **Retry a rate-limited judgment** — fewer holes in a run. Rejected for
  now: `--pause` and `--only` cover it by hand, and the right retry
  policy depends on a limit nobody has measured.

## Risks

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| The free tier cannot serve a full run in one sitting | Medium | Low — the baseline takes two sittings, or a paid key | R-6 keeps the run going; `--pause` spaces the calls; `--only` re-runs the holes. Measured in T-6 |
| A seeded defect is too obvious, or too subtle, to tell models apart | Medium | Medium — a flattering or a useless score | Nine cases across three checklist items; each is a reviewed diff; R-8 lists every miss so a bad case shows itself |
| An accepted case holds a real defect, so a correct REJECT is scored wrong | Medium | Low | R-8 lists the findings; the case's expected answer is corrected in its own reviewed change |
| A collector change makes the frozen cases unlike what the gate sends today | Medium | Medium — the eval measures a past gate | Provenance lets `freeze` rebuild every case; the case set's fingerprint then changes, and results across the change are marked not comparable |
| The numbers are read as more than they are | Medium | Medium | The scorecard prints its case count beside every rate; the spec makes no significance claim and gates nothing |
| 770,000 characters of JSON slow the repository or its reviews | Low | Low | Under 1 MB; marked generated in `.gitattributes` |

## Rollout

Six PRs (tasks.md), all additive. T-1 to T-3 are the tooling, with no
model call anywhere in their tests. T-4 and T-5 are the cases. T-6 is
the delivery edge: the docs, and the first baseline — run by vpc with a
key and committed as a result file (spec R-12). Undo for any step is
reverting its PR.

## Observability

The run prints one line per judgment as it goes — case, class, tokens —
so a long run is visibly alive, then the scorecard. The gate's own log
lines (model, stop reason, each dropped finding) appear as they do for
the gate. The result file is the durable record.

## Test strategy

- **Unit, pure:** case round-trip and every malformed shape (SC-1); edit
  application, and absent and doubled text (SC-2); every class and the
  counts (SC-7); the wrong-case listing (SC-8); both fingerprints and
  the comparison (SC-9).
- **Integration, fake provider, no key:** the run over a small set in
  `tmp_path` — the request equals `build_request` for the case's bundle,
  each outcome is recorded, a provider error becomes could-not-judge and
  the run continues (SC-5, SC-6); the whole suite passes with every
  provider key unset, and the CI workflow names no eval command (SC-10).
- **Integration, faked `gh`:** `freeze` writes a case that loads (SC-4).
- **Over the committed set, no model:** every case loads and passes the
  deterministic stage (SC-3); the counts meet R-11 (SC-11).
- **Live, cited not asserted:** the baseline run (R-12), quoted in the
  delivery PR. No test in CI invokes a model.
