# Spec: Roster currency check — notice when a bound model goes stale

- **Status:** Draft
- **Date:** 2026-10-26
- **Author:** Claude (draft) — vpc is author of record
- **Related ADRs:** ADR 0001 (model-agnostic roles — the roster is the one
  place a model is named), ADR 0004 (role execution surfaces), ADR 0005
  (one per-PR gate — this check is deliberately *not* part of it)
- **Related specs:** model-roster (Implemented, frozen — this adds a
  read-only consumer of the roster, no change to its contract)
- **Compact spec** (ADR 0024): one PR; Approach and Rollout below.

> This spec is editable while `Draft` / `Under review` / `Approved`.
> When it reaches `Implemented` it **freezes** into a historical record;
> a contradiction found later goes to a test, a new spec, or an ADR —
> not back into this file (methodology §2, §8). If the feature is later
> sunset, only the status flips to `Retired` (ADR 0019) — the content
> stays frozen.

## Problem

The roster pins each role to a concrete model ID, which is right: a
pinned model makes a validator verdict or a worker PR attributable to a
known model. But providers move underneath a pin without telling anyone.
The 2026-10-26 currency review found the validator's `gemini-3.5-flash`
had been silently routed to a previous-generation model, both Claude IDs
superseded, and a documented example (`gemini-3-pro`) no longer a valid
ID at all — three months after the last commit, discovered only because
vpc happened to ask.

Nobody is watching for this today. The roster's correctness depends on
someone remembering to check provider deprecation pages, which the
methodology names as exactly the kind of thing that belongs in CI rather
than in memory. Docs no longer restate model IDs (#49), so the roster in
`agent-framework.toml` is now the single thing that can go stale.

## Goals

1. When a model the roster binds stops being served, vpc finds out
   within a week, without having to look.
2. When a bound model has a newer sibling, vpc is told — as information,
   not as an alarm.
3. Pinning stays the norm: nothing changes the roster except a human edit.

## Non-goals

- Choosing or switching models automatically, or opening PRs that do.
- Checking model IDs outside the roster (docs are model-neutral now;
  ADRs, frozen specs and test fixtures are history).
- Tracking price, rate-limit, or terms changes.
- Local model servers (Ollama, `mlx_lm.server`) — not roster providers
  today; they join when a provider adapter for them exists.

## Requirements

- **R-1 (MUST)** For each role in the roster, determine whether its
  provider currently serves the bound model ID, using the provider's own
  model listing. A model the provider does not serve is a failing
  finding naming the role, provider, and model ID.
- **R-2 (MUST)** Run on a schedule (weekly) and on manual dispatch.
- **R-3 (MUST NOT)** Be part of the per-PR gate or a required status
  check: a provider outage or missing credential must never block a PR
  (ADR 0005).
- **R-4 (MUST)** A role whose provider cannot be checked (no credentials,
  API error) is reported as *unchecked* — never as passing.
- **R-5 (MUST)** Report through one tracking issue: open it when there
  are failing or unchecked findings, update it on later runs rather than
  opening duplicates.
- **R-6 (MUST NOT)** Write to the roster, the repository contents, or
  open pull requests; the run's GitHub token has read access to contents
  and write access to issues only.
- **R-7 (MUST)** Reach providers only through provider adapters (ADR
  0001): adding a provider adds a listing method to its adapter, not a
  branch in the check. Tests run against fake adapters, no network.
- **R-8 (MUST)** Take credentials only from the environment (repository
  secrets in CI), never from files in the repo.
- **R-9 (SHOULD)** Report an advisory, non-failing finding when the
  provider's listing contains a newer model in the same family as the
  bound one, naming the candidate.
- **R-10 (SHOULD)** Where a provider reveals which model actually served
  a request, detect a bound ID that is silently routed to a different
  model, with a minimal probe request, and report it as a failing finding.
- **R-11 (SHOULD)** Close the tracking issue when a run finds nothing
  failing or unchecked.

## Success criteria

- **SC-1** — A roster binding whose model ID is absent from the fake
  provider's listing yields a failing finding naming role, provider and
  model; the run exits non-zero.
- **SC-2** — A roster whose every model is listed yields no failing
  finding; the run exits zero.
- **SC-3** — A provider adapter that reports missing credentials or
  raises yields an *unchecked* finding for each role bound to it, and
  the run exits non-zero.
- **SC-4** — With an open tracking issue already present, a failing run
  updates that issue and opens none; with none present, it opens exactly
  one.
- **SC-5** — The workflow file triggers on `schedule` and
  `workflow_dispatch` only, declares `permissions` of `contents: read`
  and `issues: write` and nothing more, reads credentials only from
  `secrets.*`, and is not referenced by `ci.yml`.
- **SC-6** — The check resolves providers through the provider registry:
  registering a fake adapter under a new provider name makes roles bound
  to it checkable without changing the check's code.
- **SC-7** — When the listing has a newer model in the bound model's
  family, the run reports an advisory finding naming it and still exits
  zero (if nothing else fails).
- **SC-8** — When a probe reports a serving model different from the
  bound ID, the run reports a failing finding naming both.

## Approach

- **Core:** `agent_framework/currency.py` — a pure function from the
  loaded roster plus each provider's listing to a list of findings
  (`failing` / `unchecked` / `advisory`), so every criterion is a unit
  test over fakes. A thin CLI, `python -m agent_framework.currency`
  (console script `agent-framework-currency`), loads the roster, calls
  the adapters, prints findings, and sets the exit code — the same shape
  as the validator's `__main__`.
- **Adapters:** the provider protocol gains `list_models()` (IDs plus
  any creation date or version the listing gives) and an optional
  `probe_model(model)` returning the serving model where the provider
  exposes it. Anthropic: `client.models.list()` (fields: `id`,
  `created_at`, limits, capabilities — no deprecation field). Google:
  `client.models.list()` (fields: `name`, `version`, limits — no
  deprecation or routing field), and a 1-token `generate_content` probe
  whose response `model_version` should reveal routing — unverified;
  the first implementation step is to confirm it does for
  `gemini-3.5-flash` (see Open questions).
- **Family and "newer":** family is the ID with its version token
  removed (`claude-sonnet-5-5` → `claude-sonnet`, `gemini-3.8-flash` →
  `gemini-*-flash`); newer is a later `created_at` (Anthropic) or a
  higher version number (Google). A heuristic, so advisory only (R-9).
- **Workflow:** `.github/workflows/roster-currency.yml` — weekly cron
  (Mondays) plus `workflow_dispatch`; `permissions: {contents: read,
  issues: write}`; `GEMINI_API_KEY` and `ANTHROPIC_API_KEY` from repo
  secrets. A step runs the CLI to a JSON report; a following step (always
  runs) opens or updates the issue labelled `roster-currency` with `gh`,
  or closes it when clean (R-11). The issue logic sits in a small tested
  function behind a GitHub-client seam (SC-4).
- **Size:** adapter methods + core + CLI + workflow + tests ≈ 250–300
  lines; fits one PR. If it doesn't, this spec grows a `plan.md`.

### Decisions

- *2026-10-26* — Detect, don't float: pinned IDs plus a scheduled check,
  rather than "latest" aliases in the roster, so a model change is
  always a visible human edit (discussion with vpc, 2026-10-26).

## Rollout and undo

Additive and advisory: a new workflow and module, no change to the gate
or to any existing behavior. Undo is deleting the workflow file (or
disabling it in the Actions UI) and reverting the PR; the tracking issue
can be closed by hand. Adding the `ANTHROPIC_API_KEY` secret is
reversible (delete or rotate it). Nothing irreversible.

## Open questions

- [ ] **Anthropic credential.** The repo has only `GEMINI_API_KEY`.
  Add an `ANTHROPIC_API_KEY` secret (a Console key with a hard spend cap;
  listing models costs nothing, and Max now includes monthly API
  credits)? Until then the Anthropic roles report *unchecked* — R-4 keeps
  that honest, but the issue would stay open permanently.
- [ ] **Routing visibility.** Does Gemini's response `model_version`
  actually name `gemini-3.6-flash` when `gemini-3.5-flash` is requested?
  Does an Anthropic response's `model` field ever differ from the
  requested ID? Where neither does, R-10 is unachievable for that
  provider, which is acceptable — it is a SHOULD.
- [ ] **Glossary.** "Roster currency check" names a new concept; propose
  adding it (and "finding", if the term is kept) to `docs/glossary.md`
  in the implementing PR.
- [ ] **Cadence.** Weekly is the proposal; daily costs nothing extra but
  adds issue noise during an outage.

## Out of scope (for now)

- Auto-updating the roster or opening a PR with a suggested change.
- Checking pricing, quotas, or terms-of-service changes.
- Local model providers (Ollama / `mlx_lm.server` on defiant) — revisit
  with the durable-autonomy bet if a local adapter lands.

## Traceability

| Criterion | Requirement(s) | Verified by (test) |
|---|---|---|
| SC-1 | R-1 | *(pending)* |
| SC-2 | R-1 | *(pending)* |
| SC-3 | R-4 | *(pending)* |
| SC-4 | R-5 | *(pending)* |
| SC-5 | R-2, R-3, R-6, R-8 | *(pending)* |
| SC-6 | R-7 | *(pending)* |
| SC-7 | R-9 | *(pending)* |
| SC-8 | R-10 | *(pending)* |
