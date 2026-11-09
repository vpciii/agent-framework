# Architecture — current shape

The system as it exists *now*. The ADRs say why; this says what. Update in
the same PR as any structural change (methodology §2). The one exception
is *Settings outside the repository* below: no PR carries those changes, so
that section is updated promptly after one (methodology ADR 0027).

The implemented slices: the **model-roster substrate**, the **validator
agent**, the **worker agent**, the **roster currency check**, and
**orientation and alerts** (resume card, nudge, alerts). The chief does not exist as code — per
ADR 0004 its seat is a human-driven interactive session; the worker is
orchestrated headless Claude Code (`claude -p` behind a seam), not a
dispatch through the provider adapters.

```
                      roster.toml           env (ANTHROPIC_API_KEY,
                 (role → provider,model)         GEMINI_API_KEY)
                          │                          │
                          ▼                          ▼
  dispatch(roster, role, Request) ──► ProviderRegistry ──► AnthropicProvider
        ▲                                   │              GoogleProvider
        │ single-shot Request/Response      └── name → adapter (thin, the
        │ (prompt + tools in,                   only vendor-SDK imports)
        │  text + tool_calls out)
        │
  validator core (hermetic — no network, no repo access)
  ┌─────────────────────────────────────────────────────┐
  │ EvidenceBundle ─► checks.py ──findings──► Reject    │
  │   (value in)      (deterministic,        (free)     │
  │                    code, free)                      │
  │                        │ clean                      │
  │                        ▼                            │
  │                   judgment.py ──defect──► Reject    │
  │                   (one dispatch,                    │
  │                    return_verdict tool)             │
  │                        │ clean                      │
  │                        ▼                            │
  │                   Pass.from_evidence                │
  │                   (uncited PASS unconstructible)    │
  └─────────────────────────────────────────────────────┘
        ▲                                    │
        │ EvidenceBundle                     │ Pass | Reject (JSON)
        │                                    ▼
  collector.py (edge: gh pr view/diff,   __main__.py (CLI:
  contents API — one runner seam)        python -m agent_framework.validator <pr>,
                                         exit 0 PASS / 1 REJECT)
```

## Components

| Component | Where | Role |
|---|---|---|
| Roster | `roster.py` | Binds roles (chief/worker/validator) to `{provider, model}`; rejects secrets in config (ADR 0001) |
| Provider interface | `providers/base.py` | `Request`/`Response`/`ToolDef`/`ToolCall` + `Provider` Protocol — one shape across vendors; optional `ModelCatalog` / `ModelProbe` protocols for listing served models and reporting routing |
| Adapters | `providers/anthropic.py`, `providers/google.py` | The only vendor-SDK imports; thin normalization |
| Registry + dispatch | `providers/registry.py`, `dispatch.py` | Role → adapter → invoke; typed errors, no silent fallback |
| Validator core | `validator/{bundle,checks,judgment,gate,verdict}.py` | The cite-the-test gate (ADR 0005): deterministic before model; verdicts cite, never assert |
| Validator edges | `validator/{collector,__main__}.py` | Bundle assembly from a PR via `gh` (one fakeable seam; `Satisfies:` declaration is the claim channel; the claimed criteria's text and the task block are read from `specs/<slug>/` at the PR's base commit; test files are the project's `test_paths`); CLI for the human consumer |
| Worker core | `worker/{types,brief,worktree,confinement,session,orchestrator,handoff}.py` | One task → one gated PR: self-contained brief, isolated worktree cut from a freshly fetched `origin/main`, headless `claude -p` session under the confinement profile (roster's worker model, hard timeout, allowlisted environment), `.worker-result.json` contract (the file is recorded in the repository's `info/exclude` when a worktree is created, so no session can commit it), PR with the Satisfies declaration / escalation artifact / preserved-tree timeout. Never merges; a timeout kills the session's whole process group, writes a handoff note and raises a `timeout` alert; an escalation also raises an `escalation` alert; a refused handoff raises a `refused` alert |
| Handoff check | `worker/handoff_check.py` | What a session may not hand back, checked over git: a spec's text outside its Traceability table, a tasks file beyond a checkbox, a protected path, a deleted test file (ADR 0007). Returns findings; the orchestrator runs it on every completed session before pushing, and any finding refuses the handoff |
| Worker edge | `worker/__main__.py` | CLI: `python -m agent_framework.worker <slug> <task>` — exit 0 PR / 2 escalated / 3 timeout-error / 4 handoff refused, composable with the validator's 0/1 |
| Roster currency check | `currency/{check,issue,__main__}.py` + `.github/workflows/roster-currency.yml` | Weekly (and on demand): each bound model must be in its provider's catalog — failing / unchecked / advisory findings, one `roster-currency` tracking issue. Never in the per-PR gate (ADR 0005); Anthropic via Workload Identity Federation, API-key fallback |
| Resume card | `status/{card,__main__}.py` | `python -m agent_framework.status`: where the project stands + one next action, from the artifacts (and open PRs / alert issues via `gh`, or a stated "unavailable") |
| Alerts | `alerts.py` | One GitHub issue per alert key (labelled `escalation` / `timeout` / `refused` / `status`) as the record, plus a best-effort Home Assistant webhook push (`AF_HA_WEBHOOK_URL`, env only); never raises — each channel's outcome is reported |
| Nudge | `nudge.py` | `python -m agent_framework.nudge`, weekly via launchd: resume card → the `status` issue, next action → vpc's phone. Imports nothing from the worker |
| Artifact parser | `artifacts.py` | The one reader of `spec.md` / `tasks.md` text (task block, criterion text, and the comparisons the handoff check makes) — shared by the worker's brief, the validator's collector and the handoff check |
| Shared seam | `proc.py` | The one subprocess runner both edges shell out through; failures carry stderr |
| Project config | `project.py` + `agent-framework.toml` | Per-repo contract: gate commands, conventions note, test-citation pattern, test paths, ignore-checks, and how far worker sessions are widened (session paths, hosts, environment names; protected paths). Defaults = this repo's conventions; invalid patterns unconstructible. Adoption: `docs/adoption.md` |
| Spec-coverage checker | `scripts/check_spec_coverage.py` | CI-enforced traceability (ADR 0003); `*(pending)*` rows allowed at `Approved`, forbidden at `Implemented` |
| CI | `.github/workflows/ci.yml` | `uv sync --frozen` → ruff → mypy --strict → pytest → coverage check; required status check on `main`. Plus an **advisory** `validator` job: the cite-the-test gate runs on every PR (never blocking; judgment only when the `GEMINI_API_KEY` secret is set) |

## Execution surfaces (ADR 0004)

Chief + adversarial plan review: interactive sessions (Claude Code / Max,
Antigravity / AI Pro) — not dispatched by this code. Worker:
headless Claude Code, Max while supported, API-key fallback. Validator:
Gemini via `GoogleProvider` (free tier; Vertex fallback). Retrieval/triage
(future): Ollama on the LAN inference server, never on the correctness path.

## Trust boundaries

Where untrusted input enters, and what each AI agent can reach
(methodology §9, ADR 0027: an agent is an actor at a trust boundary).

- **Worker session** (`claude -p` in its worktree) — *reads* the brief
  built from `tasks.md` + `spec.md` (signed-off artifacts) and the target
  repo. *Can reach* only what the **confinement profile** allows (ADR 0007,
  `worker/confinement.py`): restricted mode, a fixed tool list, nothing
  prompts, none of the user's or project's Claude settings, and an OS
  sandbox that fails closed. Its commands write only inside the worktree,
  reach no network host, and read nothing under the home directory but the
  repository and git's user configuration — widened only by the paths,
  hosts and variable names the project declares in `agent-framework.toml`.
  Its environment is an allowlist of the dispatching shell's. No caller can
  pass it arguments. *Output*: commits on its own branch and
  `.worker-result.json`; the orchestrator, not the session, pushes and opens
  the PR, and nothing merges without the human. Before pushing, the orchestrator runs
  the **handoff check** on the session's commits (`worker/handoff_check.py`):
  a changed contract, a protected path or a deleted test file refuses the
  handoff — nothing is pushed, the worktree is kept, and a `refused` alert
  is raised. The orchestrator's own git commands for a worktree a session
  has been in never run a repository hook. macOS only; elsewhere the
  session does not start.
- **Validator judgment** (one model call via `dispatch`) — *reads* the PR's
  diff, changed test files, CI summary and red evidence, plus the claimed
  criteria's text and task block from the spec: untrusted data,
  fenced between `BEGIN/END DATA` markers. *Can reach* nothing: its only
  tool is `return_verdict`, and it holds no token. *Output*: a verdict on
  stdout (the CI log). The PR's diff and tests are **sent to the validator's
  provider** (Google today, per the roster) — on a public repo that is
  already-public data. Advisory only (ADR 0005); fork PRs receive no
  secrets, so the job skips.
- **Collector / alerts / resume card** — plain code over `gh` with the
  caller's token; PR titles and bodies are parsed by regex, never executed.
- **Roster currency workflow** — `issues: write` and `id-token: write`
  (for Anthropic Workload Identity Federation) only; runs on schedule or
  manual dispatch, never on a PR.

## Settings outside the repository

Host and platform settings the system's shape or safety depends on. No PR
carries a change to one, so update this list promptly when one changes
(methodology ADR 0027). Names and ownership only — never a value.

| Setting | Current value (checked 2026-11-09) | Depends on it |
|---|---|---|
| Repository visibility | public | CI installs via `uvx --from git+https://…` in adopting repos (`docs/adoption.md`); sending PR diffs to the validator's provider is not a disclosure |
| Ruleset `protect-main` | active, no bypass actors: changes by PR (0 approvals required), required status check `ci`, no force-push, no deletion | "the human is author of record" — nothing reaches `main` without a PR and green deterministic CI; the `validator` job is deliberately *not* required (ADR 0005) |
| Actions secret `GEMINI_API_KEY` | set (vpc's AI Studio key, free tier — ADR 0004) | the advisory validator job and the Google side of the roster currency check; absent → both skip or report unchecked |
| Actions variables `ANTHROPIC_FEDERATION_RULE_ID`, `ANTHROPIC_ORGANIZATION_ID`, `ANTHROPIC_SERVICE_ACCOUNT_ID` | set (vpc's Anthropic organization) | the roster currency check reaches Anthropic by Workload Identity Federation, with no stored Anthropic secret |
| Plans | Claude Max (worker sessions, interactive chief); Google AI Pro / Gemini API free tier (validator) — ADR 0004 | the cost model of every role; a billing change is an ADR 0004 revisit |
| launchd agent `com.ciganik.agent-framework-nudge` | loaded on vpc's primary Mac, weekly, run from a checkout of this repo | the nudge (`specs/orientation-and-alerts`) |
| `AF_HA_WEBHOOK_URL` | in an env file on vpc's primary Mac (not in the repo) | the phone push; unset → alerts still open issues and report the push as skipped |

## Specs

- `specs/model-roster/` — Implemented (frozen).
- `specs/validator-gate/` — Implemented (frozen).
- `specs/worker-agent/` — Implemented (frozen).
- `specs/verdict-rendering/` — Implemented (frozen).
- `specs/project-portability/` — Implemented (frozen).
- `specs/roster-currency-check/` — Implemented (frozen).
- `specs/orientation-and-alerts/` — Implemented (frozen).
- `specs/regression-claims/` — Approved (not yet implemented).
- `specs/validator-evidence/` — Implemented (frozen).
- `specs/worker-confinement/` — Implemented (frozen).
- `specs/result-file-ignored/` — Implemented (frozen).
- `specs/citation-from-traceability/` — Draft (awaiting sign-off).
