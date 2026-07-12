# Tasks: Project portability — run the team on any adopted repo

- **Status:** Approved
- **Spec:** ./spec.md
- **Plan:** ./plan.md

PR-sized tasks derived from the approved plan. Each behavioural task traces
to ≥1 success criterion — the tests it must make pass cite those ids. Task
PRs carry a `Satisfies:` declaration and replace their `*(pending)*`
Traceability rows.

**DAG:** T-1 → { T-2 ∥ T-3 } → T-5; **T-4 independent** (touches only
packaging — dispatchable immediately, in parallel with everything).

**Dispatch note:** T-4 is deliberately worker-shaped (small, self-contained,
zero cross-cutting context) — the first framework-backlog task to go to the
worker agent instead of an interactive session. The rest stay interactive
this round (T-2/T-3 rework the brief and gate the worker itself depends on).

**Criterion coverage:** SC-1 → T-1 · SC-2 → T-2 · SC-3 → T-3 · SC-4 → T-4 ·
SC-5 → T-5 (delivery + pilot).

---

### [x] T-1 — ProjectConfig + loader (this PR)
- **Satisfies:** SC-1
- **Depends on:** —
- **Touches:** `src/agent_framework/project.py` (new),
  `src/agent_framework/errors.py` (`ProjectConfigError`),
  `tests/test_project_config.py`
- **Brief:** The plan's `ProjectConfig` frozen dataclass (`gate_commands`,
  `conventions_note`, `test_pattern`, `ignore_checks`) and `DEFAULTS`
  reproducing today's behavior verbatim. `load_project_config(root)` reads
  `agent-framework.toml`'s `[project]` table: missing file/table →
  `DEFAULTS`; bad TOML, wrong types, or a `test_pattern` without exactly
  one capture group → `ProjectConfigError` naming the problem.
- **Done when:** SC-1's tests pass citing it (full parse; defaults on
  missing; loud on malformed, each message naming the offending field).

### [ ] T-2 — Config-driven brief + this repo's own config
- **Satisfies:** SC-2
- **Depends on:** T-1
- **Touches:** `src/agent_framework/worker/brief.py`,
  `src/agent_framework/worker/orchestrator.py` + `__main__.py` (thread
  config), `agent-framework.toml` (new, repo root),
  `examples/roster.toml` (removed), `.github/workflows/ci.yml` (roster
  default), `src/agent_framework/validator/__main__.py` (`--roster`
  default), `tests/worker/test_brief.py`
- **Brief:** `build_brief(task, project=DEFAULTS)` renders the gate as the
  configured command list + conventions note; no framework toolchain names
  in fixed text. This repo's `agent-framework.toml` lands here ([roles]
  from examples/roster.toml + [project] with our real gate), examples file
  removed, `--roster` defaults updated — same PR so CI proves nothing
  breaks (plan risk row). Roster loading must not trip its secret-field
  rejection on `[project]` content (regression test with an innocent
  "key" mention).
- **Done when:** SC-2's tests pass citing it (custom gate → exactly those
  commands + note, sentinel-proof no framework toolchain names; no config
  → today's brief); the repo's own advisory CI job still runs green.

### [ ] T-3 — Config-driven citation scan
- **Satisfies:** SC-3
- **Depends on:** T-1 (parallel with T-2)
- **Touches:** `src/agent_framework/validator/{checks,gate}.py`,
  `src/agent_framework/validator/__main__.py` (load config; CLI
  `--ignore-check` extends config), `tests/validator/test_gate.py` or new
  `tests/validator/test_checks_pattern.py`
- **Brief:** `find_citations`/`_citing_test` take the compiled pattern
  (default unchanged); `validate(..., project=DEFAULTS)` threads it; the
  validator CLI loads the target's config from cwd and merges
  `ignore_checks`.
- **Done when:** SC-3's tests pass citing it (a non-Python-shaped fixture
  pattern finds and cites per the pattern; all existing default-path tests
  unchanged and green).

### [ ] T-4 — Console entry points  *(worker-dispatch candidate)*
- **Satisfies:** SC-4
- **Depends on:** — (parallel with all; merge before T-5)
- **Touches:** `pyproject.toml` (`[project.scripts]`),
  `tests/test_entry_points.py` (new)
- **Brief:** `agent-framework-worker` → `agent_framework.worker.__main__:main`
  and `agent-framework-validate` → `agent_framework.validator.__main__:main`
  under `[project.scripts]`. Do not modify the `main` functions or any
  other file. Tests: packaging metadata maps the documented names to those
  callables, and the imported entry-point callables behave as the `python
  -m` forms (e.g. `--help` exits 0).
- **Done when:** SC-4's tests pass citing it; `uv sync` installs both
  commands; `ruff` + `mypy --strict` clean.

### [ ] T-5 — Adoption doc + opn-mcp pilot + spec close-out
- **Satisfies:** SC-5 (R-5, R-6)
- **Depends on:** T-2, T-3, T-4
- **Touches:** `docs/adoption.md` (new), `docs/architecture.md` (config
  row), `specs/project-portability/{spec,tasks}.md` (bookkeeping); plus
  **opn-mcp-side PRs** (its `agent-framework.toml`, CI advisory job +
  `GEMINI_API_KEY` secret, `.worktrees/` ignore, and a worker-sized
  mini-spec to dispatch) reviewed under opn-mcp's own methodology.
- **Brief:** Write the adoption checklist (framework-side vs target-side
  split per the plan); execute it on opn-mcp for real; dispatch the
  mini-spec's task to a worker session there; the resulting opn-mcp PR
  faces opn-mcp's advisory validator; the human merges. Flip spec + plan
  to `Implemented`.
- **Done when:** the pilot's worker PR URL + advisory verdict are cited
  (not asserted) in this task's PR body; the adoption doc covers every
  step the pilot actually required (drift found while piloting goes into
  the doc, same PR); coverage check green at `Implemented`.

---

## Criterion → task map

| Criterion | Requirement(s) | Task | Status |
|---|---|---|---|
| SC-1 | R-1 | T-1 | ✅ (this PR) |
| SC-2 | R-1, R-2 | T-2 | pending |
| SC-3 | R-1, R-3 | T-3 | pending |
| SC-4 | R-4 | T-4 | pending |
| SC-5 | R-5, R-6 | T-5 | pending |
