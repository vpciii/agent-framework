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
| Roster | `roster.py` | Binds roles (chief/worker/validator) to `{provider, model}`, with an optional **effort** (`low` / `medium` / `high`; anything else is a roster error); rejects secrets in config (ADR 0001, specs/role-effort) |
| Provider interface | `providers/base.py` | `Request`/`Response`/`ToolDef`/`ToolCall` + `Provider` Protocol — one shape across vendors. A request may name one of its tools as its **required answer**, set an output limit, and carry an effort — intent only, never a provider's option name; a response says why it stopped (`complete` / `truncated` / `refused` / `other`, plus the provider's own word) and what it used in tokens. The interface carries intent, never a provider's option name; optional `ModelCatalog` / `ModelProbe` protocols for listing served models and reporting routing |
| Adapters | `providers/anthropic.py`, `providers/google.py` | The only vendor-SDK imports; thin normalization. Each enforces a required answer its provider's way (Google: must-call mode restricted to the one tool; Anthropic: structured output with the tool's schema, returned as the call), asks for a request's effort its provider's way (Google: the thinking level; Anthropic: the output effort) and sends no such option when the request has none, maps the provider's stop reasons and usage, and raises one typed `ProviderError` for a rate limit, outage, rejected call or missing credentials |
| Registry + dispatch | `providers/registry.py`, `dispatch.py` | Role → adapter → invoke; typed errors, no silent fallback. A role's effort from the roster is put on the request here; a role without one passes the request on untouched. The worker session is not reached this way, so the worker orchestrator refuses a `worker` binding that sets an effort |
| Validator core | `validator/{bundle,checks,judgment,gate,verdict}.py` | The cite-the-test gate (ADR 0008, which supersedes ADR 0005): deterministic before model; verdicts cite, never assert. The judgment checks conformance to the contract only — test honesty, spec conformance, criteria integrity — and is told that a possible bug the task and criteria do not speak to is not a defect (specs/conformance-only-judgment). It is shown the pull request's title and description as the author's own account, inside the data and never as evidence or instructions; and when anything in the data resembles a data marker, the request's own markers carry a tag derived from the data that the data does not contain, so nothing inside the data can end it (specs/pr-description-in-judgment). It names its verdict tool as the required answer; a cut-off, declined or unanswered judgment is a typed `NoVerdictError`, never a verdict; each judgment logs its model, stop reason and token counts. A REJECT's findings are checked as a PASS's citations are: each finding carries quotes, every quote is looked for in the data the model was sent (the diff read one side at a time), and a finding with a quote that is not there is logged and dropped — a defect judgment with no finding left is "could not judge" (`unsupported-finding`), never a REJECT. A citation is a test the spec's Traceability table names, confirmed by code (it exists and its own text contains the criterion's id) — never a test found by scanning for the id |
| Validator edges | `validator/{collector,__main__}.py` | Bundle assembly from a PR via `gh` (one fakeable seam; `Satisfies:` declaration is the claim channel; the title and description are carried whole, the description cut at 20,000 characters; the claimed criteria's text and the task block are read from `specs/<slug>/` at the PR's base commit, and each criterion's cited tests from the spec's Traceability table at the PR's head; test files are the changed files matching the project's `test_paths`, less any the PR deletes, plus every file the table names); CLI for the human consumer — exit 0 PASS, 1 REJECT, 3 when the judgment could not be made (stdout then carries `{"verdict": "none", "reason": …}`) |
| Worker core | `worker/{types,brief,worktree,confinement,session,orchestrator,handoff}.py` | One task → one gated PR: self-contained brief, isolated worktree cut from a freshly fetched `origin/main`, headless `claude -p` session under the confinement profile (roster's worker model, hard timeout, allowlisted environment), `.worker-result.json` contract (the file is recorded in the repository's `info/exclude` when a worktree is created, so no session can commit it), PR with the Satisfies declaration / escalation artifact / preserved-tree timeout. Never merges; a timeout kills the session's whole process group, writes a handoff note and raises a `timeout` alert; an escalation also raises an `escalation` alert; a refused handoff raises a `refused` alert |
| Handoff check | `worker/handoff_check.py` | What a session may not hand back, checked over git: a spec's text outside its Traceability table, a tasks file beyond a checkbox, a protected path, a deleted test file (ADR 0007). Returns findings; the orchestrator runs it on every completed session before pushing, and any finding refuses the handoff |
| Worker edge | `worker/__main__.py` | CLI: `python -m agent_framework.worker <slug> <task>` — exit 0 PR / 2 escalated / 3 timeout-error / 4 handoff refused, composable with the validator's 0/1 |
| Eval cases and scoring | `evals/{case,scorecard}.py` | The eval set's file format (specs/validator-eval-set): an accepted case is a frozen evidence bundle with its expected outcome and provenance; a seeded-defect case is an accepted case plus an edit of exact replacements, applied at load. Strict and pure — a malformed file, or an edit that does not match exactly once, is an `EvalCaseError` naming the file. Scoring is pure code over a case's expected outcome and the judgment's actual one — passed / wrongly rejected, caught / other reason / missed, and could-not-judge, which is never counted as right or wrong; a result records the model, the effort its roster binding asked for (absent means the provider's default), the date and three fingerprints — of the judgment's instructions, of the case set with its answers, and of what the cases sent the judgment (the **inputs fingerprint**, which an answer does not move). A stored result is re-scored against the answers as they are now by the same code (`rescore`), so correcting an answer calls for no new run; two results are compared when their inputs fingerprints match (specs/eval-rescore). |
| Eval run, freeze + edge | `evals/{run,freeze,__main__}.py` | `agent-framework-eval run` judges every case by calling the gate's own `judge` — the same request, tool, parsing and quote check — through the roster's validator role; token counts and the number of findings reported are read from the provider's response by a recording wrapper around the adapter, so nothing in the gate changes. A provider error or an unreadable answer on one case is that case's could-not-judge and the run goes on. Prints the scorecard, writes a result file (never over an existing one). `show` prints a stored result's scorecard and `compare` the cases whose class changed between two results; both class every judgment against the answers in the case set on disk, name the cases whose answer changed since the run, write nothing, and refuse a result whose cases have since changed what they send. `run` is run by a human with a key; no workflow runs it. `freeze <pr>` writes a merged pull request into the set as an accepted case: the bundle is collected as the gate collects it (`collect_bundle` through the `gh` seam, with the project's config) and stored with its provenance; a pull request that is not merged, or that the deterministic stage rejects, is refused and nothing is written; freezing again rebuilds the bundle and keeps the expected answer already in the file. The set (`evals/validator/cases/`) holds 27 accepted cases — every merged task pull request that passes the deterministic stage today; seven of them (`pr-18`, `pr-27`, `pr-28`, `pr-39`, `pr-59`, `pr-81`, `pr-89`) carry a corrected answer, expected to be rejected, because the judgment found a real conformance defect in accepted work — and 9 seeded-defect cases, three each for test honesty, spec conformance and criteria integrity, each a hand-written edit of a few lines over an accepted case; a test puts every case through that stage with no model call, so a case that rots is caught in CI; `.gitattributes` marks the frozen bundles generated. |
| Roster currency check | `currency/{check,issue,__main__}.py` + `.github/workflows/roster-currency.yml` | Weekly (and on demand): each bound model must be in its provider's catalog — failing / unchecked / advisory findings, one `roster-currency` tracking issue. Never in the per-PR gate (ADR 0005); Anthropic via Workload Identity Federation, API-key fallback |
| Resume card | `status/{card,__main__}.py` | `python -m agent_framework.status`: where the project stands + one next action, from the artifacts (and open PRs / alert issues via `gh`, or a stated "unavailable") |
| Alerts | `alerts.py` | One GitHub issue per alert key (labelled `escalation` / `timeout` / `refused` / `status`) as the record, plus a best-effort Home Assistant webhook push (`AF_HA_WEBHOOK_URL`, env only); never raises — each channel's outcome is reported |
| Nudge | `nudge.py` | `python -m agent_framework.nudge`, weekly via launchd: resume card → the `status` issue, next action → vpc's phone. Imports nothing from the worker |
| Artifact parser | `artifacts.py` | The one reader of `spec.md` / `tasks.md` text (task block, criterion text, the Traceability table, and the comparisons the handoff check makes) — shared by the worker's brief, the validator's collector and the handoff check |
| Shared seam | `proc.py` | The one subprocess runner both edges shell out through; failures carry stderr |
| Project config | `project.py` + `agent-framework.toml` | Per-repo contract: gate commands, conventions note, test-citation pattern, test paths, ignore-checks, and how far worker sessions are widened (session paths, hosts, environment names; protected paths). Defaults = this repo's conventions; invalid patterns unconstructible. Adoption: `docs/adoption.md` |
| Spec-coverage checker | `scripts/check_spec_coverage.py` | CI-enforced traceability (ADR 0003); `*(pending)*` rows allowed at `Approved`, forbidden at `Implemented` |
| CI | `.github/workflows/ci.yml` | `uv sync --frozen` → ruff → mypy --strict → pytest → coverage check; required status check on `main`. Plus an **advisory** `validator` job: the cite-the-test gate runs on every PR (never blocking; judgment only when a credential for the validator's provider is available: Anthropic by Workload Identity Federation, or by an `ANTHROPIC_API_KEY` secret when federation is not configured; Google by the `GEMINI_API_KEY` secret), from the default branch's code, never the PR's |

**Changing the judgment: cite a run from before and after.** The eval
measures the validator's judgment on a fixed set of cases
(`agent-framework-eval run`, results under `evals/validator/results/`).
A change to the judgment's instructions, its tool schema, what it is sent
or the validator's model cites a run from before the change and one from
after, compared with `agent-framework-eval compare`. This is a rule for
the author and the reviewer; no code enforces it
(specs/validator-eval-set, R-13). Four full runs are on record. Three
were made on `gemini-3.8-flash`: `2026-11-10-gemini-3.8-flash.json` and
`2026-11-12-gemini-3.8-flash.json`, both while the judgment still hunted
for an unstated edge case, and
`2026-11-12-gemini-3.8-flash-conformance-only.json`, the first for the
judgment as it is now (specs/conformance-only-judgment). The fourth,
`claude-opus-high-full.json`, was made on `claude-opus-5-5` at effort
`high` and is the baseline for the validator the roster binds today
(ADR 0009). Answers were corrected between and after them, and that no
longer matters: all four judged the same inputs, so `show` reads each
against today's answers and `compare` takes any pair. Read that way, the
baseline is 19 of 20 accepted cases passed and 14 of 16 expected rejects
caught: `pr-59` and `pr-81` are missed, and `pr-69` is wrongly rejected,
on a sign-off recorded in the pull request description, which the
validator is not shown. The last Gemini run reads 20 of 20 and 12 of 16.
`pr-18`, `pr-28`, `pr-39`, `pr-59` and `pr-81` are the same kind of
finding — a cited test that verifies less than its criterion says. The
other result files are the 20-judgment checks on four of those cases
that specs/role-effort records.

## Execution surfaces (ADR 0004, ADR 0009)

Chief + adversarial plan review: interactive sessions (Claude Code / Max,
Antigravity / AI Pro) — not dispatched by this code. Worker:
headless Claude Code, Max while supported, API-key fallback. Validator:
`claude-opus-5-5` at effort `high` via `AnthropicProvider`, metered under
a spend cap (ADR 0009); the previous binding, Gemini via `GoogleProvider`
on the free tier, is one roster line away. Retrieval/triage
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
  already-public data. Advisory only; fork PRs receive no
  secrets, so the job skips.
- **Eval run** (`agent-framework-eval run`) — *reads* the eval set in
  `evals/validator/cases/`: frozen bundles of this repository's merged pull
  requests, some with a seeded edit. Each case is **sent to the validator's
  provider** exactly as the gate would send that bundle — the same request,
  the same single `return_verdict` tool, no token. It runs **from a human's
  shell, with the key in that shell, and never from CI**: no workflow names
  the command, and a test checks that. *Output*: a scorecard on stdout and a
  result file a human commits. `freeze` reads a merged pull request through
  `gh` with the caller's token, as the collector does.
- **CI** (`.github/workflows/ci.yml`) — the rule: **code from a pull
  request never runs in a job that holds a secret.** The `ci` job runs the
  PR's code (its tests, its locked dependencies) with no secret, a
  read-only token, and no token left in the checkout. The `validator` job
  holds the provider credentials — the `GEMINI_API_KEY` secret and, for
  Anthropic, an identity token for Workload Identity Federation (or an
  `ANTHROPIC_API_KEY` secret when federation is not configured; never
  both) — and checks out the **default branch**: the
  validator, its dependencies and its roster come from merged code, and the
  PR reaches it only as data through the API — so a PR that changes the
  validator is judged by the merged validator, not by itself. *Residual:*
  on a `pull_request` event the workflow file itself comes from the PR, so
  a PR that edits it can undo this. A worker's commits cannot (the handoff
  check refuses `.github/**`), fork PRs receive no secrets and no identity
  token, and no one but vpc pushes other branches. The Anthropic account's
  spend cap bounds what such a change could cost.
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
| Actions secret `GEMINI_API_KEY` | set (vpc's AI Studio key, free tier — ADR 0004) | the Google side of the roster currency check, and the advisory validator job when the roster binds a Google model (the fallback binding); absent → they skip or report unchecked |
| Actions variables `ANTHROPIC_FEDERATION_RULE_ID`, `ANTHROPIC_ORGANIZATION_ID`, `ANTHROPIC_SERVICE_ACCOUNT_ID` | set (vpc's Anthropic organization) | the roster currency check and the advisory validator job reach Anthropic by Workload Identity Federation, with no stored Anthropic secret. The federation rule's subject prefix is `repo:vpciii/agent-framework:*` with no `ref` claim (changed by vpc on 2026-11-13; it was pinned to `main`, which refused a pull request's token), so any workflow run in this repository can obtain a token — forks cannot. Confirmed the same day: the validator job on pull request 118 exchanged its token and made a judgment |
| Anthropic account spend cap | $100 a month, organization-wide (set by vpc, 2026-11-13 — ADR 0004, ADR 0009) | bounds what the metered validator, and anything holding its credentials, can cost |
| Plans | Claude Max (worker sessions, interactive chief); Anthropic API, metered (validator — ADR 0009); Gemini API free tier (the fallback validator binding and the roster currency check) — ADR 0004 | the cost model of every role; a billing change is an ADR 0004 revisit |
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
- `specs/validator-eval-set/` — Implemented (frozen).
- `specs/conformance-only-judgment/` — Implemented (frozen).
- `specs/eval-rescore/` — Implemented (frozen).
- `specs/role-effort/` — Implemented (frozen). This repository's roster
  uses the setting: the validator runs at effort `high` (ADR 0009).
- `specs/pr-description-in-judgment/` — Approved; the description is shown
  and the data region closed (SC-1 to SC-4). The sign-off rule and the
  eval's cases (SC-5 to SC-8) are not implemented.
