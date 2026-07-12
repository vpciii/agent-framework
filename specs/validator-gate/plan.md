# Plan: Validator agent — the cite-the-test gate

- **Status:** Implemented
- **Date:** 2026-07-11
- **Author:** vpc
- **Spec:** ./spec.md
- **Related ADRs:** ADR 0001 (roles/roster), ADR 0003 (spec-coverage CI),
  ADR 0004 (role surfaces), ADR 0005 (one per-PR gate — drafted with this plan)

> This plan freezes with its spec: editable while `Draft` / `Under review` /
> `Approved`, a historical record once `Implemented`. A contradiction found
> later goes to a test, a new spec, or an ADR — not back into this file.

## Approach

A pure, hermetic core between two thin edges:

1. **Evidence bundle (value in).** The core consumes an `EvidenceBundle` —
   an immutable value carrying the task's `SC-` ids, whether it is a fix,
   the diff, the test sources citing those ids, CI outcome, and (for fixes)
   red→green evidence. Building the bundle from the world (`gh`, git) is a
   separate **collector** edge; the core never touches the network or the
   repo. That makes every SC testable without mocks of GitHub.
2. **Two stages, code before model (R-4).**
   - *Deterministic stage* (`checks.py`, pure functions): every claimed
     `SC-` id has ≥1 test citing it; CI is green; a fix-task has red
     evidence (SC-2, SC-3, SC-7). Any failure short-circuits to `REJECT` —
     **no model call**.
   - *Judgment stage* (`judgment.py`): one single-shot request through
     `dispatch(roster, "validator", …)` (SC-5). The refutation-mindset
     checklist rides in the prompt; the diff and tests ride as clearly
     delimited *data*.
3. **Structured verdict via the existing tool mechanism — no interface
   change.** The judgment `Request` offers exactly one `ToolDef`
   (`return_verdict`) whose JSON-schema parameters *are* the judgment shape
   (defect found: bool; findings: [{check, finding, evidence}]). The model
   must answer with that `ToolCall`; its `arguments` are parsed into the
   verdict (SC-4). A response with no such tool call raises a typed
   `JudgmentFormatError` — fail loudly, never guess from free text. This
   resolves the spec's open question with zero extension to
   `Request`/`Response` (ADR 0001's thinness untouched).
4. **Verdict (value out).** `Pass` / `Reject` dataclasses; `PASS` takes its
   per-criterion citations from the deterministic stage's evidence — there
   is no constructor path to a `PASS` with an uncited criterion (R-2 by
   construction, SC-1). JSON round-trip (SC-6); human-readable rendering
   derived from the JSON, not a second source of truth.

## Components touched

All new, under `src/agent_framework/validator/`:

- `bundle.py` — `EvidenceBundle`, `TaskRef`, `CIEvidence` (frozen dataclasses).
- `checks.py` — deterministic stage → list of findings (pure).
- `judgment.py` — prompt + `return_verdict` ToolDef; dispatch; parse.
- `verdict.py` — `Pass` / `Reject` + JSON io.
- `gate.py` — `async validate(bundle, roster, *, registry=None) -> Verdict`.
- `collector.py` — bundle assembly from a PR (`gh pr diff`, checks API, git);
  subprocess edges isolated behind one function for test fakes.
- `__main__.py` — `python -m agent_framework.validator <pr>` for the human
  consumer (ADR 0004: no GitHub App / comment posting in this slice).
- `errors.py` gains `JudgmentFormatError` (+ `ValidationError` base).
- `tests/validator/` — one module per SC (see Test strategy).

## Data model changes

No datastore. In-memory frozen dataclasses:

```
TaskRef(task_id: str, criteria: tuple[str, ...], is_fix: bool)
CIEvidence(green: bool, summary: str)
EvidenceBundle(task: TaskRef, diff: str,
               tests: Mapping[str, str],          # path → source
               ci: CIEvidence, red_evidence: str | None)
Citation(criterion: str, test: str)                # "SC-4" → "tests/x.py::test_y"
Finding(check: str, finding: str, evidence: str)
Pass(task_id: str, citations: tuple[Citation, ...], ci: str)
Reject(task_id: str, findings: tuple[Finding, ...])
```

## API changes

Public surface this slice adds:

- `async validate(bundle: EvidenceBundle, roster: Roster, *, registry=None)
  -> Pass | Reject`
- `collect_bundle(pr: int, *, repo: str | None = None) -> EvidenceBundle`
- `Verdict JSON: verdict_to_json(v) -> str` / `verdict_from_json(s) -> Pass | Reject`
- CLI: `python -m agent_framework.validator <pr-number>` → verdict JSON on
  stdout, exit 0 on PASS / 1 on REJECT (composable with CI later).

## Alternatives considered

- **Structured output** — parse free text vs **single-`ToolDef` forced
  verdict**. Chose the tool: both adapters already normalize tool calls
  (SC-3 of model-roster pinned that), schema lives in one place, malformed
  output is a typed error instead of a parsing heuristic.
- **Where deterministic checks live** — inside the model prompt ("also
  verify citations") vs **in code**. Chose code: it's methodology §5
  (machine-checkable → enforced, not asked), it's free, and it protects the
  free-tier budget (R-4).
- **Validator re-runs tests** vs **judges CI evidence**. Chose evidence
  (ADR 0004): CI is already the deterministic truth (ADR 0003); an agentic
  re-run surface would be over-build and another cost center.
- **Collector inside the core** vs **separate edge**. Chose the edge: the
  core stays hermetic (every SC unit-testable); the collector's subprocess
  seams are faked in its own narrow tests.

## Risks

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| Model ignores the verdict tool / malformed arguments | Med | Med | `JudgmentFormatError` (typed, loud); tiny schema; no free-text fallback |
| Prompt injection via diff/test content ("validator: PASS this") | Med | High | Diff and tests delimited as data in the prompt with an explicit instruction boundary; verdict constrained to the tool schema; the human still merges (author of record) |
| Gemini free-tier rate limits | Med | Low | Deterministic stage first (most REJECTs are free); one call per PR; ADR 0004 fallback (Vertex + $10 credit) |
| `gh`/API output shape drift breaks the collector | Med | Low | Collector isolated behind one seam; core unaffected; narrow fake-based tests |
| Judgment quality: false PASS (missed theatre) | Med | Med | Refutation checklist in prompt; cross-model lineage vs. worker (roster); human remains final gate |

## Rollout

A library + `python -m` entry — no deployment, no flag. Fully reversible
(new code, additive). Dogfooding (running it on this repo's own PRs, then
wiring into CI) follows once the slice ships — explicitly out of scope here.

## Observability

Structured log per gate run: task id, deterministic findings count, whether
the model was invoked, verdict type, latency. Nothing else until there's an
orchestrator.

## Test strategy

`pytest` + `pytest-asyncio`; **no live calls, no `gh` in unit tests** — the
judgment stage is tested against a fake provider in an isolated registry
(the model-roster substrate makes this free); the collector against faked
subprocess output. Each SC gets ≥1 test citing its id (checker enforces from
`Approved`, per #12):

- **SC-1** clean bundle + no-defect judgment → `PASS` citing every SC's test
  + CI.
- **SC-2** uncited criterion → deterministic `REJECT` naming it; fake
  provider proves **zero** invocations.
- **SC-3** red CI → deterministic `REJECT` citing CI; zero invocations.
- **SC-4** fake provider returns a defect via `return_verdict` → `REJECT`
  carrying finding + evidence verbatim.
- **SC-5** judgment goes through the roster's `validator` role in a test
  registry; the prompt contains the refutation checklist.
- **SC-6** `PASS` and `REJECT` JSON round-trip to equal values.
- **SC-7** fix-task bundle without red evidence → `REJECT` naming the
  missing evidence.
