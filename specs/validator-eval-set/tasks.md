# Tasks: An eval set for the validator's judgment

- **Status:** Done
- **Spec:** ./spec.md
- **Plan:** ./plan.md

PR-sized tasks derived from the plan. Each behavioural task traces to ≥1
success criterion — the tests it must make pass cite those ids — and
replaces its `*(pending)*` Traceability rows as its tests land. Mark a task
`[x]` with its merged PR number when done. Task PRs carry a `Satisfies:`
declaration and name `specs/validator-eval-set/` in their body.

**DAG:** T-1 → T-2 → T-3; T-1 → T-4 → T-5; T-6 after T-3 and T-5. T-2 and
T-4 touch different files and can proceed in parallel once T-1 merges.

**Criterion coverage:** SC-1, SC-2 → T-1 · SC-7, SC-8, SC-9 → T-2 ·
SC-5, SC-6, SC-10 → T-3 · SC-3, SC-4 → T-4 · SC-11 → T-5 · T-6 is the
delivery edge and closes out the spec.

**Dispatch.** T-1 and T-2 are pure code with no network and are
candidates for a worker session. T-4 needs GitHub, T-5 is a human's
judgment about what a defect is, and T-6 needs a provider key — none of
those is for dispatch.

---

### [x] T-1 — Eval cases: the file format, the loader, seeded edits (#87)
- **Satisfies:** SC-1, SC-2
- **Depends on:** —
- **Touches:** `src/agent_framework/evals/__init__.py` (new),
  `src/agent_framework/evals/case.py` (new),
  `tests/evals/__init__.py` (new), `tests/evals/test_case.py` (new),
  `docs/glossary.md`,
  `specs/validator-eval-set/spec.md` (Traceability rows SC-1, SC-2)
- **Brief:** `case.py` defines `EvalCase` (id, kind, expected outcome,
  checklist item, reason, provenance, bundle) and the two file shapes in
  `plan.md` (Data model changes). `dump_case` / `load_case` turn an
  accepted case into JSON and back to an equal `EvidenceBundle`.
  `load_set(directory)` loads every case, resolving each seeded-defect
  case's `base` to its accepted case and applying its edit: a list of
  replacements, each naming `diff` or a test file's path, the exact text
  to find and the text to put there; each must match exactly once in its
  target. `set_fingerprint(directory)` is a short hash over every case
  file's name and bytes. Every malformed shape raises one typed error
  naming the file: a missing field, an unknown kind, a `reject` with no
  checklist item or one outside the judgment's four names, a `base` that
  is not an accepted case in the set, an edit that matches zero times or
  twice. Pure: no network, no model. Add the spec's three glossary terms
  to `docs/glossary.md` as the spec words them.
- **Done when:** SC-1 and SC-2's tests pass citing them: a bundle with a
  contract, two test files and red evidence round-trips to an equal
  bundle; each malformed shape fails naming the file; a seeded-defect
  case's bundle differs from its base by exactly its edit, in the diff
  and in the test file; absent and doubled edit text each fail to load;
  the fingerprint changes when a case is added, removed or edited and is
  stable otherwise.

### [x] T-2 — Scoring: the classes, the scorecard, a comparable result (#88)
- **Satisfies:** SC-7, SC-8, SC-9
- **Depends on:** T-1
- **Touches:** `src/agent_framework/evals/scorecard.py` (new),
  `tests/evals/test_scorecard.py` (new),
  `specs/validator-eval-set/spec.md` (Traceability rows)
- **Brief:** Pure functions, no model and no I/O beyond reading a result
  file. `classify(case, outcome)` returns the class per the table in
  `plan.md` (The classes), where an outcome is a pass, a reject with its
  findings, or could-not-judge with its reason. `scorecard(judgments)`
  counts classes per kind of case, sums dropped findings and tokens, and
  marks a case whose runs disagree as unstable. A result record carries
  the model, the date (passed in, never read from the clock inside),
  the number of runs, both fingerprints, every judgment and the
  scorecard, and round-trips through JSON as `plan.md` shows.
  `instructions_fingerprint()` hashes the request `build_request` makes
  for one fixed placeholder bundle together with the tool's schema.
  `render(result)` gives the scorecard as text, with the case count
  beside every rate and, listed in full with the model's findings, every
  wrongly-rejected, missed and other-reason case. `compare(a, b)` gives
  the cases whose class changed, and says the results are not comparable
  when their case-set fingerprints differ.
- **Done when:** SC-7, SC-8 and SC-9's tests pass citing them: one of
  each outcome for each kind of case yields the right counts; a seeded
  defect rejected under another checklist item is `other-reason`, not
  `caught`; could-not-judge is in neither the right nor the wrong count;
  the rendering lists each wrong case with its findings; the
  instructions' fingerprint changes when `build_request`'s wording or
  the tool schema is changed (monkeypatched) and not when the bundle
  is; comparing results with different case sets says so.

### [x] T-3 — The run, and the command (#89)
- **Satisfies:** SC-5, SC-6, SC-10
- **Depends on:** T-2
- **Touches:** `src/agent_framework/evals/run.py` (new),
  `src/agent_framework/evals/__main__.py` (new), `pyproject.toml`,
  `tests/evals/test_run.py` (new), `tests/evals/test_cli.py` (new),
  `tests/test_ci_workflow.py`,
  `specs/validator-eval-set/spec.md` (Traceability rows)
- **Brief:** `run.py` judges each case by calling the gate's own
  `judge(bundle, roster, registry=…)` with a registry of its own in
  which the roster's validator adapter is wrapped by a recorder; from
  the recorded response it takes the token counts and how many findings
  the model reported (dropped = reported − supported). A
  `JudgmentFormatError` or `ProviderError` is that case's
  could-not-judge with its reason, and the loop goes on. `--runs`,
  `--only` and `--pause` as `plan.md` describes; the sleep is injected.
  `__main__.py` is the CLI with `run` and `compare` (`freeze` is T-4);
  it registers the adapters as the gate's CLI does, prints one line per
  judgment and then the rendered scorecard, and writes the result file.
  Add the `agent-framework-eval` entry point. Change nothing under
  `validator/` or `providers/`.
- **Done when:** SC-5, SC-6 and SC-10's tests pass citing them: with a
  fake provider, the request sent for each case equals `build_request`
  for that case's bundle and goes through the roster's validator role;
  a pass, a reject and each could-not-judge reason are recorded as
  such; a provider error on the second of three cases leaves the first
  and third judged; the eval's tests pass with `GEMINI_API_KEY` and
  `ANTHROPIC_API_KEY` unset; and no job in `.github/workflows/` runs the
  eval.

### [x] T-4 — Freeze a merged pull request; the accepted cases (#90, #92)
- **Satisfies:** SC-3, SC-4
- **Depends on:** T-1
- **Touches:** `src/agent_framework/evals/freeze.py` (new),
  `src/agent_framework/evals/__main__.py`,
  `tests/evals/test_freeze.py` (new), `tests/evals/test_set.py` (new),
  `evals/validator/cases/pr-*.json` (new), `.gitattributes` (new),
  `specs/validator-eval-set/spec.md` (Traceability rows)
- **Brief:** `freeze(pr, …)` collects the bundle through
  `collect_bundle` and the `gh` seam with the project's config, reads
  the pull request's state and head commit, and writes an accepted case.
  It refuses — writing nothing — a pull request that is not merged,
  claims no criteria, or whose bundle the deterministic stage rejects,
  naming the check. Add the `freeze` subcommand. Then freeze every
  merged task pull request in this repository that qualifies (18 on
  2026-11-10; #77 among them) into `evals/validator/cases/`, and mark
  that directory generated in `.gitattributes`. If a case file is
  written by a PR that also changes `freeze`, split the data into its
  own PR.
- **Done when:** SC-3 and SC-4's tests pass citing them: with a faked
  `gh`, `freeze` writes a file that `load_case` reads back as the
  collected bundle, and refuses an open pull request and one the
  deterministic stage rejects; every case under
  `evals/validator/cases/` loads and passes `run_checks`, the test
  naming the case and the check when one does not.

### [x] T-5 — The seeded-defect cases (#93)
- **Satisfies:** SC-11
- **Depends on:** T-4
- **Touches:** `evals/validator/cases/*--*.json` (new),
  `tests/evals/test_set.py`,
  `specs/validator-eval-set/spec.md` (Traceability row SC-11)
- **Brief:** At least nine seeded-defect cases over the accepted ones,
  at least three per checklist item: **test honesty** (an assertion made
  a tautology, an assertion on the mock instead of the result, a test
  body emptied of its checks — the citation left intact so the
  deterministic stage still passes); **spec conformance** (a hunk added
  that the task did not ask for); **criteria integrity** (a hunk that
  rewords or weakens the claimed criterion in `spec.md`). Each is one
  edit of a few lines, its `reason` saying in a sentence what was
  planted. Spread them over different accepted cases, small and large.
- **Done when:** SC-11's test passes citing it — at least 12 accepted
  cases including `pr-77`, at least 9 seeded-defect cases, at least 3
  for each of the three checklist items — and T-4's test over the set
  still passes with the new cases in it.

### [x] T-6 — Delivery: docs and the first baseline (#95)
- **Satisfies:** —
- **Depends on:** T-3, T-5
- **Touches:** `docs/architecture.md`, `docs/adoption.md`,
  `evals/validator/results/*.json` (new),
  `specs/validator-eval-set/{spec,tasks}.md`
- **Brief:** In `docs/architecture.md`: the new package in the component
  table; under Trust boundaries, that the eval sends the cases to the
  validator's provider from a human's shell and never from CI; and the
  rule in spec R-13 — a change to the judgment's instructions, its tool
  schema, what it is sent or the validator's model cites a run from
  before and after. In `docs/adoption.md`: how to run the eval, and how
  a project builds its own set with `freeze`. vpc runs the full set once
  with a key; the result file is committed as the baseline and its
  scorecard quoted in the PR (R-12), with what the free tier allowed.
  Confirm the Traceability table has no pending row. Marking the spec
  `Implemented` is the human's sign-off, in its own PR.
- **Done when:** the docs name the command and the rule; the baseline
  result file is in the repository and loads; the PR quotes its
  scorecard; spec coverage passes with zero pending rows.
