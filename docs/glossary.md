# Glossary — agent-framework

The project's ubiquitous language. Use these terms exactly, in code, docs,
and agent prompts. Add a term here before inventing a name for a concept.

- **Chief agent** — the coordinating agent. Decomposes a signed-off
  `spec.md` into `tasks.md`, dispatches tasks, and runs the aggregate
  requirements-met check. Does **not** write feature code, and is **not**
  the final acceptance authority (the human is).
- **Worker agent** — executes exactly one **task** → one PR with tests.
  May be a cheaper model. Reads its task + the spec, not the chief's
  context.
- **Validator agent** — gates a worker's PR against its criteria via the
  **cite-the-test gate**. A *different model* than the worker, for
  blind-spot coverage.
- **Task** — a PR-sized (~<300-line) unit of work in `tasks.md`, tracing to
  **≥1 success criterion**, with explicit dependencies (the tasks form a
  DAG) and an explicit "done when" (the tests that must pass).
- **Success criterion (`SC-…`)** — a stable-id, testable signal defined in
  the spec. The **coordination thread**: it ties chief intent → worker
  output → validator check → the chief's requirements-met verdict.
- **Cite-the-test gate** — the validator's rule: a **PASS** must cite the
  passing test for each claimed criterion (plus red→green for a fix, green
  CI, and the review checklist); it never asserts "looks correct." Output
  is a structured `PASS{criteria:[SC-…✓(test)]}` or `REJECT{finding,
  evidence}`.
- **Ready frontier** — the set of tasks whose DAG dependencies are all
  satisfied, dispatchable in parallel.
- **Escalation** — when a worker finds the spec wrong (or a term/boundary
  is unspecified), it stops and escalates to the chief; a contract change
  is its own diff for human sign-off, never a quiet `tasks.md` edit.
- **Role** — a model-agnostic slot (chief / worker / validator), bound to a
  concrete model by the **roster**. The framework hardcodes no vendor
  (ADR 0001).
- **Roster** — the single config that binds each role to a model (e.g.
  `chief: claude-fable-5`, `worker: claude-sonnet-5`,
  `validator: gemini-3-pro`). Swapping a model is a roster edit, not a code
  change; it is the one source of truth for the role→model mapping.
- **Provider adapter** — a thin per-provider (Anthropic, Google, …) shim
  behind a common interface (prompt + tools in, response out), so models are
  pluggable. Adding a provider = a new adapter + a roster entry.
