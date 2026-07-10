# agent-framework

A hierarchical **agent-orchestration** layer for methodology-driven
development: a **chief** agent plans and dispatches, **worker** agents write
the code, and a **validator** agent gates their output — all coordinating
**through the shared methodology's artifacts** rather than through chat.

- **Chief** decomposes a signed-off `spec.md` into a DAG of PR-sized tasks,
  each traced to success-criterion (`SC-…`) ids; dispatches the ready
  frontier; verifies requirements-met at the end.
- **Workers** each take a task → one small PR with tests that cite the
  criterion ids. Can be cheaper models.
- **Validator** gates each PR with a **cite-the-test** rule — a PASS names
  the passing test per criterion, never a vibe — and is a *different model*
  than the worker (blind-spot coverage).
- **The human** is author of record, above the chief.

**Model-agnostic.** Roles are slots bound to models by a **roster** — e.g.
`chief: claude-fable-5`, `worker: claude-sonnet-5`, `validator: gemini-3-pro` —
reached through thin per-provider adapters. Swap a model by config, not code;
no vendor lock-in ([ADR 0001](docs/adr/0001-model-agnostic-roles.md)).

The design principle: **the methodology's artifacts are the coordination
protocol.** This repo is disposable orchestration *over* that contract, so
the harness is swappable while the artifacts endure — and because the
artifacts are model-neutral, every model in every role follows the same
practices.

## Status

Nascent. The initial design is in
[`docs/design/orchestration-design.md`](docs/design/orchestration-design.md);
it feeds the first `specs/<slug>/`. Development follows the shared
methodology at `$METHODOLOGY_HOME` (`~/Developer/methodology`) — see
[`CLAUDE.md`](CLAUDE.md).
