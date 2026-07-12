# Plan: Project portability — run the team on any adopted repo

- **Status:** Approved
- **Date:** 2026-07-12
- **Author:** vpc
- **Spec:** ./spec.md
- **Related ADRs:** ADR 0001 (artifacts as substrate), ADR 0002 (harness
  language boundary), ADR 0004 (surfaces)

> This plan freezes with its spec: editable while `Draft` / `Under review` /
> `Approved`, a historical record once `Implemented`. A contradiction found
> later goes to a test, a new spec, or an ADR — not back into this file.

## Approach

One new value at the center, threaded through the existing seams:

1. **`ProjectConfig` (new `project.py`).** Frozen dataclass: `gate_commands:
   tuple[str, ...]`, `conventions_note: str`, `test_pattern: str` (a regex
   with exactly one capture group naming the test), `ignore_checks:
   tuple[str, ...]`. `DEFAULTS` reproduces today's behavior verbatim (the
   framework's own gate, the Python `def test_…` pattern, `("validator",)`).
   `load_project_config(root=Path("."))` reads the `[project]` table of
   **`agent-framework.toml`** at the target root — resolving the spec's
   open question: **one file to adopt**, carrying both `[roles]` (the
   roster) and `[project]`. Missing file or table → `DEFAULTS`; malformed
   values (bad TOML, a pattern that isn't one-capture-group) → typed
   `ProjectConfigError` naming the problem. A standalone roster file keeps
   working (`Roster.from_file` is unchanged and `--roster` still accepts
   any path).
2. **Config-driven brief.** `build_brief(task, project=DEFAULTS)`: the
   conventions section renders the gate as the configured command list plus
   the conventions note; the framework's toolchain names move out of the
   fixed text and into *this repo's own* `agent-framework.toml` (dogfood,
   R-2). `examples/roster.toml` is superseded by the root config file —
   one fact, one place; CLI `--roster` defaults change accordingly.
3. **Config-driven citation scan.** `checks.find_citations` /
   `_citing_test` take the compiled pattern (default unchanged);
   `validate()` and the validator CLI thread it from `load_project_config`.
   The CLI's `--ignore-check` flags *extend* the config's `ignore_checks`.
4. **Entry points.** `[project.scripts]`: **`agent-framework-worker`** and
   **`agent-framework-validate`** → the existing `main` functions (long
   names resolve the open question: unambiguous, uvx-friendly; alias
   locally if you like). `python -m` forms keep working.
5. **Adoption doc + pilot.** `docs/adoption.md`: the checklist from zero to
   gated worker PR — artifacts (per the methodology's `adopting.md`),
   `agent-framework.toml`, install (`uv add --dev <path-or-git>`), CI
   advisory job snippet + `GEMINI_API_KEY` secret, `.worktrees/` ignore.
   The pilot executes it on opn-mcp; target-side changes (config, CI job,
   secret, and a worker-sized mini-spec to dispatch) land as **opn-mcp
   PRs under its own methodology** — the doc says exactly what lands on
   which side (resolves the third open question).

## Components touched

- `src/agent_framework/project.py` — new (`ProjectConfig`, `DEFAULTS`,
  `load_project_config`).
- `src/agent_framework/errors.py` — `ProjectConfigError`.
- `src/agent_framework/worker/brief.py` — conventions rendered from config.
- `src/agent_framework/validator/checks.py` + `gate.py` — pattern threading.
- `src/agent_framework/{worker,validator}/__main__.py` — load config from
  cwd; entry-point functions.
- `pyproject.toml` — `[project.scripts]`.
- `agent-framework.toml` (new, repo root) — this repo's roster + project
  config; `examples/roster.toml` removed (fact moved, not copied).
- `docs/adoption.md` — new; `docs/architecture.md` — config row (same PR
  as the structural change).
- `tests/test_project_config.py`, updates to brief/gate/collector tests.

## Data model changes

```
ProjectConfig(gate_commands: tuple[str, ...],
              conventions_note: str,
              test_pattern: str,          # exactly one capture group
              ignore_checks: tuple[str, ...])
```

`agent-framework.toml` shape:

```toml
[roles]
worker    = { provider = "anthropic", model = "claude-sonnet-5" }
validator = { provider = "google",    model = "gemini-3.5-flash" }

[project]
gate_commands    = ["uv run pytest", "docker build -t opn-mcp-ci ."]
conventions_note = "Read CLAUDE.md; scheduled-task prompts are single-source (ADR 0008)."
test_pattern     = '^(?:async\\s+)?def\\s+(test_\\w+)'   # default shown
ignore_checks    = ["validator"]
```

## API changes

- `load_project_config(root: Path = Path(".")) -> ProjectConfig`
- `build_brief(task, project: ProjectConfig = DEFAULTS) -> str`
- `validate(bundle, roster, *, registry=None, project: ProjectConfig = DEFAULTS)`
- Console commands `agent-framework-worker` / `agent-framework-validate`.
- CLI `--roster` default: `agent-framework.toml` (falls back loudly if
  absent — no silent guessing).

## Alternatives considered

- **Config in the target's `pyproject.toml`** (`[tool.agent-framework]`) —
  idiomatic for Python targets, but the whole point is non-Python targets
  (ADR 0002); a language-neutral file wins.
- **Separate roster + project files** — rejected: two files to adopt and
  keep pointed at each other; one `agent-framework.toml` with two tables.
- **Short entry-point names (`af-*`)** — rejected: collision-prone and
  opaque; long names are self-documenting and alias-able.
- **Gate execution by the orchestrator** (run the commands itself before
  opening the PR) — explicitly out of scope in the spec; the session runs
  its gate, CI re-runs it deterministically.

## Risks

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| Roster's secret-field rejection trips on `[project]` content | Med | Low | Roster parsing scopes to `[roles]`; add a test with a config whose `[project]` mentions "key" innocently |
| Config regex is bad/pathological | Low | Low | Compiled + one-capture-group validated at load, loud `ProjectConfigError`; repo config is trusted content |
| opn-mcp pilot needs a dispatchable task (its specs are frozen) | High | Low | The pilot includes a verdict-rendering-sized mini-spec **in opn-mcp**, signed off under its methodology — the adoption doc documents this as the normal first-task path |
| Brief conventions drift from target reality | Med | Med | The config is in the target repo, reviewed by its own PRs; same-PR rule applies there |
| `--roster` default change breaks this repo's CI advisory job | Low | Med | This repo's `agent-framework.toml` lands in the same PR as the default change; CI proves it |

## Rollout

Additive + one visible default change (`--roster` path), all landing with
this repo's own config file so nothing breaks in the same commit. Fully
reversible. The pilot exercises the path on opn-mcp; nothing auto-adopts.

## Test strategy

Each SC ≥1 citing test; fakes at the existing seams; no live calls except
the pilot (cited, not asserted):

- **SC-1** config parse (all four fields), missing-file defaults equal
  `DEFAULTS`, malformed TOML / bad pattern → `ProjectConfigError` naming it.
- **SC-2** brief with custom gate contains exactly those commands + note,
  sentinel-proof none of the framework's toolchain names appear; no-config
  brief equals today's.
- **SC-3** custom pattern (non-Python-shaped fixture) → citation found and
  cited per the pattern; default path: existing gate/checks tests unchanged.
- **SC-4** `[project.scripts]` maps the documented names to the `main`
  callables (packaging metadata assertion) + behavioral call through the
  imported entry-point functions.
- **SC-5** the delivery PR cites the opn-mcp pilot: worker PR URL +
  advisory verdict from opn-mcp's CI (R-6, live evidence).
