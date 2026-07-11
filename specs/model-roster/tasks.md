# Tasks: Model roster and provider abstraction

- **Status:** Approved
- **Spec:** ./spec.md
- **Plan:** ./plan.md

PR-sized tasks derived from the approved plan. Each behavioural task traces to
≥1 success criterion — the tests it must make pass cite those ids. Mark a task
`[x]` with its merged PR number when done (Definition of Done).

**DAG:** T-1 → T-2 → { T-3 ∥ T-4 } → T-5.
(T-3 and T-4 are independent — dispatch after T-2 in parallel.)

**Criterion coverage:** SC-1, SC-5, SC-6 → T-1 · SC-2, SC-4 → T-2 · SC-3 →
T-3 + T-4 (both adapters) · T-5 enforces the whole set in CI.

---

### [x] T-1 — Scaffold + roster (#5)
- **Satisfies:** SC-1, SC-5, SC-6
- **Depends on:** —
- **Touches:** `pyproject.toml`, `uv.lock`, `src/agent_framework/{__init__,models,errors,roster}.py`, `tests/test_roster.py`, `examples/roster.toml`, `ruff`/`mypy` config
- **Brief:** Stand up the package (uv, ruff, mypy --strict, pytest+asyncio). Add
  `ModelRef` (dataclass) and the typed errors (`RosterError`,
  `UnknownRoleError`). Implement `Roster.from_file()` (stdlib `tomllib`),
  `resolve(role) -> ModelRef`, and rejection of any secret-looking field (keys
  come from env, never config).
- **Done when:** tests pass and cite their ids — SC-1 (each role resolves to the
  right `ModelRef`), SC-5 (a roster containing an API key is rejected), SC-6
  (validator + worker on different providers resolve to distinct providers);
  `ruff` + `mypy --strict` clean; `uv sync` reproducible.

### [x] T-2 — Provider interface + registry + dispatch (#6)
- **Satisfies:** SC-2, SC-4
- **Depends on:** T-1
- **Touches:** `src/agent_framework/providers/{base,registry}.py`, `src/agent_framework/dispatch.py`, `tests/test_dispatch.py`
- **Brief:** Add `providers/base.py` — `Request`, `Response`, `ToolCall`
  (dataclasses) and the `Provider` `Protocol` (`async invoke(request) ->
  response`). Add `providers/registry.py` (`register_provider` / `get_provider`,
  raising `UnknownProviderError`). Add `dispatch(roster, role, request)` —
  resolve the role, look up the adapter, invoke; no silent fallback.
- **Done when:** SC-2 (dispatch sends prompt + tools through a *fake* adapter and
  returns a normalized `Response`) and SC-4 (unknown role, or provider with no
  adapter, raises a typed error and does not invoke) pass, citing their ids.

### [x] T-3 — Anthropic adapter (#7)
- **Satisfies:** SC-3 (Anthropic half)
- **Depends on:** T-2
- **Touches:** `src/agent_framework/providers/anthropic.py`, `tests/test_provider_anthropic.py`, `pyproject.toml` (`anthropic` dep)
- **Brief:** `AnthropicProvider` wrapping the `anthropic` SDK; normalize its
  response into `Response` (`text` + `tool_calls`); read `ANTHROPIC_API_KEY` from
  env; register under `"anthropic"`. Keep the adapter thin (ADR 0001).
- **Done when:** SC-3's Anthropic test round-trips a request → normalized
  `Response` against a **mocked SDK transport** (no live call), citing SC-3.

### [x] T-4 — Google adapter (this PR)
- **Satisfies:** SC-3 (Google half)
- **Depends on:** T-2 (parallel with T-3)
- **Touches:** `src/agent_framework/providers/google.py`, `tests/test_provider_google.py`, `pyproject.toml` (`google-genai` dep)
- **Brief:** `GoogleProvider` wrapping `google-genai`; normalize to `Response`;
  read `GEMINI_API_KEY` from env; register under `"google"`. Thin adapter.
- **Done when:** SC-3's Google test round-trips a request → normalized `Response`
  against a mocked SDK transport, citing SC-3.

### [ ] T-5 — Spec-coverage CI + required status check
- **Satisfies:** — (enabling infrastructure: it *enforces* that every SC is
  covered, rather than satisfying a product criterion)
- **Depends on:** T-1, T-2, T-3, T-4
- **Touches:** `.github/workflows/ci.yml`, `scripts/check_spec_coverage.py`
- **Brief:** Adapt the methodology's `check-spec-coverage.py` (§5, ADR 0017) to
  verify SC → test mapping and `MUST` → criterion coverage (ADR 0011). Add a CI
  workflow: `uv sync --frozen`, `ruff`, `mypy --strict`, `pytest`, then the
  coverage check. Once green, add `required_status_checks` to the `protect-main`
  ruleset (the branch-protection piece deferred until CI existed).
- **Done when:** CI passes on a PR; the coverage check confirms all six `SC-`
  ids are traced to tests; the `main` ruleset requires the CI check to pass
  before merge.

---

## Criterion → task map

Which task delivers each criterion. The canonical `SC-` → **test** mapping
lives in `spec.md`'s Traceability table (single source, checked in CI by T-5);
this is only the planning view.

| Criterion | Requirement(s) | Task | Status |
|---|---|---|---|
| SC-1 | R-1, R-2 | T-1 | ✅ (#5) |
| SC-2 | R-2, R-3 | T-2 | ✅ (#6) |
| SC-3 | R-3, R-4 | T-3, T-4 | T-3 ✅ (#7); T-4 ✅ (this PR) |
| SC-4 | R-5 | T-2 | ✅ (#6) |
| SC-5 | R-6 | T-1 | ✅ (#5) |
| SC-6 | R-7 | T-1 | ✅ (#5) |
