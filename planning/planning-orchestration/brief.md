# Problem brief: no orchestration for the planning phase

- **Status:** Exploring
- **Date:** 2026-07-19
- **Author:** Claude (draft) — vpc is author of record

> Solution-free on purpose. Describe the problem; do not name a remedy —
> if a solution creeps in, move it to `options.md` (planning.md §1).

## The problem

The methodology now covers both halves of the work: `planning.md`
defines how to decide *what* to build (brief → PR-FAQ → options → bet →
pre-mortem, converging to a spec), and `methodology.md` defines how to
build it right. Agent support exists only for the second half:
agent-framework orchestrates spec → tasks → PRs → validation. The
planning phase has templates but no agent leverage at all — every
artifact is produced by a single unaided author.

That gap lands exactly where a single author is weakest. The planning
practices exist to force divergence (≥2 genuinely different options,
kept alive late) and adversarial pressure (the skeptic's FAQ, the
pre-mortem). A lone author — human or a single AI session — is the
worst-positioned producer of those: first-plausible-option lock-in and
blind spots are the failure modes `planning.md` itself names as the most
common and most expensive.

## Who feels it

- **vpc**, as the sole planner across projects: producing a genuine
  options doc or pre-mortem solo is high-friction, so the artifacts risk
  being skipped or produced as ceremony rather than as real divergence.
- **The chief agent** in agent-framework: it requires a signed-off
  `spec.md`, and a flawed criterion poisons every task decomposed from
  it (orchestration-design.md, "Two review stages"). Spec quality today
  depends entirely on unaided upstream drafting.
- **Any project adopting the methodology**: the planning templates exist,
  but there is nothing that makes following them easier than skipping them.

## Evidence

- **Measured:** the cross-model adversarial-review trial
  (`$METHODOLOGY_HOME/experiments/adversarial-review/`) found that a
  different-lineage model catches what the author's model misses, and
  that this earns its keep on *design decisions* — which is precisely
  what planning artifacts are.
- **Measured:** agent-framework's own design doc already calls for a
  spec-stage adversarial gate ("challenge the contract… upstream, at the
  spec gate") that nothing currently produces input for or implements.
- **Suspected:** planning artifacts are underproduced relative to specs
  across the repos (agent-framework has six `specs/<slug>/` and, until
  this one, no `planning/<slug>/`). Worth a quick audit before betting.

## Why now

agent-framework is nascent and its validator/adversarial-gate design is
still being shaped. Deciding now whether planning-phase orchestration is
part of that framework, a sibling, or deliberately lighter-weight will
shape the spec-stage adversarial gate's design either way. Deferring
means the gate gets built with no opinion about what feeds it.

## Not the problem

- Replacing the human as author of record — the bet decision (appetite,
  why-now) and all sign-offs stay human, per the methodology.
- Changing the planning practices themselves — `planning.md` and its
  templates are the fixed contract; this is tooling *over* them.
- Automating routine work's planning — trivial changes still go straight
  to a spec or a commit; ceremony must stay scaled to the work.
