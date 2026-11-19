# Spec: The phone push goes through Pushover, encrypted before it leaves the Mac

- **Status:** Approved
- **Approved:** 2026-11-19, signed off by vpc
- **Date:** 2026-11-19
- **Author:** Claude (draft) — vpc is author of record
- **Related ADRs:** ADR 0011 (alert text leaves the machine as a
  pointer or encrypted — accepted with this spec), ADR 0001 (artifacts
  are the coordination protocol — the GitHub issue stays the record),
  ADR 0007 (worker session
  confinement — the session's environment is an allowlist), ADR 0010
  (what starts and steers an unattended run — nothing here lets a phone
  start or steer one)

> This spec is editable while `Draft` / `Under review` / `Approved`.
> When the PR that marks it `Implemented` merges it **freezes** into a
> historical record; a contradiction found later goes to a test, a new
> spec, or an ADR — not back into this file.

## Problem

An alert reaches vpc's phone today through a Home Assistant webhook
(`specs/orientation-and-alerts`, frozen). On 2026-11-19 the first
escalation of a real run (dispatch-from-issue T-5) showed what that
push is worth on the phone:

- It says a decision is needed and not what the decision is. The
  worker's question is only in the GitHub issue.
- Tapping it opens Home Assistant wherever it last was, not the issue.
- The Home Assistant app keeps no list of past notifications, so a
  tapped alert is gone from the phone.

Unattended dispatch makes the push the one thing vpc sees while away,
so it has to carry enough to judge and lead to the record. Putting more
text into it raises a second problem: that text passes through servers
vpc does not run. vpc's rule for this work is that data security
decides the choice. A project such as change-it-forward handles patient
data, and nothing a worker wrote about it may be readable by a
notification service.

## Goals

1. An alert on the phone can be read later, and a tap opens its GitHub
   issue.
2. For a project that allows it, the push carries the worker's question,
   so an escalation can be judged from the phone.
3. No alert text is readable by the service that delivers it.
4. By default a push says only which task needs attention. Carrying
   more is a setting a project turns on.
5. Nothing listens on vpc's network and no firewall rule changes.

## Non-goals

- Answering an alert from the phone. Only a dispatch issue starts a run
  (ADR 0010); this spec adds no way to reply.
- Replacing the GitHub issue as the record. The push stays a nudge that
  may fail without losing anything.
- Moving Uptime Kuma's monitoring alerts. They are vpc's to move.
- The dispatch tick's heartbeat. It goes to Home Assistant and stays
  there (`specs/dispatch-from-issue` R-20).
- Removing the Home Assistant push or its dashboard card.

## Requirements

- **R-1 (MUST)** When the application token, the user key and the
  encryption key are all in the environment, every alert that pushes
  today — an escalation, a timeout, a refused handoff, a failed run, the
  nudge, and the alerts the dispatch tick raises about itself — sends
  one request to Pushover's message API. An alert that is not pushed
  again because its issue is already open (`quiet_if_open`) sends none.
- **R-2 (MUST)** The title, the message, the link and the link's title
  are each encrypted with the encryption key, by the scheme Pushover
  publishes for end-to-end encryption, before the request is built, and
  the request is marked as encrypted.
- **R-3 (MUST NOT)** Send any alert text to Pushover unencrypted. With
  the token and the user key set and the encryption key missing or not
  64 hexadecimal characters, no request is made and the alert's report
  says why.
- **R-4 (MUST)** The three values come only from the environment. None
  appears in the repository, a log line, an alert's report, an issue, or
  the text of an error; and none reaches a worker session's environment.
- **R-5 (MUST)** When the alert has a GitHub issue, its address is the
  push's link, so a tap opens it, and is not repeated in the message.
  When the issue could not be opened, the push has no link.
- **R-6 (MUST)** What a push says is set per project. By default it
  says only what it says today: the kind of alert, the spec and the
  task. With `push_detail = "full"` in the project's `[alerts]` table,
  an escalation's push to Pushover also carries the worker's question.
  Any other value is refused when the configuration is loaded.
- **R-7 (MUST NOT)** Send the worker's question, or anything else beyond
  today's text, through a channel that does not encrypt it. The Home
  Assistant push says what it says today whatever `push_detail` is.
- **R-8 (MUST)** A request Pushover refuses, limits or does not answer
  never changes a run's outcome or a command's exit status. It is tried
  once, and what happened is one line of the alert's report.
- **R-9 (MUST)** The Home Assistant push works as it does today when its
  address is set. With both configured both are sent, and each has its
  own line in the report.
- **R-10 (MUST)** Text longer than Pushover accepts is cut before it is
  encrypted: 1,024 characters for the message, 250 for the title, 512
  for the link, 100 for the link's title. A cut message ends with a mark
  saying so.
- **R-11 (SHOULD)** Every push is sent at normal priority.

## Success criteria

- **SC-1** — With the three values set, an alert makes one POST to
  `https://api.pushover.net/1/messages.json` carrying the token, the
  user key and the encrypted mark; a test that decrypts the title, the
  message, the link and the link's title with the key gets back the
  alert's text. An alert quieted because its issue is open makes no
  request. (R-1, R-2)
- **SC-2** — The request's body contains none of the alert's title,
  message or link as plain text. With the encryption key missing, and
  with one that is not 64 hexadecimal characters, no request is made,
  the report's Pushover line says it was skipped and why, and the Home
  Assistant push is still sent. (R-3)
- **SC-3** — With the three values set to marker strings, none of them
  is in any log line, report line or issue body an alert produces,
  including when the send fails with an error that quotes the request;
  and the environment built for a worker session from one containing
  them holds none of the three names. (R-4)
- **SC-4** — For an alert with an issue, the decrypted link is the
  issue's address and the decrypted message does not contain it. For an
  alert whose issue could not be opened, the request has no link. (R-5)
- **SC-5** — With no `[alerts]` table, an escalation's decrypted message
  holds none of the worker's question. With `push_detail = "full"` it
  holds the question, and the Home Assistant push sent for the same
  alert does not. A `push_detail` of anything else is refused when the
  configuration is loaded. (R-6, R-7)
- **SC-6** — With Pushover answering 400, answering 429, answering 500
  and not answering, a worker run ends with the same outcome and exit
  status as with Pushover unset, exactly one request was made, and the
  report's Pushover line says it failed. (R-8)
- **SC-7** — With only the Home Assistant address set, an alert sends
  what it sends today and its report is today's two lines; the existing
  alert tests pass unmodified. With both configured, both are sent and
  the report has a line for each. (R-9)
- **SC-8** — A question of 3,000 characters produces a decrypted message
  of at most 1,024 characters that ends with the cut mark. (R-10)

## Approach

**One more sender behind the seam that exists.** `alerts.py` already
sends a push through one function type and reports its outcome. This
spec adds a Pushover sender beside the Home Assistant one and lets an
alert go to each configured sender in turn, reporting each on its own
line. `notify`'s callers (the worker, the nudge, the tick) keep calling
it as they do.

**The text an alert carries.** Today a caller hands `notify` one short
line. It will hand over the short line and, optionally, a longer detail.
Only a sender that encrypts receives the detail. The worker passes the
escalation's question as the detail when the project's `push_detail` is
`"full"`; every other caller passes none. A sender that does not encrypt
cannot be given the detail by mistake, because the choice is made in
`notify`, not by each caller.

**Encryption.** Pushover's published scheme, per field: gzip the text,
a fresh random 16-byte IV, AES-256-CBC with PKCS7 padding, HMAC-SHA256
over the IV and the ciphertext with the same key, and the three joined
and base64-encoded. AES comes from the `cryptography` package, which is
already in the lockfile at 49.0.0 as a dependency of the Google SDK's
`google-auth`; this spec names it as a direct dependency. Everything
else is the standard library. Nothing is written by hand that a
library provides.

**Configuration.** Three names in the environment, set in the env file
that holds the webhook address: `AF_PUSHOVER_TOKEN`, `AF_PUSHOVER_USER`,
`AF_PUSHOVER_KEY`. The worker session's environment is an allowlist
(ADR 0007) that passes nothing beginning `AF_`; SC-3 pins that for
these three. `[alerts] push_detail` joins the project configuration the
way `[dispatch]` did: optional, typed, refused when wrong.

**What it costs to check.** The tests decrypt with code written in the
test, so they prove the request is well-formed and holds no plain text.
They cannot prove a phone can read it. That is the live check below.

### Decisions

- *2026-11-19* — Pushover chosen over a Telegram bot, the public
  ntfy.sh, self-hosted ntfy and Bark, by vpc: of those that need no
  server of his and nothing inbound, it is the one whose delivery
  service cannot read the text. Telegram can read bot chats; a free
  ntfy topic is readable and writable by anyone who knows its name, and
  its iPhone app had an open no-delivery bug on iOS 27.

## Rollout and undo

- **Off until configured.** With none of the three names set, alerts
  behave exactly as today (SC-7).
- **vpc's own steps.** Copy the three values from 1Password into the env
  file. To carry the worker's question for this repository, add
  `[alerts] push_detail = "full"` to `agent-framework.toml` by his own
  pull request, since that file is a protected path.
- **Undo.** Remove the three lines from the env file. Nothing else
  changes; the Home Assistant push was never removed.
- **A lost or changed key** makes later pushes unreadable on the phone
  until both ends hold the same key. No alert is lost: each has its
  issue.
- **Live check, recorded here with its date when done:** one alert sent
  to vpc's phone shows a readable title and message; a tap opens its
  GitHub issue; an escalation from a project with `push_detail = "full"`
  shows the question; and the Home Assistant card still shows the short
  line.
- `docs/architecture.md` gains the three names and the Pushover account
  as settings outside the repository; `docs/adoption.md` says how to set
  them and what `push_detail` means.

## Open questions

All five were answered by vpc on 2026-11-19, each as recommended.

- [x] **Does this need an ADR?** Decided: yes — ADR 0011, accepted
  with this spec. The rule "alert text leaves the machine either as a
  pointer or encrypted with a key only vpc holds" constrains every
  later channel and every adopting project, which is more than this
  spec should carry alone.
- [x] **Keep the Home Assistant push alongside?** Decided: yes. It
  costs nothing, the dashboard card is a glanceable sign that something
  waits, and R-7 keeps its text to today's short line.
- [x] **What `"full"` adds.** Decided: the escalation's question only.
  A refused handoff's findings name file paths, and a failed run's
  alert already names its kind in the title.
- [x] **Priority.** Decided: normal for everything (R-11). High
  priority breaks through the phone's quiet hours; an escalation at
  night waits for morning anyway.
- [x] **Who builds it.** Decided: the worker, from a one-task
  `tasks.md` written after this is approved. It is one pull request of
  code and tests with no network beyond the package index.

## Out of scope (for now)

- A desktop client. Pushover's documentation names its iPhone and
  Android apps as supporting end-to-end encryption and does not say the
  desktop client does.
- Retrying a push that failed for a passing reason.
- Emergency priority with acknowledgement, for an alert that must not
  be missed.
- Sending Uptime Kuma's alerts encrypted. Its Pushover integration is
  its own, not this code.

## Traceability

| Criterion | Requirement(s) | Verified by (test) |
|---|---|---|
| SC-1 | R-1, R-2 | *(pending)* |
| SC-2 | R-3 | *(pending)* |
| SC-3 | R-4 | *(pending)* |
| SC-4 | R-5 | *(pending)* |
| SC-5 | R-6, R-7 | *(pending)* |
| SC-6 | R-8 | *(pending)* |
| SC-7 | R-9 | *(pending)* |
| SC-8 | R-10 | *(pending)* |
