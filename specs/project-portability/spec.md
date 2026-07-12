# Spec: Project portability — run the team on any adopted repo

- **Status:** Implemented
- **Date:** 2026-07-12
- **Author:** vpc
- **Related ADRs:** ADR 0001 (artifacts are the model-neutral coordination
  substrate), ADR 0002 (Python is the harness's language, not the
  target's), ADR 0004 (role surfaces)
- **Pilot:** `opn-mcp` (`~/Developer/personal/opn-mcp`, vpciii/opn-mcp) —
  already methodology-native; the pilot measures the framework's
  portability, not the project's readiness.

> This spec is editable while `Draft` / `Under review` / `Approved`.
> When it reaches `Implemented` it **freezes** into a historical record.

## Problem

The framework exists to orchestrate work on *other* projects, but three
places quietly assume "this repo," discovered by surveying the pilot:

1. **The brief hardcodes this repo's gate** (`ruff`, `mypy --strict`,
   `pytest`, spec-coverage). opn-mcp's gate is `pytest` + spec-coverage +
   a Docker build, with no ruff and no mypy — a worker dispatched there
   today would be instructed to run tools that don't exist and skip the
   check that matters.
2. **The citation scan assumes Python** (`def test_…` spans). Fine for the
   pilot; wrong for any non-Python target — and ADR 0002 explicitly says
   Python is the harness's language, not the target's.
3. **Installation is path-coupled**: no console entry points, no
   documented adoption path; `python -m` from a venv that happens to have
   the framework importable.

(The survey also found a CI-evidence bug — SKIPPED/NEUTRAL conclusions
blocking green — fixed separately with a regression test in #33; not part
of this spec.)

## Goals

1. **Per-project configuration**: the gate commands/conventions a worker
   must satisfy, the test-citation pattern, and check-name settings live
   in a small declarative file in the *target* repo — the framework ships
   defaults matching its own conventions, so absent config means today's
   behavior.
2. **Config-driven briefs**: `build_brief` renders the target project's
   gate, never a hardcoded toolchain.
3. **Installable tooling**: console entry points, so an adopted repo runs
   the worker and validator as commands after installing the package.
4. **A documented, tested adoption path**: a checklist an adopted repo
   follows, kept honest by actually running the pilot.

## Non-goals

- Publishing to PyPI (a local/git dependency is fine for now; release
  engineering is its own later decision).
- Multi-repo orchestration from one seat (a chief concern, later).
- Porting the *checker script* per project — that is already each
  project's own adapted copy by design (ADR 0017 / project ADR 0003).
- Windows support.
- Changing verdict/brief/escalation semantics — only where their inputs
  come from.

## Requirements

Use RFC 2119 keywords. Every `MUST` is reflected in a success criterion.

- **R-1 (MUST)** The framework reads an optional per-project config file
  from the target repo root declaring at least: the ordered **gate
  commands** (what the worker must run green before committing), a
  **conventions note** (free text appended to the brief's conventions),
  the **test-citation pattern** (regex locating a citing test and naming
  it), and the **check names** the in-CI advisory run must ignore.
  A missing file yields the framework's own documented defaults
  (current behavior); a malformed file fails loudly.
- **R-2 (MUST)** The brief's gate/conventions text is rendered from that
  config — the framework's toolchain names appear nowhere in
  `build_brief`'s fixed text; this repo itself migrates to a config file
  (dogfood: a fact lives in one place).
- **R-3 (MUST)** The deterministic citation check uses the configured
  pattern; with no config it behaves exactly as today (Python
  `def test_…` spans).
- **R-4 (MUST)** The package installs **console entry points** for the
  worker and validator CLIs, functionally identical to the `python -m`
  forms (which keep working).
- **R-5 (MUST)** An adoption document in this repo walks a target repo
  from zero to gated-worker-PR: artifact conventions (per the
  methodology's `adopting.md`), config file, roster, CI advisory job +
  secret, install. Same-PR honesty: it ships with the code it describes.
- **R-6 (SHOULD)** The pilot: one real task dispatched in `opn-mcp`
  end-to-end — worker PR with its declaration, advisory verdict in
  opn-mcp's CI, human merge — cited (not asserted) in the delivery PR.

## Success criteria

Each has a stable id and is verified by ≥1 test that cites it; together
they cover every `MUST`. R-6's evidence is the cited pilot run (a live
outcome, not a unit test).

- **SC-1** — Config loading: a target-root config declaring gate commands,
  a conventions note, a citation pattern, and ignore-checks parses into
  the framework's project-config value; a missing file yields the
  documented defaults; a malformed file raises a typed error naming the
  problem. (R-1)
- **SC-2** — Config-driven brief: with a config declaring a custom gate
  (e.g. `uv run pytest` + `docker build`), the brief contains exactly
  those commands and the conventions note, and contains none of the
  framework's own toolchain names; with no config, the brief matches
  today's defaults. (R-1, R-2)
- **SC-3** — Configurable citation scan: with a custom test-citation
  pattern, the deterministic check finds (and cites) tests per that
  pattern; with no config, existing citation tests pass unchanged.
  (R-1, R-3)
- **SC-4** — Entry points: the installed console commands invoke the same
  `main` functions as the `python -m` forms (verified at the packaging
  metadata level plus a behavioral test through the entry-point
  callables). (R-4)
- **SC-5** — The adoption doc exists, covers every step the pilot actually
  required, and the delivery PR cites the pilot run: an opn-mcp worker PR
  URL + its advisory verdict. (R-5, R-6)

## Open questions

Resolved before the spec is `Approved` (inline or via an ADR).

- [x] **Config file name/format** — resolved in `plan.md`: one
  `agent-framework.toml` at the target root carrying `[roles]` + `[project]`
  (one file to adopt); standalone roster paths still honored via `--roster`.
- [x] **Entry-point names** — resolved in `plan.md`:
  `agent-framework-worker` / `agent-framework-validate` (unambiguous,
  alias-able).
- [x] **Where the pilot's opn-mcp changes land** — resolved in `plan.md`:
  config/CI job/secret/mini-spec are opn-mcp PRs under its own methodology;
  the adoption doc enumerates the target-side vs framework-side split.

## Out of scope (for now)

- Gate-command *execution* by the orchestrator (the worker session runs
  the gate; the framework only tells it what the gate is).
- Language-aware anything beyond the citation pattern.
- Auto-generating the CI advisory job in target repos.

## Traceability

Built up during implementation; complete before the spec is `Implemented`.
Rows may be `*(pending)*` while `Approved` (#12).

| Criterion | Requirement(s) | Verified by (test) |
|---|---|---|
| SC-1 | R-1 | `tests/test_project_config.py::test_sc1_full_config_parses_all_four_fields`, `tests/test_project_config.py::test_sc1_missing_file_and_missing_table_yield_defaults`, `tests/test_project_config.py::test_sc1_malformed_config_fails_loudly_naming_the_problem` |
| SC-2 | R-1, R-2 | `tests/worker/test_brief.py::test_sc2_brief_renders_the_configured_gate_not_the_framework_one`, `tests/worker/test_brief.py::test_sc2_default_brief_carries_the_framework_gate` |
| SC-3 | R-1, R-3 | `tests/validator/test_checks_pattern.py::test_sc3_custom_pattern_finds_and_cites_non_python_tests`, `tests/validator/test_checks_pattern.py::test_sc3_gate_threads_the_project_pattern_end_to_end` |
| SC-4 | R-4 | `tests/test_entry_points.py::test_sc4_entry_points_declared_in_packaging_metadata`, `tests/test_entry_points.py::test_sc4_worker_entry_point_loads_the_same_main_as_python_dash_m` |
| SC-5 | R-5, R-6 | `tests/test_adoption_doc.py::test_sc5_adoption_doc_covers_every_pilot_required_step` (R-6's half is the cited live pilot: opn-mcp#21) |
