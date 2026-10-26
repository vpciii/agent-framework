# Spec: Roster currency check — notice when a bound model goes stale

- **Status:** Approved
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
  open pull requests. The run's GitHub token has read access to
  contents, write access to issues, and `id-token: write` — the last
  used only to request the identity token for Anthropic federation
  (R-12), never to authenticate anywhere else.
- **R-7 (MUST)** Reach providers only through provider adapters (ADR
  0001): adding a provider adds a listing method to its adapter, not a
  branch in the check. Tests run against fake adapters, no network.
- **R-8 (MUST)** Take credentials only from the environment (repository
  secrets and variables in CI), never from files in the repo.
- **R-9 (SHOULD)** Report an advisory, non-failing finding when the
  provider's listing contains a newer model in the same family as the
  bound one, naming the candidate.
- **R-10 (SHOULD)** Where a provider reveals which model actually served
  a request, detect a bound ID that is silently routed to a different
  model, with a minimal probe request, and report it as a failing finding.
- **R-11 (SHOULD)** Close the tracking issue when a run finds nothing
  failing or unchecked.
- **R-12 (MUST)** Authenticate to Anthropic with Workload Identity
  Federation when it is configured (no stored Anthropic secret), falling
  back to an `ANTHROPIC_API_KEY` repository secret only when federation
  is not configured. When federation is configured, the check step MUST
  NOT also receive `ANTHROPIC_API_KEY`: the SDK gives an API key
  precedence over federation, so exposing both would silently bypass it.

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
  `workflow_dispatch` only, declares `permissions` of `contents: read`,
  `issues: write` and `id-token: write` and nothing more, reads
  credentials only from `secrets.*` and `vars.*`, and is not referenced
  by `ci.yml`.
- **SC-6** — The check resolves providers through the provider registry:
  registering a fake adapter under a new provider name makes roles bound
  to it checkable without changing the check's code.
- **SC-7** — When the listing has a newer model in the bound model's
  family, the run reports an advisory finding naming it and still exits
  zero (if nothing else fails).
- **SC-8** — When a probe reports a serving model different from the
  bound ID, the run reports a failing finding naming both.
- **SC-9** — In the workflow, the step that runs the check receives the
  federation variables (`ANTHROPIC_FEDERATION_RULE_ID`,
  `ANTHROPIC_ORGANIZATION_ID`, `ANTHROPIC_SERVICE_ACCOUNT_ID`,
  `ANTHROPIC_IDENTITY_TOKEN_FILE`) when the rule ID variable is set, and
  `ANTHROPIC_API_KEY` only when it is not; the identity token is
  requested with audience `https://api.anthropic.com`.

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
  issues: write, id-token: write}`. `GEMINI_API_KEY` comes from repo
  secrets. A step runs the CLI to a JSON report; a following step (always
  runs) opens or updates the issue labelled `roster-currency` with `gh`,
  or closes it when clean (R-11). The issue logic sits in a small tested
  function behind a GitHub-client seam (SC-4).
- **Anthropic auth (R-12):** following Anthropic's GitHub Actions WIF
  guide. When `vars.ANTHROPIC_FEDERATION_RULE_ID` is set, a step fetches
  GitHub's OIDC token (audience `https://api.anthropic.com`) into a
  file, and the check step gets `ANTHROPIC_FEDERATION_RULE_ID`,
  `ANTHROPIC_ORGANIZATION_ID`, `ANTHROPIC_SERVICE_ACCOUNT_ID` (repo
  *variables* — identifiers, not secrets) and
  `ANTHROPIC_IDENTITY_TOKEN_FILE`; the SDK (already supported by the
  locked `anthropic` 0.116) exchanges it for a ~10-minute access token.
  Otherwise the step gets `secrets.ANTHROPIC_API_KEY`; with neither,
  the Anthropic roles report *unchecked* (R-4). The job runs well under
  the GitHub token's ~5-minute life, so no refresh loop is needed.
- **Federation rule (set up once, in the Console):** issuer
  `https://token.actions.githubusercontent.com` in discovery mode; rule
  `subject_prefix: "repo:vpciii/agent-framework:ref:refs/heads/main"`,
  `audience: "https://api.anthropic.com"`, `claims: {repository_owner:
  vpciii, ref: refs/heads/main}`; target a dedicated service account;
  `oauth_scope: workspace:developer`; `token_lifetime_seconds: 600`.
  Scheduled and dispatched runs both run on `main`, so pull-request runs
  and other branches cannot authenticate.
- **Size:** adapter methods + core + CLI + workflow + tests ≈ 250–300
  lines; fits one PR. If it doesn't, this spec grows a `plan.md`.

### Decisions

- *2026-10-26* — Detect, don't float: pinned IDs plus a scheduled check,
  rather than "latest" aliases in the roster, so a model change is
  always a visible human edit (discussion with vpc, 2026-10-26).
- *2026-10-26* — Anthropic roles are checked with an `ANTHROPIC_API_KEY`
  repository secret that vpc adds: a Console key with a hard spend cap,
  per ADR 0004 corollary 4 ("spend caps precede live runs").
- *2026-10-26* — Superseding the entry above: Anthropic access uses
  **Workload Identity Federation**, with the `ANTHROPIC_API_KEY` secret
  kept only as a fallback. No long-lived Anthropic credential is stored
  in this public repo, and the rule admits only runs on `main` (vpc's
  decision, 2026-10-26). The organization's monthly spend limit still
  applies.
- *2026-10-26 (implementation)* — Catalog and probe are separate
  `ModelCatalog` / `ModelProbe` protocols in `providers/base.py` rather
  than new methods on `Provider`, so existing adapters and test fakes stay
  valid; an adapter without `ModelCatalog` makes its roles *unchecked*.
- *2026-10-26 (implementation)* — "Newer" compares the version tokens in
  the ID for every provider (not Anthropic's `created_at`): one rule,
  and the listing's dates say when a model shipped, not where it sits in
  its family. Date-stamped snapshot IDs are never candidates.
- *2026-10-26 (implementation)* — No Anthropic probe: a request costs
  tokens and the API echoes the requested model, so it would not reveal
  routing. The Google probe stays; whether `model_version` reveals
  Gemini's rerouting is confirmed by the first live run.
- *2026-10-26 (implementation)* — One CLI step does the check and the
  issue sync (`--sync-issue`) instead of a separate always-run step; the
  workflow has two mutually exclusive check steps (federation / API-key
  fallback) so the key is never exposed alongside federation (R-12).
  Advisory-only runs close or skip the issue (R-11) and appear in the run
  log.
- *2026-10-26 (implementation)* — `pyyaml` + `types-pyyaml` added as
  dev-only dependencies so SC-5 and SC-9 are tested against the parsed
  workflow, not by text matching.

## Rollout and undo

Additive and advisory: a new workflow and module, no change to the gate
or to any existing behavior. Undo is deleting the workflow file (or
disabling it in the Actions UI) and reverting the PR; the tracking issue
can be closed by hand. The federation setup is
reversible: archive the federation rule (and, if unused elsewhere, the
service account and issuer) in the Console and delete the repo
variables; the fallback secret, if added, is deleted or rotated.
Nothing irreversible.

## Open questions

- [x] **Anthropic credential.** Resolved 2026-10-26: Workload Identity
  Federation (R-12), set up by vpc in the Console; an `ANTHROPIC_API_KEY`
  secret is the fallback. Until either exists, the Anthropic roles
  report *unchecked* (R-4). The organization's monthly spend limit is
  the cap (ADR 0004 corollary 4).
- [x] **Federation availability.** Resolved 2026-10-26: available to
  the organization. vpc registered the `github-actions` issuer, a
  `roster-currency-check` service account and a federation rule (this
  repo, `main` only, audience `https://api.anthropic.com`, Default
  workspace, `workspace:developer`, 10-minute tokens); the rule,
  service-account and organization IDs are set as repository variables.
  First real exchange is verified by the implementation PR's manual run.
- [x] **Routing visibility.** Resolved 2026-10-26 as best-effort:
  R-10 is a SHOULD. The implementation first probes whether Gemini's
  `model_version` (and Anthropic's response `model`) reveal rerouting;
  a provider that does not gets no probe, and that is recorded as a
  dated Decision rather than reopening this spec. SC-8 is verified
  against a fake adapter either way.
- [x] **Glossary.** Resolved 2026-10-26: the implementing PR adds
  **Roster currency check** to `docs/glossary.md` (vpc). "Finding" is
  used in its ordinary sense and gets no entry.
- [x] **Cadence.** Resolved 2026-10-26: weekly (vpc).

## Out of scope (for now)

- Auto-updating the roster or opening a PR with a suggested change.
- Checking pricing, quotas, or terms-of-service changes.
- Local model providers (Ollama / `mlx_lm.server` on defiant) — revisit
  with the durable-autonomy bet if a local adapter lands.

## Traceability

| Criterion | Requirement(s) | Verified by (test) |
|---|---|---|
| SC-1 | R-1 | `tests/currency/test_check.py::test_sc1_unserved_model_is_a_failing_finding`, `tests/currency/test_check.py::test_sc1_sc2_cli_exit_code_follows_findings` |
| SC-2 | R-1 | `tests/currency/test_check.py::test_sc2_all_served_roster_has_no_failing_finding`, `tests/currency/test_check.py::test_sc1_sc2_cli_exit_code_follows_findings` |
| SC-3 | R-4 | `tests/currency/test_check.py::test_sc3_unlistable_provider_leaves_roles_unchecked`, `tests/currency/test_check.py::test_sc3_unregistered_provider_is_unchecked` |
| SC-4 | R-5 | `tests/currency/test_issue.py::test_sc4_failing_run_updates_the_open_issue`, `tests/currency/test_issue.py::test_sc4_failing_run_opens_exactly_one_issue`, `tests/currency/test_issue.py::test_sc4_gh_tracker_finds_and_creates_through_the_gh_cli` |
| SC-5 | R-2, R-3, R-6, R-8 | `tests/currency/test_workflow.py::test_sc5_triggers_permissions_and_isolation_from_the_gate`, `tests/currency/test_workflow.py::test_sc5_credentials_come_only_from_secrets_and_vars` |
| SC-6 | R-7 | `tests/currency/test_check.py::test_sc6_new_provider_needs_only_a_registered_adapter`, `tests/currency/test_adapters.py::test_sc6_anthropic_adapter_lists_model_ids`, `tests/currency/test_adapters.py::test_sc6_google_adapter_lists_model_ids_without_prefix` |
| SC-7 | R-9 | `tests/currency/test_check.py::test_sc7_newer_sibling_is_advisory_only`, `tests/currency/test_check.py::test_sc7_family_parsing_ignores_snapshots_and_other_tiers` |
| SC-8 | R-10 | `tests/currency/test_check.py::test_sc8_rerouted_model_is_a_failing_finding`, `tests/currency/test_adapters.py::test_sc8_google_probe_reports_the_serving_model` |
| SC-9 | R-12 | `tests/currency/test_workflow.py::test_sc9_federation_and_api_key_are_never_combined`, `tests/currency/test_workflow.py::test_sc9_oidc_token_requested_for_the_anthropic_audience` |
