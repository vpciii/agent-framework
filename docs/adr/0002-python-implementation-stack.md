# ADR 0002: Python implementation stack

- **Status:** Accepted
- **Date:** 2026-06-25
- **Deciders:** vpc

## Context

The `model-roster` spec (the foundation slice) flagged the implementation
language as an open question to settle *before* `plan.md`, because it is
future-constraining — every component is written in it. The framework's work is
orchestration: calling LLM providers (Anthropic, Google), speaking MCP, managing
subprocesses and git worktrees for workers, and following the methodology
(tests-as-spec, spec-criterion coverage in CI).

## Decision

**The framework is written in Python (3.12+),** with this founding toolchain
(each a §10 dependency decision, recorded here so §10 stays traceable):

- **`uv`** — dependency management + lockfile (`uv.lock` committed).
- **`pytest`** + **`pytest-asyncio`** — tests (the orchestration is async).
- **`ruff`** — lint + format (the automated style gate; review spends attention
  on behavior, not style).
- **`mypy --strict`** — static types.
- **`asyncio`** — concurrency for parallel provider calls and worker
  orchestration (the work is I/O-bound; the GIL is not a constraint).

Provider adapters (ADR 0001) wrap the **official provider SDKs** (`anthropic`,
`google-genai`) behind the common interface, kept thin so the SDK is swappable.

## Alternatives considered

- **TypeScript / Node** — also has both provider SDKs, the MCP TS SDK, and
  strong async. Rejected: no ecosystem advantage over Python here, and it
  diverges from the existing stack — `opn-mcp` is already Python + `uv` +
  `pytest`, so conventions, the spec-coverage checker (stdlib Python), and
  muscle memory carry straight over.
- **Go** — great for a self-contained binary and concurrency, but the LLM SDKs
  are less mature and it adds ceremony for what is mostly orchestration glue.
  Rejected for the first cut.
- **Raw HTTP instead of provider SDKs** — considered; rejected for now: the SDKs
  handle auth, retries, and streaming. The adapter stays thin enough that
  dropping to HTTP later is a contained change if an SDK disappoints.

## Consequences

- Aligns with `opn-mcp`: same package manager, test runner, and CI-check
  conventions; the methodology's `check-spec-coverage.py` runs as-is.
- The AI ecosystem is first-class (official SDKs, MCP Python SDK).
- Async orchestration is idiomatic; concurrent provider calls and worker fan-out
  come naturally.
- A per-provider SDK dependency to weigh and pin (§10) — `uv.lock` committed; a
  behavior-changing major bump warrants its own ADR.
- Commits the project to the Python packaging world (`pyproject.toml`, `uv`).

## Adoption impact

Founding stack decision — all code is Python from the first line. No migration
(greenfield).

## References

- The `model-roster` spec (`specs/model-roster/spec.md`) — flagged this decision.
- ADR 0001 (model-agnostic roles; adapters wrap provider SDKs).
- `methodology.md` §6 (Twelve-Factor), §10 (dependencies are decisions,
  lockfiles committed), the "automate what is checkable" rule.
- Precedent: `opn-mcp` (Python + `uv` + `pytest`).

---

> Following the format proposed by Michael Nygard in
> [Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).
