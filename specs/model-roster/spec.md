# Spec: Model roster and provider abstraction

- **Status:** Approved
- **Date:** 2026-06-25
- **Author:** vpc
- **Related ADRs:** ADR 0001 (model-agnostic roles, bound by a roster)

> This spec is editable while `Draft` / `Under review` / `Approved`.
> When it reaches `Implemented` it **freezes** into a historical record;
> a contradiction found later goes to a test, a new spec, or an ADR —
> not back into this file (methodology §2, §8).

## Problem

ADR 0001 commits the framework to model-agnostic roles: `chief` / `worker` /
`validator` are slots bound to concrete models, reached through per-provider
adapters, with no hardcoded vendor. Today none of that exists — there is no way
to declare which model fills a role, and no uniform way to call a model
regardless of provider. Every downstream component (the chief's decomposition,
the workers, the validator gate) needs this substrate first, so until it exists
the model-agnostic claim is aspirational. This is the foundation slice, and it
is what proves ADR 0001 with working, tested code.

## Goals

1. A **roster** declaratively binds each role to a model (provider + model id).
2. A **uniform provider interface** invokes any configured model: prompt +
   tool definitions in, a normalized response out.
3. **Role-based dispatch:** given a role, resolve the bound model and invoke it
   through the right provider adapter.
4. Adding a provider is **a new adapter + a roster entry** — no changes to the
   dispatch core.

## Non-goals

- The chief / worker / validator *behaviours* (each is a later spec). This slice
  only lets a role invoke its model.
- Streaming, retries/failover, and cost/token accounting (later).
- Any config UI or dynamic/learned routing — the roster is static config.

## Requirements

Use [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) keywords. Every `MUST` is
reflected in a success criterion below.

- **R-1 (MUST)** The roster loads from declarative config binding each role to a
  `{provider, model-id}`.
- **R-2 (MUST)** Invoking a role resolves its model via the roster and
  dispatches through that model's provider adapter.
- **R-3 (MUST)** A single provider interface accepts a prompt + tool definitions
  and returns a normalized response (assistant text + any tool calls),
  identical in shape across providers.
- **R-4 (MUST)** At least two provider adapters implement the interface —
  Anthropic and Google.
- **R-5 (MUST)** An unknown role, or a roster referencing a provider with no
  adapter, **fails loudly** with a clear error — never a silent default or
  fallback.
- **R-6 (MUST)** Provider secrets (API keys) come from the environment / a
  secret manager, **never** the roster file or the repo (methodology §9).
- **R-7 (SHOULD)** When the roster binds `validator` to a different provider
  than `worker`, resolution preserves the distinction (the framework must not
  collapse roles onto one model), so a distinct-lineage validator is always a
  config choice.

## Success criteria

Each has a stable id and is verified by ≥1 test that cites it; together they
cover every `MUST`.

- **SC-1** — A roster binding `chief → anthropic/fable`, `worker →
  anthropic/sonnet`, `validator → google/gemini` resolves each role to the
  correct `{provider, model-id}`. (R-1, R-2)
- **SC-2** — Invoking a role sends the prompt + tool definitions through the
  bound model's adapter and returns a normalized response object (text + tool
  calls), verified against a mocked provider transport. (R-2, R-3)
- **SC-3** — Both the Anthropic and Google adapters implement the interface and
  round-trip a prompt → normalized response in tests (mocked transport, no live
  calls). (R-3, R-4)
- **SC-4** — Resolving an undefined role, or a roster entry whose provider has
  no adapter, raises a clear, typed error; no invocation occurs. (R-5)
- **SC-5** — Secrets are read from the environment; a roster file that contains
  an API key is rejected (or the key is ignored) so no secret can live in
  config or the repo. (R-6)
- **SC-6** — A roster with `validator` and `worker` on different providers
  resolves them to distinct providers (roles are not collapsed). (R-7)

## Open questions

Resolved before the spec is `Approved` (inline or via an ADR).

- [ ] **Implementation language / runtime** — not yet chosen; it's a
  future-constraining dependency decision, so it gets **its own ADR (0002)**
  before `plan.md`. The spec is language-neutral.
- [ ] **Response normalization depth** — providers differ on tool-call shape;
  how much to normalize vs. pass through is a `plan.md` question.
- [ ] **Roster format** — YAML / JSON / TOML: a small tooling call for
  `plan.md`.

## Out of scope (for now)

- Streaming responses; retries, timeouts, and cross-provider failover.
- Cost / token accounting and budget caps.
- Non-LLM tools and the MCP wiring workers will use (a later spec).

## Traceability

Built up during implementation; complete before the spec is `Implemented`.
Every `SC-` maps to the test(s) that verify it and the requirement(s) it covers;
a CI check fails on any uncovered criterion, and every `MUST` appears here
(methodology §5, ADR 0011).

| Criterion | Requirement(s) | Verified by (test) |
|---|---|---|
| SC-1 | R-1, R-2 | `tests/test_roster.py::test_sc1_resolves_each_role_to_its_model_ref` |
| SC-2 | R-2, R-3 | `tests/test_dispatch.py::test_sc2_dispatch_invokes_bound_provider_and_returns_response` |
| SC-3 | R-3, R-4 | `tests/test_provider_anthropic.py::test_sc3_anthropic_adapter_round_trips_to_normalized_response` (Google half pending T-4) |
| SC-4 | R-5 | `tests/test_dispatch.py::test_sc4_unknown_role_fails_loudly_and_does_not_invoke`, `…::test_sc4_provider_without_adapter_fails_loudly_and_does_not_invoke` |
| SC-5 | R-6 | `tests/test_roster.py::test_sc5_roster_with_a_secret_field_is_rejected`, `…::test_sc5_top_level_secret_is_rejected` |
| SC-6 | R-7 | `tests/test_roster.py::test_sc6_distinct_providers_are_preserved` |
