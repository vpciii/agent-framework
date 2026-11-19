# ADR 0011: Alert text leaves the machine as a pointer, or encrypted with a key only vpc holds

- **Status:** Accepted
- **Date:** 2026-11-19
- **Deciders:** vpc

## Context

An alert has two parts. Its record is a GitHub issue in the project's
own repository, where the project's own access rules apply. Its push is
a short message to vpc's phone, and a push always travels through
servers vpc does not run: the notification service's, then Apple's.

Until now the push said only that a task needed attention
(`specs/orientation-and-alerts`). The first escalation of a real run,
on 2026-11-19, showed that this is too little to act on from a phone:
the worker's question was only in the issue. The obvious remedy is to
put the question in the push.

That remedy changes what crosses the boundary. A worker's question is
text a session wrote about the code it was reading. For this repository,
which is public, that is harmless. For an adopting project it may not
be: change-it-forward handles patient data, and a worker's question
there could quote a table name, a file path or a line of a fixture. A
notification service would then hold that text, readable by its
operator, by whoever compromises it, and by whoever compels it.

vpc's rule for this work is that data security decides. The channel
compared first, a Telegram bot, can read every bot message. A free
ntfy.sh topic can be read and written by anyone who knows its name. A
self-hosted service would keep the text on vpc's network but needs
either an inbound port or a private network to reach the phone.

Unattended dispatch (ADR 0010) makes this more pressing, since the push
is then the only thing vpc sees while away, and the temptation to put
more into it will recur with every new kind of alert and every new
channel.

## Decision

We will let alert text leave the machine in only two forms.

1. **A pointer.** The kind of alert, the spec and the task, and the
   address of the alert's issue. A pointer may go through any channel.
   It is what every push says unless a project chooses otherwise.
2. **Encrypted with a key only vpc holds.** Anything beyond a pointer —
   today, an escalation's question — goes only through a channel that
   encrypts it on the machine before sending, with a key that exists
   only in the machine's environment and on vpc's own devices. The
   delivering service never has the key.

A project carries more than a pointer only by saying so in its own
configuration. The default is the pointer.

A channel that cannot encrypt this way receives the pointer and nothing
else, whatever the project's setting. The choice is made in one place
in the code, not by each caller.

The keys and tokens a channel needs come only from the environment, as
the webhook address does, and never reach a worker session.

## Alternatives considered

- **Keep every push a pointer.** Nothing sensitive could ever leave.
  Rejected because it leaves the problem that started this: an
  escalation cannot be judged from the phone, and unattended runs make
  that the common case. The pointer stays the default, so a project
  that wants this gets it by doing nothing.
- **Send the question in the clear, and tell sensitive projects to turn
  it off.** Simplest to build. Rejected because the safe state would
  then depend on someone remembering a setting, and the failure is
  silent: text simply arrives somewhere it should not be.
- **Trust the service's own encryption.** Every service encrypts in
  transit and most at rest. Rejected because the service holds those
  keys; "encrypted" would mean readable by the operator.
- **Self-host the notification service.** Keeps all text on vpc's
  network. Rejected by vpc: it needs an inbound port, or a private
  network on the phone, and a server to keep running. It remains
  compatible with this decision — a self-hosted channel that cannot
  encrypt would still receive only pointers.
- **A separate rule per channel, decided as each is added.** Rejected
  because the question is the same every time, and answering it once
  means a new channel is an implementation, not a new argument.

## Consequences

- An escalation can be judged from the phone for a project that allows
  it, and nothing a worker wrote about a sensitive project is readable
  by a notification service.
- Adding a channel is cheaper to reason about: either it encrypts with
  vpc's key and may carry detail, or it carries pointers.
- The encryption key becomes something to look after. If it is lost or
  the two ends disagree, pushes are unreadable on the phone until it is
  set again. No alert is lost, since each has its issue.
- A pointer still discloses that a named task in a named spec needs
  attention, and when. For a project whose spec names are themselves
  sensitive, that is a leak this decision accepts.
- The issue's address in a pointer leads to the full text. That is
  intended: reading it requires access to the repository, which is the
  project's own boundary.
- Two-way use of a channel — answering an alert from the phone — is not
  made easier or harder by this. It is closed by ADR 0010 and would
  need its own decision.
- The Home Assistant push will always say less than the encrypted one.

## Adoption impact

Per-project action only for a project that wants more than a pointer:
it adds `push_detail = "full"` to the `[alerts]` table of its
`agent-framework.toml`. A project that does nothing is on the safe
default. `docs/adoption.md` says so when `specs/pushover-push` is
implemented. The first channel that encrypts is Pushover, built by that
spec.

## References

- `specs/pushover-push/spec.md` — the first encrypting channel; R-6 and
  R-7 are this decision in testable form.
- `specs/orientation-and-alerts/spec.md` — the push as it was; R-9, the
  endpoint and credentials come only from the environment.
- ADR 0007 — the worker session's environment is an allowlist.
- ADR 0010 — nothing a phone sends starts or steers a run.
- Pushover's published end-to-end encryption scheme:
  <https://pushover.net/api>.

---

> Following the format proposed by Michael Nygard in
> [Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).
