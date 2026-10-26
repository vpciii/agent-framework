# Bet: durable autonomy — D first, A only on evidence

- **Status:** Placed
- **Date:** 2026-10-26
- **Author:** vpc (decision); Claude (draft)

> Decide how much the work is *worth* before deciding how to do it — fix
> an appetite, not an open-ended estimate (planning.md §4).

## Appetite

- **Option D: up to two working sessions** to build, as one
  compact-spec PR (ADR 0024). If it doesn't fit, scope is cut, not the
  appetite.
- **Then a four-week trial** with no further building on this bet.
- **Option A: no capacity at all** until D's trial verdict is written
  down. A's approach is also reopened (the pre-mortem found that
  off-the-shelf scheduled tasks may replace its home-built tick).

## Why now

The July stall cost three months and the project's context — vpc no
longer remembered where it had left off ([brief](brief.md)). D tests the
cheapest explanation for that (losing the thread, not lack of autonomy)
for about two sessions, before anything larger is built. Delay keeps the
stall-and-forget cycle running on every project that adopts the
framework.

## In / out

**In (D):**
- a resume card: where the project stands and the next action, derived
  from the repo's artifacts;
- a weekly nudge carrying it;
- escalations that reach vpc — a Home Assistant push plus a GitHub issue
  as the second channel;
- the cheap worker fixes the pre-mortem's spikes justified: kill the
  session's whole process group on timeout, and turn a timeout into a
  handoff note plus a notification;
- a record of every nudge and escalation, so the trial is measurable.

**Out:** anything that runs work unattended (that is A); local models;
a durable runtime (option C, in reserve); changes to ADR 0004.

## Done looks like

After four weeks, the trial answers two questions with evidence:

1. Were nudges and escalations acted on, and how fast?
2. Did agent-framework keep moving without a re-orientation session?

The written verdict is one of: **D is enough** (stop here), **D + A**
(re-run `plan-options` for A only), or **drop the bet**.

## No-go conditions

- D's build grows past two sessions — stop and cut scope.
- Anything in D starts running work unattended — that is A by stealth;
  stop and decide deliberately.
- A starts before the verdict is written.
