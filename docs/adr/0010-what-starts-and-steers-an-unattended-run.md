# ADR 0010: Only vpc's dispatch issue starts an unattended run, and only `main` steers it

- **Status:** Proposed
- **Date:** 2026-11-18
- **Deciders:** vpc

## Context

Until now a worker run has started in one way: a person types the
dispatch command in a terminal. ADR 0007 drew the boundary around the
session on that footing. The session is confined; the orchestrator, run
by that person, holds the credentials, pushes, and opens the pull
request.

`specs/dispatch-from-issue` removes the person from the start of the
run. A scheduled command on one of vpc's Macs, the dispatch tick, starts
the same worker when vpc opens an issue from his phone
(`planning/durable-autonomy/options-a.md`, option A1; bet placed
2026-11-18). That moves three things across a boundary that had a human
standing on it:

- **The start.** Something on GitHub now causes a process on vpc's Mac
  to run, holding his `gh` token and his Claude login. This repository
  is public: anyone can open an issue, write any text in it, and comment
  on any issue.
- **The instructions.** A worker session does what its brief says. If
  any text an outsider can write reaches the brief, an outsider steers a
  session whose commits the orchestrator pushes. The pre-mortem's
  disposition 4 made this a hard requirement for unattended work: the
  worker never reads text vpc did not author.
- **The code.** The tick runs this repository's own code. Whichever
  commit that is, it runs with no one watching.

The methodology's rule for an agent at a trust boundary applies (its ADR
0027): least privilege; what it reads is data, not instructions; what it
can read, it can publish.

Two facts about this repository shape the decision. Only vpc can merge
to `main`: he is the only account with write access, and the branch
ruleset requires a pull request and a green `ci` check. And the worker
already takes its whole task from two files, `tasks.md` and `spec.md`;
dispatch refuses a task that claims no criterion (#130).

## Decision

We will let a run start with no one at the keyboard under these rules.

1. **One thing starts a run: a dispatch issue.** An open issue labelled
   `dispatch`, whose author is the one account the project's
   configuration names, and whose title is a spec slug and a task id.
   Nothing else starts one — no comment, no reaction, no webhook, no
   tracker, no schedule.
2. **The issue is a pointer, never content.** Code reduces it to two
   values that match a fixed pattern, and checks that they name a task
   on `origin/main`. No other text from any issue reaches a session's
   brief, command line or environment, or any prompt to any model.
3. **`main` is the one line of trust.** What a run does is decided only
   by what is merged on `main`: the task and criteria the brief is built
   from, the project's configuration, and the framework's own code,
   which the tick brings to `origin/main` before each pass. Content
   becomes trusted by vpc merging it and in no other way.
4. **The tick adds no access.** It holds what a hand dispatch holds and
   launches the session under ADR 0007's confinement profile, unchanged.
   What bounds a run with no one watching is what bounds one today — the
   time budget, the spend limit, the handoff check before anything is
   pushed — plus: one run at a time, no retry the tick decides on its
   own, and no merge, ever.
5. **What the tick writes back is its own.** A comment or an alert it
   raises is fixed wording plus values the code computed. It never
   echoes an issue's text.
6. **Anything from outside comes in as a pull request.** A tracker
   issue, a bug report, or any other outside text may become a drafted
   spec or task in a pull request for vpc to merge. It may not become a
   run, and it may not become part of a brief, until he has merged it.
7. **Off until switched on.** A project that names no dispatch author
   has no unattended runs.

## Alternatives considered

- **Rent the run: a cloud scheduled task fired by phone or a tracker
  rule (option A2).** Attractive because the trigger, the scheduler, the
  runner and a phone client already exist, the run survives the Mac
  being off, and a tracker could start one in the first week. Rejected:
  it acts as vpc's own GitHub account with nothing in code limiting
  which branches it can push; it has no per-run spend limit; the handoff
  check would run in CI, after the push to a public repository; the
  tracker's issue text would be the prompt; and it binds the worker to
  one vendor against ADR 0001. To be looked at again if the Mac's uptime
  turns out to be the limit.
- **Build the trigger and runner seams and tracker intake now (option
  A3).** Attractive because a second tracker or host would then be an
  adapter and a line of configuration, and it puts criteria on a bug
  report before a worker sees it. Not taken now: four specs and six to
  eight weeks before the first unattended pull request, for a second
  tracker and host that do not exist yet. Its first slice is this
  decision, and its rule for outside text is rule 6 here.
- **Build nothing; dispatch by hand and count (option A4).** Its case
  was that the worker had finished three tasks ever and a trigger would
  have nothing to feed. Its tally was run alongside instead of in
  front: six tasks dispatched by hand reached six merged pull requests
  (the worker-eval task list's dispatch tally). What it found still
  stands and is recorded as a consequence below: with no revise loop, a
  rejected run waits for vpc.
- **Let the issue's body be the task.** The shortest path from "an issue
  comes in" to "a fix starts". Rejected: on a public repository it hands
  the brief to anyone, and even from vpc it would dispatch work with no
  criterion for the validator to cite.
- **A command in a comment on any issue or pull request.** Familiar
  from other tools. Rejected: it widens what must be parsed from one
  title to every comment by anyone, to gain nothing a dispatch issue
  does not give.
- **Claude Code's GitHub Action.** Considered in the options round and
  rejected there: a long-lived subscription token in a public
  repository's secrets.

## Consequences

**Easier.** A run starts from a phone. The whole question of what an
unattended run was told is answered by reading `main` at one commit.
Outside triggers have a defined way in (rule 6) that does not reopen
this decision. Hand dispatch is untouched, and unloading the tick or
removing the configuration returns the project to it.

**Harder, and accepted.**

- **A Mac holds standing credentials that are used with no one
  present.** They are the same credentials a hand dispatch uses; what is
  new is that nobody is looking when they are used.
- **A merge to `main` is now also a deployment to that Mac.** A change
  to the worker, the tick or the configuration runs at the next pass.
  Review before merging matters more than it did; that includes pull
  requests the worker itself wrote.
- **vpc's GitHub account is the root of trust.** Whoever controls it can
  start runs and merge. That was already true of merging; it is now true
  of running code on his Mac as well.
- **A question is answered by a merge, not a reply.** A worker's
  escalation is resolved by changing the spec or the task on `main` and
  opening a new dispatch issue. Nothing vpc types in an issue reaches a
  session.
- **The author check and the pattern are security controls**, not
  conveniences. A change that loosens either is a change to this
  decision and needs a superseding ADR.
- **Nothing runs while the Mac is off or asleep**, and a run that draws
  a validator REJECT waits for vpc until the revise loop exists.
- **The tick's own comments and alerts are published text.** They are
  kept to fixed wording and computed values so that nothing a session
  read, and nothing an outsider wrote, is repeated by the project's own
  account.

## Adoption impact

A project ADR. For this repository: the dispatch tick and its
configuration (`specs/dispatch-from-issue`), a `dispatch` label and a
`failed` label, a launchd agent on one Mac, and a heartbeat check
outside the repository, each recorded in `docs/architecture.md` when it
exists. For a project that adopts the framework: none until it names a
dispatch author; then the same rules apply to it, and its own `main`
must be one that only its author of record can merge to.

## References

- `specs/dispatch-from-issue/spec.md` — the requirements this decision
  bounds.
- `planning/durable-autonomy/` — `options-a.md` (the four options),
  `bet-a1.md` (the bet), `premortem.md` (dispositions 4, 5, 6 and 7),
  `verdict.md`.
- ADR 0007 — the worker session is confined; the orchestrator holds the
  credentials and checks what comes back. Unchanged by this ADR.
- ADR 0004 — the worker is headless Claude Code on the Max plan.
- ADR 0001 — roles are model-agnostic slots bound by the roster.
- Methodology ADR 0027 — an AI agent is an actor at a trust boundary.

---

> Following the format proposed by Michael Nygard in
> [Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).
