# Verdict: durable autonomy — option D's trial

- **Status:** Decided — D + A
- **Date:** 2026-11-17
- **Decided:** 2026-11-17, signed off by vpc
- **Author:** vpc (decision); Claude (draft)
- **Bet:** [bet.md](bet.md) (Placed 2026-10-26: D first, A only on
  evidence)
- **Trial:** 2026-10-26 to 2026-11-17 — closed six days short of the
  four weeks the bet set (see *Why early*)

> The bet asked for one of three written verdicts: **D is enough**,
> **D + A**, or **drop the bet**. This file is that record. It is added
> beside the frozen planning artifacts, not edited into them.

## Verdict

**D + A.** Keep option D (the resume card, the weekly nudge, the
alerts). Option A — work that runs without vpc at the keyboard — may
now be planned. Per the bet, the next step is to re-run `plan-options`
for A only; nothing unattended is built before that converges.

## The bet's two questions

**1. Were nudges and escalations acted on, and how fast?**

- **Measured — the nudge ran every week.** The launchd log
  (`~/Library/Logs/agent-framework-nudge.log`) shows a run on 2026-11-02,
  2026-11-09 and 2026-11-16 at 08:00, each reporting `github issue:
  updated #60` and `phone push: sent`, after the two set-up runs on
  2026-10-26.
- **Measured — no escalation, timeout or refused alert was ever raised.**
  No issue carries the `escalation`, `timeout` or `refused` label, open
  or closed. So "how fast were they answered" has no data: the alert
  path was never exercised by a real event.
- **Measured — the push got as far as Home Assistant.** For the
  2026-11-16 run, `automation.agent_framework_alert` fired at 08:00:10
  and called `notify.mobile_app_typhone` with the card's next action, no
  error in its trace. Earlier traces are no longer stored. Nothing
  records whether the phone displayed it (pre-mortem disposition 10:
  Home Assistant's success does not confirm delivery).
- **Stated by vpc, 2026-11-17 — "i never saw any alerts".** So the
  nudge did not reach his attention. The second channel could not have:
  the nudge edits issue #60 in place, and GitHub sends no notification
  for an edited issue body.
- **Measured, 2026-11-17 — the path delivers, and the push is easy to
  miss.** A test push through the same webhook at 08:56 arrived on
  vpc's phone. vpc: "it only appears as a push on my phone, it doesn't
  appear in home assistant as a notification like the firewall test
  does, it's easy to miss". The firewall alert latches onto the Home
  dashboard's Alerts section until dismissed; the agent-framework alert
  leaves nothing behind once the push is swiped away. The Monday pushes
  most likely arrived and were missed. Fixed the same day on vpc's
  word: the agent-framework alert now latches onto the same Alerts
  section until dismissed (`docs/architecture.md`, settings outside the
  repository). The trial ran without that fix.
- **Not measurable — whether a nudge was acted on.** The spec defined
  "answered" only for escalations and timeouts (first comment or
  closing). Issue #60 has no comments and is open, and nothing else
  records a response to a nudge.
- **A nudge that was seen would have pointed elsewhere.** Every card
  named "Implement spec regression-claims" as the next action — the
  oldest Approved spec (2026-07-12) — while the work vpc actually did
  from 2026-11-09 was the validator and the worker.

**2. Did agent-framework keep moving without a re-orientation session?**

- **Measured — it moved on 7 of the trial's 23 days.** Merges to `main`
  landed on 2026-10-26, then on 2026-11-09, -10, -12, -13, -15 and -17.
- **Measured — a 13-day gap, 2026-10-27 to 2026-11-08.** The 2026-11-02
  nudge fell inside it and was followed by a further week with no
  activity.
- **Measured — work resumed on a nudge day.** The 2026-11-09 nudge was
  sent at 08:00; the first commit of the restart is at 16:15 the same
  day. Given vpc's statement above, the nudge was not the cause.
- **Stated by vpc, 2026-11-17 — the restart needed re-orientation.**
  "i had to work out where i left off". So the answer to this question
  is no: after a 13-day gap the project did not resume without a
  re-orientation session. The resume card existed and was current, but
  it had not reached him (question 1), so D's remedy for losing the
  thread went untested rather than disproved.

## What the trial showed about the brief's problem

The brief's problem was that the project "only moves while vpc is
driving it". On that, the trial's records are unambiguous: every day
with a merge was a day vpc sat down, and every day he did not was a day
with none. The one merged task pull request known to be the worker's
in the trial is #73 (2026-11-09, per specs/worker-eval); the rest of
the work came from interactive sessions.

D addressed losing the thread. It was never meant to make work happen
unattended (options: "Doesn't make work happen unattended — by
design"), and it did not. That is the case for A, and it does not rest
on D having failed.

## What the trial did not test

- **The alert path under a real event.** No escalation or timeout
  occurred, so there is no response time to report.
- **A stall as long as July's.** The longest gap was 13 days, not three
  months.
- **Whether a share of tasks can finish without vpc.** The brief marks
  this "Suspected … Unmeasured", and it still is. specs/worker-eval
  (Approved 2026-11-15) is the instrument for it.

## Why early

The bet set four weeks, ending 2026-11-23. On 2026-11-17 vpc stated
that he wants unattended dispatch — a run that starts and finishes
without him, whether he hands it a task or an outside trigger starts
it. Six further days of the same records would not change that, so the
verdict is written now. This is a deliberate decision by vpc, recorded
here, not drift past the bet's no-go condition ("A starts before the
verdict is written").

## What this unlocks, and what it does not

- **Unlocked:** planning for A — `plan-options` for A only, then a spec.
- **Not unlocked:** building anything that runs work unattended. That
  waits for A's options to converge and its spec to be approved.
- **Unchanged:** vpc is author of record; unattended work ends at an
  open pull request or a question, never at `main` (brief, *Not the
  problem*).

## Carried into A's options

Already decided by the pre-mortem's dispositions (accepted 2026-10-26),
and binding on whichever option wins:

- A is "first find out whether a scheduled task already does this" —
  compare off-the-shelf unattended execution against a home-built tick
  (disposition 1), and strip connectors and MCP servers from any
  unattended run.
- **The unattended worker never reads text not authored by vpc**, and
  sign-offs count only from vpc's account; this is a trust boundary and
  takes an ADR (disposition 4).
- Process-group kill, resume from the handoff note, exactly-once pull
  request creation (disposition 5); a pinned worker CLI, failure
  classification, an external heartbeat (dispositions 6 / 7).
- The usage-headroom and local-model spikes still stand before A
  (dispositions 2 and 9).

New inputs from vpc on 2026-11-17, to be weighed there, not decided
here:

- **An outside trigger.** A run started by an issue arriving in a
  tracker (YouTrack was the example), as well as by vpc handing over a
  task. This meets disposition 4 head-on: an issue is text the worker
  reads, so who may author a triggering issue has to be settled.
- **Where an unattended run executes.** A runner that is not vpc's Mac
  was raised; the worker's confinement profile is macOS-only (ADR 0007)
  and the brief's frame was "one owner, one host".
- **What exists since October.** A spend limit and a session record for
  every worker session (specs/worker-spend-and-record), the handoff
  check and `refused` alert (ADR 0007), and the approved worker eval.
