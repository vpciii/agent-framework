# Adopting agent-framework in a project

How a repo goes from zero to a gated worker PR. The framework coordinates
through the methodology's artifacts (ADR 0001) — most of adoption is the
target project having them; the framework-specific surface is one config
file, one CI job, one secret. Kept honest by the opn-mcp pilot
(project-portability R-5/R-6): every step below was actually required
there.

## Prerequisites (the target repo)

1. **Methodology artifacts** — `specs/<slug>/spec.md` with `R-n`/`SC-n`
   ids and a Traceability table, `tasks.md` with `T-n` tasks tracing to
   criteria, and a spec-coverage check in CI (adapt the methodology's
   reference checker, its ADR 0017). An existing codebase adopts these
   forward-only per the methodology's `adopting.md`.
2. **Deterministic CI** on every PR (the validator judges CI evidence,
   never re-runs tests), with a required status check.
3. On the dispatching machine: the `claude` CLI (worker sessions;
   auth per ADR 0004 — Max subscription or `ANTHROPIC_API_KEY`), `gh`
   authenticated for the repo, and `git`.

## Target-side changes (the adoption PR)

1. **`agent-framework.toml`** at the repo root:

   ```toml
   [roles]
   worker    = { provider = "anthropic", model = "claude-sonnet-5" }
   validator = { provider = "google",    model = "gemini-3.5-flash" }

   [project]
   gate_commands = [ ... this repo's real gate, in order ... ]
   conventions_note = "Read CLAUDE.md; <project-specific rules workers must know>."
   test_pattern = '...'   # omit for the Python default: ^(?:async\s+)?def\s+(test_\w+)
   ignore_checks = ["validator", "<any conditional advisory checks>"]
   ```

   No secrets here, ever. `gate_commands` are what a worker must run
   green before committing; `test_pattern` needs exactly one capture
   group (the test name) — non-Python projects set their own.
   `ignore_checks` entries are **check names** (the job name GitHub
   reports, e.g. `review`), not workflow filenames — the pilot's first
   worker PR was REJECTed on exactly this confusion (opn-mcp#22).
2. **`.worktrees/`** in `.gitignore`.
3. **The advisory validator CI job** — copy the `validator` job from this
   repo's `.github/workflows/ci.yml`, adjusting: `needs:` to the target's
   required check name, and the install line. Keep `continue-on-error:
   true` and do **not** add it to required checks until its judgment has
   earned trust on your PRs.
4. **`GEMINI_API_KEY` secret** on the repo (free-tier AI Studio key;
   ADR 0004): `gh secret set GEMINI_API_KEY --repo <owner/name> --body ...`
   from a shell holding it. Without it the job skips politely — as it
   also does on fork PRs, which receive no secrets.

## Installing the framework

- **In CI**: `uvx --from git+https://github.com/vpciii/agent-framework
  agent-framework-validate ...` — requires this repo to be readable from
  the target's CI (public, or a read PAT).
- **Locally** (for dispatching workers): `uv tool install
  ~/Developer/agent-framework` or add it as a dev dependency; both
  console commands (`agent-framework-worker`, `agent-framework-validate`)
  and the `python -m` forms work. Run them **from the target repo's
  root** — config, specs, and worktrees resolve from cwd.

## The first task

Worker tasks come from the target's own artifacts: draft a small
`specs/<slug>/` (spec + tasks) under the target's methodology, get it
signed off, then from the target root:

```
agent-framework-worker <slug> <task-id> --session-arg=--dangerously-skip-permissions
```

Outcomes: exit 0 = PR opened (with its `Satisfies:` declaration, facing
the advisory gate); 2 = the worker escalated (read
`specs/<slug>/escalations/`); 3 = timeout/error (worktree preserved).

Task-brief authoring lessons (paid for in this framework's own repo):
put **all** expected file changes in `Touches` — including the spec's
Traceability row — or the worker won't make them; name the test-harness
pattern to follow; state what must NOT be modified; for tests-only
tasks, say that behavioral surprises are escalation material, not fixes.

## What stays framework-side

The framework repo owns the gate semantics (its ADR 0005), the brief
format, the verdict schema, and these docs. A target repo owns its
config, its CI wiring, its specs, and every merge decision — the human
is author of record in both places.
