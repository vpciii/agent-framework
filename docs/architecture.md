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
                                         exit 0 PASS / 1 REJECT /
                                         3 could not judge)
```

## Components

| Component | Where | Role |
|---|---|---|
| Roster | `roster.py` | Binds roles (chief/worker/validator) to `{provider, model}`; rejects secrets in config (ADR 0001) |
| Provider interface | `providers/base.py` | `Request`/`Response`/`ToolDef`/`ToolCall` + `Provider` Protocol — one shape across vendors. A request may name one of its tools as its **required answer** and set an output limit; a response says why it stopped (`complete` / `truncated` / `refused` / `other`, plus the provider's own word) and what it used in tokens. The interface carries intent, never a provider's option name; optional `ModelCatalog` / `ModelProbe` protocols for listing served models and reporting routing |
| Adapters | `providers/anthropic.py`, `providers/google.py` | The only vendor-SDK imports; thin normalization. Each enforces a required answer its provider's way (Google: must-call mode restricted to the one tool; Anthropic: structured output with the tool's schema, returned as the call), maps the provider's stop reasons and usage, and raises one typed `ProviderError` for a rate limit, outage, rejected call or missing credentials |
| Registry + dispatch | `providers/registry.py`, `dispatch.py` | Role → adapter → invoke; typed errors, no silent fallback |
| Validator core | `validator/{bundle,checks,judgment,gate,verdict}.py` | The cite-the-test gate (ADR 0005): deterministic before model; verdicts cite, never assert. The judgment names its verdict tool as the required answer; a cut-off, declined or unanswered judgment is a typed `NoVerdictError`, never a verdict; each judgment logs its model, stop reason and token counts. A REJECT's findings are checked as a PASS's citations are: each finding carries quotes, every quote is looked for in the data the model was sent (the diff read one side at a time), and a finding with a quote that is not there is logged and dropped — a defect judgment with no finding left is "could not judge" (`unsupported-finding`), never a REJECT. A citation is a test the spec's Traceability table names, confirmed by code (it exists and its own text contains the criterion's id) — never a test found by scanning for the id |
| Validator edges | `validator/{collector,__main__}.py` | Bundle assembly from a PR via `gh` (one fakeable seam; `Satisfies:` declaration is the claim channel; the claimed criteria's text and the task block are read from `specs/<slug>/` at the PR's base commit, and each criterion's cited tests from the spec's Traceability table at the PR's head; test files are the changed files matching the project's `test_paths` plus every file the table names); CLI for the human consumer — exit 0 PASS, 1 REJECT, 3 when the judgment could not be made (stdout then carries `{"verdict": "none", "reason": …}`) |
| Worker core | `worker/{types,brief,worktree,confinement,session,orchestrator,handoff}.py` | One task → one gated PR: self-contained brief, isolated worktree cut from a freshly fetched `origin/main`, headless `claude -p` session under the confinement profile (roster's worker model, hard timeout, allowlisted environment), `.worker-result.json` contract (the file is recorded in the repository's `info/exclude` when a worktree is created, so no session can commit it), PR with the Satisfies declaration / escalation artifact / preserved-tree timeout. Never merges; a timeout kills the session's whole process group, writes a handoff note and raises a `timeout` alert; an escalation also raises an `escalation` alert; a refused handoff raises a `refused` alert |
| Handoff check | `worker/handoff_check.py` | What a session may not hand back, checked over git: a spec's text outside its Traceability table, a tasks file beyond a checkbox, a protected path, a deleted test file (ADR 0007). Returns findings; the orchestrator runs it on every completed session before pushing, and any finding refuses the handoff |
| Worker edge | `worker/__main__.py` | CLI: `python -m agent_framework.worker <slug> <task>` — exit 0 PR / 2 escalated / 3 timeout-error / 4 handoff refused, composable with the validator's 0/1 |
| Eval cases and scoring | `evals/{case,scorecard}.py` | The eval set's file format (specs/validator-eval-set, in progress): an accepted case is a frozen evidence bundle with its expected outcome and provenance; a seeded-defect case is an accepted case plus an edit of exact replacements, applied at load. Strict and pure — a malformed file, or an edit that does not match exactly once, is an `EvalCaseError` naming the file. Scoring is pure code over a case's expected outcome and the judgment's actual one — passed / wrongly rejected, caught / other reason / missed, and could-not-judge, which is never counted as right or wrong; a result records the model, the date and fingerprints of the judgment's instructions and of the case set, and two results are compared only when their case sets match. No runner yet |
| Roster currency check | `currency/{check,issue,__main__}.py` + `.github/workflows/roster-currency.yml` | Weekly (and on demand): each bound model must be in its provider's catalog — failing / unchecked / advisory findings, one `roster-currency` tracking issue. Never in the per-PR gate (ADR 0005); Anthropic via Workload Identity Federation, API-key fallback |
| Resume card | `status/{card,__main__}.py` | `python -m agent_framework.status`: where the project stands + one next action, from the artifacts (and open PRs / alert issues via `gh`, or a stated "unavailable") |
| Alerts | `alerts.py` | One GitHub issue per alert key (labelled `escalation` / `timeout` / `refused` / `status`) as the record, plus a best-effort Home Assistant webhook push (`AF_HA_WEBHOOK_URL`, env only); never raises — each channel's outcome is reported |
| Nudge | `nudge.py` | `python -m agent_framework.nudge`, weekly via launchd: resume card → the `status` issue, next action → vpc's phone. Imports nothing from the worker |
| Artifact parser | `artifacts.py` | The one reader of `spec.md` / `tasks.md` text (task block, criterion text, the Traceability table, and the comparisons the handoff check makes) — shared by the worker's brief, the validator's collector and the handoff check |
| Shared seam | `proc.py` | The one subprocess runner both edges shell out through; failures carry stderr |
| Project config | `project.py` + `agent-framework.toml` | Per-repo contract: gate commands, conventions note, test-citation pattern, test paths, ignore-checks, and how far worker sessions are widened (session paths, hosts, environment names; protected paths). Defaults = this repo's conventions; invalid patterns unconstructible. Adoption: `docs/adoption.md` |
| Spec-coverage checker | `scripts/check_spec_coverage.py` | CI-enforced traceability (ADR 0003); `*(pending)*` rows allowed at `Approved`, forbidden at `Implemented` |
| CI | `.github/workflows/ci.yml` | `uv sync --frozen` → ruff → mypy --strict → pytest → coverage check; required status check on `main`. Plus an **advisory** `validator` job: the cite-the-test gate runs on every PR (never blocking; judgment only when the `GEMINI_API_KEY` secret is set), from the default branch's code, never the PR's |

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
  stdout (the CI log); a finding reaches it only if every excerpt it quotes
  is in the data that was sent. The PR's diff and tests are **sent to the validator's
  provider** (Google today, per the roster) — on a public repo that is
  already-public data. Advisory only (ADR 0005); fork PRs receive no
  secrets, so the job skips.
- **CI** (`.github/workflows/ci.yml`) — the rule: **code from a pull
  request never runs in a job that holds a secret.** The `ci` job runs the
  PR's code (its tests, its locked dependencies) with no secret, a
  read-only token, and no token left in the checkout. The `validator` job
  holds `GEMINI_API_KEY` and checks out the **default branch**: the
  validator, its dependencies and its roster come from merged code, and the
  PR reaches it only as data through the API — so a PR that changes the
  validator is judged by the merged validator, not by itself. *Residual:*
  on a `pull_request` event the workflow file itself comes from the PR, so
  a PR that edits it can undo this. A worker's commits cannot (the handoff
  check refuses `.github/**`), fork PRs receive no secrets, and no one but
  vpc pushes other branches.
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
| Default workflow token permissions | read-only; workflows cannot approve pull requests | the `ci` job runs a PR's code — `ci.yml` also pins `contents: read` itself, so this setting is a second layer, not the only one |
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
- `specs/citation-from-traceability/` — Implemented (frozen).
- `specs/judgment-reliability/` — Implemented (frozen).
- `specs/finding-evidence/` — Implemented (frozen).
- `specs/validator-eval-set/` — Approved; in progress (T-2 of 6).
