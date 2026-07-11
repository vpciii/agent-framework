# Tasks: Validator agent — the cite-the-test gate

- **Status:** Approved
- **Spec:** ./spec.md
- **Plan:** ./plan.md

PR-sized tasks derived from the approved plan. Each behavioural task traces to
≥1 success criterion — the tests it must make pass cite those ids. Mark a task
`[x]` with its merged PR number when done (Definition of Done). Each task also
updates its rows in the spec's Traceability table (replacing `*(pending)*` —
the coverage checker requires zero pending at `Implemented`, per #12).

**DAG:** T-1 → T-2 → T-3 → T-4.
(Strictly sequential: T-2 needs T-1's types; T-3 wires T-2's judgment into the
gate; T-4 is the edge over a finished core.)

**Criterion coverage:** SC-6 → T-1 · SC-4, SC-5 → T-2 · SC-1, SC-2, SC-3,
SC-7 → T-3 · T-4 is the delivery edge (collector + CLI) and closes out the
spec.

---

### [x] T-1 — Verdict + bundle types, JSON round-trip (#15)
- **Satisfies:** SC-6
- **Depends on:** —
- **Touches:** `src/agent_framework/validator/{__init__,bundle,verdict}.py`,
  `src/agent_framework/errors.py` (`ValidationError`, `JudgmentFormatError`),
  `tests/validator/test_verdict.py`
- **Brief:** The plan's data model as frozen dataclasses: `TaskRef`,
  `CIEvidence`, `EvidenceBundle`; `Citation`, `Finding`, `Pass`, `Reject`.
  `verdict_to_json` / `verdict_from_json`. `Pass` requires a citation per
  criterion at construction (the R-2-by-construction shape T-3 relies on).
- **Done when:** SC-6's test round-trips `Pass` and `Reject` through JSON to
  equal values, citing SC-6; `ruff` + `mypy --strict` clean.

### [x] T-2 — Judgment stage (prompt + `return_verdict` tool + dispatch) (#16)
- **Satisfies:** SC-4, SC-5
- **Depends on:** T-1
- **Touches:** `src/agent_framework/validator/judgment.py`,
  `tests/validator/test_judgment.py`
- **Brief:** Build the judgment `Request`: refutation-mindset checklist in
  the prompt (test honesty, scope creep, silently reworded criteria, one
  unstated edge case), bundle contents delimited as *data*; exactly one
  `ToolDef` — `return_verdict(defect_found, findings[])`. Invoke via
  `dispatch(roster, "validator", …)`; parse the `ToolCall` into `Finding`s;
  a response without the tool call raises `JudgmentFormatError`.
- **Done when:** SC-4 (fake provider returns a defect via `return_verdict` →
  findings carried verbatim) and SC-5 (the request goes through the roster's
  `validator` role in an isolated test registry; the prompt contains the
  checklist) pass, citing their ids; the no-tool-call path raises the typed
  error.

### [x] T-3 — Deterministic checks + the gate (this PR)
- **Satisfies:** SC-1, SC-2, SC-3, SC-7
- **Depends on:** T-2
- **Touches:** `src/agent_framework/validator/{checks,gate}.py`,
  `tests/validator/test_gate.py`
- **Brief:** `checks.py` (pure): every claimed `SC-` has ≥1 citing test in
  the bundle; CI green; fix-tasks carry red evidence. `gate.py`:
  `async validate(bundle, roster, *, registry=None)` — findings from checks
  → `Reject` **without dispatch**; otherwise run T-2's judgment; defect →
  `Reject`; clean → `Pass` built from the deterministic citations.
- **Done when:** SC-1 (clean bundle + no-defect judgment → `PASS` citing
  every criterion's test + CI), SC-2 (uncited criterion → deterministic
  REJECT naming it, fake provider proves **zero** invocations), SC-3 (red CI
  → same, citing CI), SC-7 (fix without red evidence → REJECT naming the
  missing evidence) pass, citing their ids.

### [ ] T-4 — Collector edge + CLI + spec close-out
- **Satisfies:** — (delivery edge; the core criteria are T-1–T-3's)
- **Depends on:** T-3
- **Touches:** `src/agent_framework/validator/{collector,__main__}.py`,
  `tests/validator/test_collector.py`, `docs/architecture.md` (new),
  `specs/validator-gate/{spec,tasks}.md` (bookkeeping)
- **Brief:** `collect_bundle(pr)` assembling an `EvidenceBundle` via `gh`
  (diff, checks) + git, subprocess calls isolated behind one fakeable seam;
  `python -m agent_framework.validator <pr>` → verdict JSON on stdout, exit
  0/1. Create `docs/architecture.md` (first real component beyond the
  substrate — record the system's current shape: roster → dispatch →
  adapters; validator core + edges; CI). Flip spec + plan to `Implemented`
  (checker then requires zero pending — the table must be complete).
- **Done when:** collector tests pass against faked subprocess output; a
  smoke run against a real merged PR of this repo produces a verdict (cited
  in the PR body, not asserted); architecture doc rides in the same PR;
  coverage check passes with the spec at `Implemented`.

---

## Criterion → task map

Which task delivers each criterion. The canonical `SC-` → **test** mapping
lives in `spec.md`'s Traceability table (single source, checked in CI);
this is only the planning view.

| Criterion | Requirement(s) | Task | Status |
|---|---|---|---|
| SC-1 | R-1, R-2, R-5 | T-3 | ✅ (this PR) |
| SC-2 | R-3, R-4 | T-3 | ✅ (this PR) |
| SC-3 | R-3, R-4 | T-3 | ✅ (this PR) |
| SC-4 | R-1, R-3, R-6 | T-2 | ✅ (#16) |
| SC-5 | R-5, R-6 | T-2 | ✅ (#16) |
| SC-6 | R-7 | T-1 | ✅ (#15) |
| SC-7 | R-8 | T-3 | ✅ (this PR) |
