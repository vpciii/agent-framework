# Bet: durable autonomy — A1, a dispatch issue starts a worker run

- **Status:** Placed
- **Date:** 2026-11-18
- **Placed:** 2026-11-18, by vpc
- **Author:** vpc (decision); Claude (draft)

> Decide how much the work is *worth* before deciding how to do it — fix
> an appetite, not an open-ended estimate (planning.md §4).

This is the bet for option A1 of the second options round
([options-a.md](options-a.md), Converged 2026-11-17). It sits beside the
first [bet](bet.md), which was placed for option D, is closed by the
[verdict](verdict.md), and is not edited.

## Appetite

**Two weeks, ending 2026-12-02** (vpc, 2026-11-18): one compact spec,
one ADR for the trust boundary, and three or four pull requests.

- **Up to one day of it goes to spikes first**, because the pre-mortem's
  dispositions 2 and 9 say "spike before A" and one of option A1's own
  unknowns decides whether the host works at all:
  - `claude -p` started by launchd on defiant authenticates on the Max
    plan and finishes one real task (A1's "unverified");
  - usage before and after that task, set against a week of interactive
    use (pre-mortem spike 2);
  - defiant's memory and its other jobs while a worker runs (spike 9).
- **If the appetite runs short, nothing structural is cut** (vpc,
  2026-11-18). The tick, the lock, the author check, resume from a
  handoff note, exactly-once pull request creation, the heartbeat and
  the pinned CLI all stay; the depth of the docs and the detail of
  failure classification give way first. If that is still not enough,
  the bet stops at the no-go below. It is not extended.

## Why now

- **Every run still needs someone at a keyboard.** The verdict found
  that every day with a merge in the trial was a day vpc sat down, and
  vpc said on 2026-11-17 that he wants unattended dispatch.
- **The worker has now shown it finishes tasks.** On 2026-11-17 and
  2026-11-18, six worker-eval tasks dispatched by hand reached six
  merged pull requests with no interactive rework, for $5.68 reported,
  and the worker eval's first baseline was ready for review on 6 of 6
  cases for $2.99 (`specs/worker-eval/tasks.md`). In October the worker
  had finished three tasks, ever; the contrarian's case in the options
  round rested on that.
- **The one alert that fired was the dispatcher's mistake, not the
  worker's**, and it reached vpc's phone. The alert path the trial never
  exercised has now been exercised once.
- **What it displaces:** the loop that sends a REJECT back to the worker
  to revise, and YouTrack intake. Both are agreed to come after A1, in
  that order. Until the first exists, an unattended run that draws a
  REJECT still waits for vpc.
- **What waiting costs:** nothing breaks. The cost is that the next
  spec's tasks are dispatched the way these six were, by someone sitting
  down to do it.

## In / out

**In — the first version, on defiant:**

- a launchd tick that looks for open issues labelled `dispatch`;
- an issue counts only if vpc's account opened it and its body is
  `<spec-slug> <task-id>`; code reduces it to those two values and the
  session never reads the issue;
- the tick runs today's worker command, one run at a time, under a lock
  that names its process;
- a killed or timed-out run can be retried: the retry resumes the
  existing worktree and branch from the handoff note instead of refusing
  them, and a pushed branch with no pull request gets its pull request
  opened once (pre-mortem disposition 5);
- a stall is visible: an outside heartbeat, an alert after repeated
  failures, the worker CLI pinned to a version (dispositions 6 and 7);
- a kill switch: remove the label, or unload the agent;
- the trust boundary written as an ADR, with options A2, A3 and A4 as
  its alternatives considered (disposition 4).

**Out:**

- any trigger other than vpc's own `dispatch` issue — no YouTrack, no
  webhook, no `tasks.md` change that dispatches itself;
- any text from outside `origin/main` reaching the session;
- a runner that is not a Mac, or runs while defiant is off or asleep;
- sending a REJECT back to the worker to revise (the next spec);
- more than one run at a time;
- the trigger and runner seams of option A3, and its four proposed
  glossary terms;
- auto-merge of any kind. vpc merges, as now.

## Done looks like

- **The signal:** vpc opens a `dispatch` issue from his phone, away from
  any keyboard, and a pull request for that task is open when he next
  looks, with CI and the validator's verdict on it — or an alert with
  the worker's question is on his phone.
- **Enough to judge it:** three tasks started that way within the two
  weeks, each ending in a pull request or an alert, none needing a
  terminal on defiant.
- **Recovery shown, not assumed:** one run killed on purpose mid-session
  is retried from an issue and ends in exactly one pull request.
- **Silence shown to be loud:** with the tick unloaded, the missing
  heartbeat raises an alert.

Then renew toward the REJECT loop and intake, or walk away.

## No-go conditions

- **`claude -p` under launchd on defiant does not authenticate on the
  Max plan, or the spike shows unattended runs starve interactive use.**
  Stop before the spec; reopen the host (enterprise, or API credits
  under the spend limit, per disposition 2).
- **The session would have to read the issue's text**, or anything else
  not on `origin/main`, for the design to work. That is the trust
  boundary; stop and decide it deliberately.
- **Resume from a handoff note turns out to need a redesign of the
  worktree and branch handling** rather than an extension of it. Stop
  and re-scope with vpc; do not ship the tick without recovery.
- **Two weeks pass without the signal above.** Stop and write down why;
  no extension without a new bet.
- **Any step would merge, or would act as vpc's GitHub account beyond
  what the worker's token does today.** Stop.
