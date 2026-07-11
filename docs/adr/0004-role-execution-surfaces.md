# ADR 0004: Role execution surfaces — subscription-backed interactive roles, API-backed programmatic roles

- **Status:** Accepted
- **Date:** 2026-07-11
- **Deciders:** vpc

## Context

ADR 0001 made roles model-agnostic slots bound by the roster, and the
model-roster spec (now `Implemented`) built the substrate: thin provider
adapters (Anthropic, Google) invoked by role-based dispatch. The next
decision is *where each role actually runs* — which billing/auth surface
carries it — because the cost structures differ by an order of magnitude:

- **Subscriptions already paid for.** A Claude Max plan (used with Claude
  Code) and a Google AI Pro plan (Antigravity, Gemini app, and — since
  Jan 2026 — $10/month in Google Cloud credits via the Google Developer
  Program). Neither includes raw API credits: direct `ANTHROPIC_API_KEY` /
  `GEMINI_API_KEY` calls are metered separately (Console / Cloud billing).
- **Supported subscription paths for agents exist but differ in firmness.**
  Interactive Claude Code and Antigravity sessions are the plans' intended
  use. Headless Claude Code / the Claude Agent SDK currently also count
  against a Max plan (officially supported; a billing change announced for
  June 2026 was paused and is under review). Anthropic's Feb 2026
  authentication policy states OAuth is intended for Claude Code and
  claude.ai; fully programmatic agents' intended path is an API key.
- **The Gemini API has a real free tier** (rate-limited, no billing
  account); the Anthropic API has none.
- **Local inference is free at the margin.** An always-on M1 Max (64 GB)
  LAN server can host Ollama natively (Metal requires native macOS — no
  GPU passthrough in containers) and run 20–30B-class models well.
- **Roles differ in shape.** The chief and plan review are low-volume,
  judgment-heavy, and already human-in-the-loop (the human is author of
  record, above the chief). The worker is a high-volume *agentic loop*
  (edit, test, iterate — not single prompt→response). The validator gate
  is single-shot judgment over artifacts + CI results, in the exact
  `Request → Response` shape the adapters already serve. Retrieval and
  triage are high-volume, judgment-light.

The force in tension: minimizing spend without minimizing *total* cost —
a "free" surface whose output fails the validator gate costs more in
human review and rework than a metered call that lands first time.

## Decision

We bind each role to the cheapest surface that can hold it without
raising total cost, and keep every binding reversible:

| Role | Surface | Billing | Fallback |
|---|---|---|---|
| Chief (spec / plan / tasks) | Claude Code, interactive | Max plan (intended use) | — |
| Adversarial plan review | Antigravity, interactive | AI Pro (distinct lineage vs. chief, per ADR 0001) | — |
| Worker (coding) | Headless Claude Code / Agent SDK | Max plan, while supported | Same surface with `ANTHROPIC_API_KEY` + Console spend cap — an auth-config change, not a code change |
| Validator (cite-the-test gate) | Direct API via `GoogleProvider` | Gemini free tier | Vertex AI billing → the AI Pro $10/month Cloud credit |
| Retrieval + triage (embeddings, pre-validation checks, review-panel diversity) | Ollama on the M1 Max LAN server (native macOS service) | $0 marginal | — (non-critical path) |

Corollaries:

1. **The programmatic chief drops out of the build queue.** The chief's
   seat is a human-driven Claude Code session writing the same artifacts;
   dispatch only needs to serve programmatic roles (worker, validator,
   triage). Coordination through artifacts (ADR 0001) is what makes an
   interactive session and an API call interchangeable fillers of a role.
2. **The worker is orchestrated headless Claude Code, not a bespoke loop**
   built on the raw Messages API. The Agent SDK already is the agentic
   coding harness (tools, editing, tests); the framework dispatches a task
   artifact to a headless session and collects the PR. The concrete design
   is the worker spec's job, not this ADR's.
3. **Local models get infrastructure and triage, not authorship.**
   Embeddings over the artifact corpus, fuzzy pre-validation checks
   (anything fully machine-checkable stays a script, per methodology §5),
   and lineage diversity in review panels. No local model authors PRs.
4. **Spend caps precede live runs.** Before the first unmocked worker or
   validator invocation, the Console account gets a hard spend cap and the
   Google side stays inside the free tier until measured volume says
   otherwise.

## Alternatives considered

- **Everything through metered APIs** (the default the current adapters
  imply) — simplest and fully within every provider's intended use, but
  pays per token for work two already-paid subscriptions can carry, and
  hand-builds a worker harness the Agent SDK ships for free. Rejected on
  cost and build effort.
- **Everything on subscription auth, workers included, indefinitely** —
  cheapest on paper, but stakes the framework's core loop on a policy
  explicitly under review, and parallel workers share rate limits with the
  human's interactive sessions (the framework would compete with its own
  author of record for headroom). Rejected as a foundation; adopted only
  as the *current* worker surface with the API-key fallback one config
  change away.
- **Local models as workers** ("free" coding) — 20–30B local models
  regularly produce PRs that fail a `mypy --strict` + criterion-cited-test
  gate; the rework and human review cost exceeds a cheap frontier API
  model that lands work first pass. Rejected: minimum $/token is not
  minimum total cost.
- **Validator as an agentic session** (re-running tests itself) —
  unnecessary: CI already runs the tests (ADR 0003's required check); the
  validator judges artifacts + CI evidence, which the thin adapters
  already serve single-shot. Rejected as over-build.

## Consequences

- Marginal cost of a full chief→worker→validator cycle approaches zero
  today: subscriptions carry chief/review/worker, the free tier carries
  the validator, local inference carries triage.
- Every binding is reversible per the methodology's core rule: worker
  billing flips via auth config; validator billing flips via Vertex
  config; models flip via roster edit (ADR 0001).
- **New external dependencies on plan policies.** Two revisit triggers are
  part of this decision:
  1. Anthropic finalizes the Agent SDK / headless billing review, or
     otherwise tightens subscription auth for programmatic use → move
     workers to the API-key fallback (config change) and re-evaluate
     worker model choice on cost.
  2. Worker volume grows enough to squeeze interactive Max headroom or
     validator volume exhausts the Gemini free tier → same fallbacks,
     now on measured data.
- The worker's execution surface (headless Claude Code) is decided here;
  its orchestration design (task artifact → headless invocation, worktree
  isolation, PR handoff) is explicitly deferred to the worker spec.
- Two roles (chief, plan review) are *not* served by dispatch; the roster
  documents their binding for the record, but the framework does not
  invoke them. The model-agnostic claim is unchanged — an interactive
  session is just another provider of a role's artifacts.
- The M1 Max server becomes quiet infrastructure the framework assumes
  (embeddings/triage endpoint); its unavailability degrades triage, never
  correctness — nothing on the critical path depends on it.

## Adoption impact

Project ADR. Rollout it forces:

- The worker spec (next slice) designs against headless Claude Code, not
  a bespoke Messages-API loop.
- An `OllamaProvider` adapter + roster entry when the triage/embedding
  slice is specified (also the cheapest third-lineage proof of ADR 0001).
- Console spend cap configured before the first live worker/validator run.
- `docs/architecture.md` (when first written) records the role→surface
  mapping as part of the system's current shape.

## References

- ADR 0001 — model-agnostic roles, bound by a roster (the seam that makes
  surfaces swappable).
- ADR 0003 — spec-coverage CI (why the validator can judge on CI evidence
  instead of re-running tests).
- `docs/design/orchestration-design.md` — artifacts as the coordination
  medium; two-stage review (conformance vs. refutation).
- Anthropic: "Use the Claude Agent SDK with your Claude plan" (support
  article); Feb 2026 authentication policy; June 2026 Agent SDK billing
  change (announced, paused, under review).
- Google: Gemini API billing docs (free tier; separate billing account);
  Google Developer Program premium benefits in AI Pro/Ultra (Jan 2026,
  $10–$100/month Cloud credits).
