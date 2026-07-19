# Bet: planning-phase skills spike (Option C)

- **Status:** Placed
- **Date:** 2026-07-19
- **Author:** vpc (decision); Claude (draft)

> Decide how much the work is *worth* before deciding how to do it — fix
> an appetite, not an open-ended estimate (planning.md §4).

## Appetite

One build session for the skills themselves, then **trial on the next
two or three real bets** — no further build investment until the trial
verdict. Scope flexes to fit: if a skill fights the appetite, it ships
as a thinner prompt or not at all.

## Why now

agent-framework's spec-stage adversarial gate is being designed now;
whether planning orchestration feeds it (and from where) shapes that
design. The spike answers the load-bearing questions cheaply before any
harness is built. Delay means the gate is designed with no opinion about
its upstream.

## In / out

**In:** one skill per planning practice (brief, PR-FAQ, options, bet,
pre-mortem) plus a spec-handoff skill; canonical copies in
`$METHODOLOGY_HOME/experiments/planning-skills/` (trial posture, per the
`experiments/` precedent — graduates to `templates/` + ADR or gets
deleted); installed as personal Claude Code skills. Each reads and writes only `planning/<slug>/`
artifacts.

**Out:** any harness (roster, adapters, cross-model dispatch);
CI/machine-checkable gates on planning artifacts; the spec-stage
adversarial gate itself (that is agent-framework work, tracked there).

## Done looks like

After 2–3 real uses we can answer, with the produced artifacts as
evidence:

1. Did making the artifacts cheap to produce get them produced (vs.
   skipped)?
2. Did single-model divergers produce *genuinely different* options, or
   restatements of one idea?

Yes/yes → keep C. Yes/no → graduate to Option B (sibling repo,
roster-bound divergers), ADR with the options doc as
alternatives-considered. No/– → drop the bet; the templates alone stand.

## No-go conditions

- The skills start accumulating harness-like machinery (state, config,
  code) — that is Option B by stealth; stop and decide deliberately.
- The skills write anything outside `planning/<slug>/` (or the drafted
  `specs/<slug>/spec.md` at handoff) — violates the disposability
  contract in planning.md.
