# Tasks: Verdict rendering

- **Status:** Approved
- **Spec:** ./spec.md
- **Plan:** — (single-function slice; the spec's Requirements are the plan)

One task. This is the worker agent's first dispatched task (the
worker-agent T-5 smoke run): PR-sized by construction, criteria-traced,
self-contained.

---

### [ ] T-1 — Render verdicts to markdown
- **Satisfies:** SC-1
- **Depends on:** —
- **Touches:** `src/agent_framework/validator/render.py` (new),
  `tests/validator/test_render.py` (new), `specs/verdict-rendering/spec.md`
  (Traceability row)
- **Brief:** Add `render_verdict(verdict: Pass | Reject) -> str` in a new
  `src/agent_framework/validator/render.py`. Input types come from
  `agent_framework.validator.verdict` (`Pass`, `Reject`, `Citation`,
  `Finding`) — import them; do not modify them or any existing file except
  the spec's Traceability row. A `Pass` renders as markdown with a
  `PASS — <task_id>` heading, one line per citation (`SC-n` and its
  `path::test`), and the CI evidence. A `Reject` renders with a
  `REJECT — <task_id>` heading and, per finding, its check, finding, and
  evidence. Pure function: no I/O, no printing, no new dependencies.
  Follow repo style: `ruff` and `mypy --strict` clean, frozen values in,
  string out. Update the spec's Traceability table: replace `*(pending)*`
  in the SC-1 row with your citing tests (full `path::test_name`, no
  shorthand).
- **Done when:** tests in `tests/validator/test_render.py` citing SC-1
  pass — a rendered `Pass` contains the task id, every criterion with its
  cited test, and the CI evidence; a rendered `Reject` contains the task
  id and every finding's three fields; `ruff` + `mypy --strict` clean.

---

## Criterion → task map

| Criterion | Requirement(s) | Task | Status |
|---|---|---|---|
| SC-1 | R-1, R-2 | T-1 | pending |
