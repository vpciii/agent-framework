# Architecture — current shape

The system as it exists *now*. The ADRs say why; this says what. Update in
the same PR as any structural change (methodology §8).

Two implemented slices: the **model-roster substrate** and the **validator
agent**. The chief and worker roles do not exist as code — per ADR 0004 the
chief's seat is a human-driven interactive session, and the worker (future
slice) will be orchestrated headless Claude Code.

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
| Provider interface | `providers/base.py` | `Request`/`Response`/`ToolDef`/`ToolCall` + `Provider` Protocol — one shape across vendors |
| Adapters | `providers/anthropic.py`, `providers/google.py` | The only vendor-SDK imports; thin normalization |
| Registry + dispatch | `providers/registry.py`, `dispatch.py` | Role → adapter → invoke; typed errors, no silent fallback |
| Validator core | `validator/{bundle,checks,judgment,gate,verdict}.py` | The cite-the-test gate (ADR 0005): deterministic before model; verdicts cite, never assert |
| Validator edges | `validator/{collector,__main__}.py` | Bundle assembly from a PR via `gh` (one fakeable seam); CLI for the human consumer |
| Spec-coverage checker | `scripts/check_spec_coverage.py` | CI-enforced traceability (ADR 0003); `*(pending)*` rows allowed at `Approved`, forbidden at `Implemented` |
| CI | `.github/workflows/ci.yml` | `uv sync --frozen` → ruff → mypy --strict → pytest → coverage check; required status check on `main`. Plus an **advisory** `validator` job: the cite-the-test gate runs on every PR (never blocking; judgment only when the `GEMINI_API_KEY` secret is set) |

## Execution surfaces (ADR 0004)

Chief + adversarial plan review: interactive sessions (Claude Code / Max,
Antigravity / AI Pro) — not dispatched by this code. Worker (future):
headless Claude Code, Max while supported, API-key fallback. Validator:
Gemini via `GoogleProvider` (free tier; Vertex fallback). Retrieval/triage
(future): Ollama on the LAN inference server, never on the correctness path.

## Specs

- `specs/model-roster/` — Implemented (frozen).
- `specs/validator-gate/` — Implemented (frozen).
