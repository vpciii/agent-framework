# Plan: Model roster and provider abstraction

- **Status:** Draft
- **Date:** 2026-06-25
- **Author:** vpc
- **Spec:** ./spec.md
- **Related ADRs:** ADR 0001 (model-agnostic roles), ADR 0002 (Python stack)

> This plan freezes with its spec: editable while `Draft` / `Under review` /
> `Approved`, a historical record once `Implemented` (methodology §2, ADR 0007).
> A contradiction found later goes to a test, a new spec, or an ADR — not back
> into this file.

## Approach

A small, dependency-light core with three seams:

1. **Roster** — loaded from a **TOML** file (`tomllib`, stdlib — no dependency)
   binding each role to `{provider, model}`. `Roster.resolve(role) →
   ModelRef(provider, model)`. Rejects a roster that carries a secret-looking
   field (SC-5) — keys never live in config.
2. **Provider interface** — a `Provider` `Protocol`: `async def
   invoke(request: Request) -> Response`. `Request` = `{prompt, tools}`;
   `Response` = `{text, tool_calls}` — one normalized shape across providers.
   Thin stdlib `@dataclass`es (no pydantic — the models are simple; keeps deps
   minimal per §10).
3. **Dispatch** — `async def dispatch(roster, role, request) -> Response`
   resolves the role via the roster, looks up the provider adapter in a
   **registry** (name → factory), and invokes it. Unknown role →
   `UnknownRoleError`; provider with no adapter → `UnknownProviderError`. Typed,
   no silent fallback (SC-4).

Provider adapters wrap the official SDKs and normalize their responses; they are
the only place a vendor SDK is imported.

## Components touched

Greenfield — all new, under `src/agent_framework/`:

- `roster.py` — `Roster.from_file()`, `resolve()`, secret-field rejection.
- `providers/base.py` — `Provider` Protocol, `Request`, `Response`, `ToolCall`.
- `providers/anthropic.py` — `AnthropicProvider` (wraps `anthropic`).
- `providers/google.py` — `GoogleProvider` (wraps `google-genai`).
- `providers/registry.py` — `{ "anthropic": …, "google": … }` name → factory.
- `dispatch.py` — `dispatch()` (resolve + invoke).
- `errors.py` — `UnknownRoleError`, `UnknownProviderError`, `RosterError`.
- `tests/` — one module per SC (see Test strategy).
- `pyproject.toml`, `uv.lock`; `examples/roster.toml`.

## Data model changes

No datastore. In-memory `@dataclass`es only:

```
ModelRef(provider: str, model: str)
Request(prompt: str, tools: list[ToolDef] = [])
ToolCall(name: str, arguments: dict)
Response(text: str, tool_calls: list[ToolCall] = [])
```

Roster TOML shape (no secrets — keys come from env):

```
[roles]
chief     = { provider = "anthropic", model = "claude-fable-5" }
worker    = { provider = "anthropic", model = "claude-sonnet-5" }
validator = { provider = "google",    model = "gemini-3-pro" }
```

## API changes

Public surface (the substrate later specs build on):

- `Roster.from_file(path) -> Roster` / `roster.resolve(role: str) -> ModelRef`
- `class Provider(Protocol): async def invoke(self, request: Request) -> Response`
- `register_provider(name, factory)` / `get_provider(name) -> Provider`
- `async def dispatch(roster, role, request) -> Response`
- Secrets read from env in each adapter: `ANTHROPIC_API_KEY`,
  `GEMINI_API_KEY` (never passed through the roster).

## Alternatives considered

- **Config format** — YAML (needs `pyyaml`) vs JSON vs **TOML**. Chose TOML:
  stdlib `tomllib`, human-friendly, matches `pyproject.toml`. No new dependency.
- **Models** — pydantic vs **stdlib dataclasses**. Chose dataclasses: the models
  are thin; avoids a dependency (§10). Revisit if validation needs grow.
- **Response normalization depth** — full canonical schema vs **thin**. Chose
  thin (`text` + `tool_calls`): enough for the orchestration to route, and it
  keeps adapters thin per ADR 0001. Extra fields (usage, stop reason) are
  additive later.

## Risks

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| Provider tool-call shapes differ; normalization leaks | Med | Med | Thin `Response`; per-adapter tests with mocked transport (SC-3) pin the mapping |
| An API key slips into a roster file | Low | High | SC-5 test + `Roster.from_file` rejects secret-looking fields |
| SDK churn breaks an adapter | Med | Low | Pin in `uv.lock`; adapter thin, so swapping SDK/HTTP is contained |
| Async surface leaks sync callers | Low | Low | `invoke`/`dispatch` are `async` from day one |

## Rollout

A library — no deployment, no flag needed (nothing depends on it yet). Fully
reversible (new code). It ships when its criteria pass; downstream specs (chief,
worker, validator) import it.

## Observability

Structured logging on `dispatch`: role → `{provider, model}`, latency, and token
usage when the SDK reports it. No metrics/tracing yet — added when there's a
running orchestrator to observe.

## Test strategy

`pytest` + `pytest-asyncio`; **no live API calls** — provider SDKs mocked at the
transport layer (the `opn-mcp` pattern). Each SC gets ≥1 test citing its id, and
the spec-coverage check (§5, adapted from `check-spec-coverage.py`) runs in CI —
which also becomes the first required status check on `main`.

- **SC-1** roster resolves each role to the right `ModelRef`.
- **SC-2** `dispatch` sends prompt+tools through a fake adapter, returns a
  normalized `Response`.
- **SC-3** Anthropic + Google adapters each round-trip a request → `Response`
  against a mocked SDK transport.
- **SC-4** unknown role / provider-without-adapter → typed error, no invocation.
- **SC-5** a roster file containing a key is rejected.
- **SC-6** validator + worker on different providers resolve to distinct
  providers.
