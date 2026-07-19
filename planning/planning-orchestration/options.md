# Options: where planning-phase orchestration lives

- **Status:** Converged — Option C (vpc, 2026-07-19); see `bet.md`
- **Date:** 2026-07-19
- **Author:** Claude (draft) — vpc is author of record

> At least two genuinely different approaches, kept alive until the last
> responsible moment (planning.md §3). The chosen option's rejected
> siblings become the ADR's "alternatives considered" (methodology.md §1).

## The decision

We want agent leverage for the planning phase (divergent options,
skeptic pressure, pre-mortems — the practices in `planning.md`), with
output the other frameworks can consume: `planning/<slug>/` artifacts
converging to a `spec.md` that agent-framework's chief picks up. The
choice being forced: **how heavy is the harness, and which repo owns it?**

Common to all options (not in dispute):

- The canonical planning artifacts are the only interface — the tool
  reads and writes `planning/<slug>/` and nothing else, per
  `planning.md`'s "optional planning tools are welcome but disposable."
- The human makes the bet and signs off the spec; agents draft and
  pressure-test, never accept.
- The **spec-stage adversarial gate** already sketched in
  agent-framework's design doc belongs to agent-framework regardless of
  this decision — it is the receiving end of the handoff, not part of
  the planning tool.

## Options

### Option A — Extend agent-framework with planning-phase roles

- **What** — Add design-mode role slots to the existing framework
  (roughly: a framer drafting the brief, a pool of divergers each
  producing one option from a different stance/model, a skeptic writing
  the PR-FAQ's hard questions, a red team running the pre-mortem), bound
  by the same roster, reached through the same provider adapters.
- **Attractive because** — Reuses the machinery that already exists
  (roster, adapters, artifacts-as-protocol discipline); one repo, one
  roster; cross-model divergence comes free — different lineages
  naturally produce genuinely different options; the spec-stage
  adversarial gate and the planning pipeline land in one coherent design.
- **Trade-offs / risks** — Stretches the repo's identity: the dev loop is
  a convergent, machine-gated conveyor; the planning loop is divergent,
  low-volume, and human-in-the-loop at every step. Different loop shapes
  in one harness invite coupling. Also front-loads work onto a nascent
  codebase that hasn't shipped its core loop yet.
- **Wins when** — Cross-model divergence proves essential and the
  roster/adapter layer is stable enough to carry a second loop shape.

### Option B — A separate sibling framework (its own repo)

- **What** — A new repo (e.g. `design-framework`) that orchestrates the
  planning practices and converges to a `spec.md`; agent-framework
  consumes the handoff. Mirrors the `planning.md` / `methodology.md`
  document split with a tool split.
- **Attractive because** — Clean boundary at the spec, matching the
  methodology's own seam; each harness stays disposable independently;
  neither repo's loop shape constrains the other.
- **Trade-offs / risks** — Duplicates the roster/adapter machinery or
  forces its premature extraction into a shared library; a second repo's
  maintenance overhead while the first is still nascent; fragmentation
  before either has proven its core loop.
- **Wins when** — Both loops are proven and the shared machinery is worth
  extracting — i.e., later, as a growth path, not as a starting point.

### Option C — No harness: session-level role prompts (skills/subagents)

- **What** — A set of Claude Code skills / subagent definitions (living in
  `$METHODOLOGY_HOME/templates/`, so any project inherits them) that
  drive a planning session: one command per practice — frame the brief,
  fan out N divergers for the options doc, run the skeptic over the
  PR-FAQ, run the pre-mortem — each writing only the canonical
  `planning/<slug>/` artifacts.
- **Attractive because** — Matches the phase's actual shape: low-volume,
  human-at-every-step, divergence-heavy — a full harness may be ceremony
  here (`planning.md`: "planning is where ceremony metastasizes
  fastest"). Ships in days, zero new dependencies, and is maximally
  disposable — retiring it loses an editor, not the decision trail.
- **Trade-offs / risks** — Single-vendor by default: no built-in
  cross-model divergence or different-lineage skepticism, which the
  adversarial-review experiment suggests is where much of the value is.
  Nothing machine-checkable; discipline rests on the prompts.
- **Wins when** — The bottleneck is *producing the artifacts at all*, not
  the diversity of the pressure applied to them.

## Comparison

| Option | Cost / appetite | Risk | Reversibility | Notes |
|---|---|---|---|---|
| A — extend agent-framework | Weeks; competes with core-loop work | Medium — identity stretch, coupling | Medium — roles removable, design entanglement lingers | Cross-model free via roster |
| B — sibling repo | Weeks + ongoing second-repo overhead | Medium — duplication or premature extraction | High — delete the repo | Cleanest boundary; best as growth path |
| C — skills over templates | Days | Low — worst case, unused prompts | High — delete the files | No cross-model pressure built in |

## Recommendation

**Start with C, as a deliberate spike with a small appetite** (this is
also `planning.md` §5 — probe the riskiest assumption cheaply). The
assumption to test: does making the planning artifacts cheap to produce
actually get them produced, and do single-model divergers generate
*genuinely* different options? Use it on the next two or three real bets.

Carry forward from the runners-up:

- From **A**: build the **spec-stage adversarial gate** in agent-framework
  now regardless — it is already in that repo's design doc, it is the
  handoff's receiving end, and a different-lineage check at the spec is
  where the experiment says the value concentrates. C + the gate covers
  most of what A offers at a fraction of the cost.
- From **B**: if the spike proves the loop and single-model divergence is
  the limiting factor, graduate to B (sibling repo, roster-bound
  divergers) — not A — and record that as an ADR with this doc as the
  alternatives-considered.

Converge after the spike: keep C, graduate to B, or drop the bet — and
write the ADR either way.
