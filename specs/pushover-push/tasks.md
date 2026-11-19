# Tasks: The phone push goes through Pushover, encrypted before it leaves the Mac

- **Status:** Draft
- **Spec:** ./spec.md

PR-sized tasks for the spec, which has no separate plan (its *Approach*
is the plan). Each task traces to ≥1 success criterion — the tests it
must make pass cite those ids — and replaces its `*(pending)*`
Traceability rows as its tests land. Mark a task `[x]` with its merged
PR number when done. Task PRs carry a `Satisfies:` declaration and name
`specs/pushover-push/` in their body.

**DAG:** T-1 → T-2 → T-3, one at a time. T-1 and T-2 both change
`alerts.py`.

**Criterion coverage:** SC-1, SC-2, SC-3, SC-4, SC-6, SC-7, SC-8 → T-1 ·
SC-5 → T-2 · SC-1 → T-3 (the live half: a phone that reads it).

**One departure from the spec, to be accepted with this list.** The
spec's fifth answered question says the worker builds this from a
one-task list. Here it is two worker tasks and one done with vpc. The
nine tasks dispatched for `specs/dispatch-from-issue` were written for
about 300 lines and came back at 289 to 701, tests included. This work
is a sender with its encryption and eight criteria's tests, plus a
configuration setting and the worker's use of it; as one task it would
land near the top of that range. Split, the sender (T-1) can be read on
its own, and the part that decides what text may leave (T-2) is small
enough to read line by line. T-3 exists because the spec's live check
needs vpc's phone and `agent-framework.toml` is a protected path.

**Tried before being written down.** The encryption below was run on
this Mac with a throwaway key before this list was drafted: the
`cryptography` package from the lockfile produced a field that the
`openssl` program decrypted and `gunzip` read back. Nothing in T-1 or
T-2 needs a program the worker's sandbox refuses, or any network beyond
the package index.

**Names fixed here so each brief stands alone:** the environment names
`AF_PUSHOVER_TOKEN`, `AF_PUSHOVER_USER`, `AF_PUSHOVER_KEY`; the
endpoint `https://api.pushover.net/1/messages.json`; the report line's
label `pushover`; the setting `[alerts] push_detail`, `"pointer"` or
`"full"`.

---

### [ ] T-1 — The Pushover sender: encrypted, reported on its own line, never able to change an outcome
- **Satisfies:** SC-1, SC-2, SC-3, SC-4, SC-6, SC-7, SC-8
- **Depends on:** —
- **Touches:** `src/agent_framework/alerts.py`, `pyproject.toml`,
  `uv.lock`, `tests/conftest.py`,
  `tests/orientation/test_pushover.py` (new),
  `tests/worker/test_confinement.py`,
  `specs/pushover-push/spec.md` (Traceability rows)
- **Brief:** Add Pushover as a second push beside the Home Assistant
  one, inside `notify`, so that the worker, the nudge and the dispatch
  tick gain it without any of them changing. **What is sent.** One
  `POST` of form fields to the endpoint: `token`, `user`,
  `encrypted=1`, `title`, `message`, and, when the alert has an issue,
  `url` (the issue's address) and `url_title` (fixed wording). The
  title is what the Home Assistant push uses as its title; the message
  is the short line `notify` is given, without the issue's address
  appended — the address travels as `url`. `notify` also gains an
  optional longer text, the detail; when given, the Pushover message is
  the short line, a blank line, and the detail. The Home Assistant push
  is never given the detail: what it sends is exactly what it sends
  today. No caller passes a detail in this task. **Encryption.** Each
  of `title`, `message`, `url` and `url_title` separately: gzip the
  UTF-8 text; a fresh random 16-byte IV; AES-256-CBC with PKCS7
  padding under the 32-byte key; HMAC-SHA256 over the IV followed by
  the ciphertext, with the same key; base64 of IV, ciphertext and HMAC
  joined in that order. AES comes from the `cryptography` package:
  make it a direct dependency with `uv add cryptography` and commit the
  lockfile, in which no package's version may change. **Limits.**
  Before encrypting, cut the message to 1,024 characters, the title to
  250, the link to 512 and the link's title to 100; a cut message ends
  with a fixed mark saying it was cut, inside the limit. **When it is
  sent, and what the report says.** `AlertReport.lines()` keeps its
  first two lines exactly as today — the GitHub issue, then
  `phone push:` for Home Assistant — and gains a third, labelled
  `pushover:`, only when at least one of the three environment names is
  set. With none set there is no third line and nothing else changes.
  With all three set and the key 64 hexadecimal characters: one
  request, and the line says `sent` when the answer is HTTP 200 whose
  JSON has `status` 1. With any of the three missing, or the key not 64
  hexadecimal characters: no request, and the line says `skipped:` and
  names which name is missing or malformed — the name, never a value.
  When the alert is quieted because its issue is already open: no
  request, and the line says what the Home Assistant line says. Any
  other answer — HTTP 200 with another `status`, 4xx, 429, 5xx, a
  timeout, no connection — is `failed:` followed by the HTTP status or
  the kind of error and nothing else: not the response's body, not the
  request, not the error's own text. One attempt, ten seconds, no
  retry. `notify` still never raises. **Where the three values may
  appear.** Only in the request. Read them from the environment at the
  moment of sending. **Tests never reach Pushover.** Extend the
  suite-wide guard in `tests/conftest.py` to remove the three names for
  every test, as it removes the webhook's; tests that exercise the
  sender set marker values themselves and pass a fake in place of the
  network call.
- **Done when:** tests citing SC-1 show one `POST` to the endpoint
  with the token, the user key and `encrypted=1`, that code in the test
  which reverses the scheme (checks the HMAC, decrypts, gunzips)
  recovers the title, the message, the link and the link's title, that
  two sends of the same text differ, and that a quieted alert makes no
  request; tests citing SC-2 show the request's body holds none of the
  title, message or link as plain text, and that a missing key and a
  malformed key each make no request, say `skipped` with the name, and
  leave the Home Assistant push sent; tests citing SC-3 show that with
  the three names set to marker strings none appears in any log record,
  any report line or the issue's body, including when the fake network
  call raises an error whose text contains the whole request, and that
  `session_env` given an environment holding the three names returns
  none of them; tests citing SC-4 show the decrypted link is the
  issue's address and the decrypted message does not contain it, and
  that an alert whose issue could not be opened sends no `url` field;
  tests citing SC-6 show that for an answer of 400, of 429, of 500, of
  200 with `status` 0, and for a call that times out, `notify` returns
  normally with a `failed` line and exactly one request was made, and
  that a worker run whose escalation meets a failing Pushover ends with
  the same outcome as one with Pushover unset; tests citing SC-7 show
  that with only the webhook set `lines()` is today's two lines, that
  with both set both are sent and there are three lines, and
  `tests/orientation/test_alerts.py` passes unmodified; a test citing
  SC-8 shows a detail of 3,000 characters decrypts to a message of at
  most 1,024 characters ending with the cut mark. The gate passes.

### [ ] T-2 — What a push may say: `push_detail`, and the worker's question
- **Satisfies:** SC-5
- **Depends on:** T-1
- **Touches:** `src/agent_framework/project.py`,
  `src/agent_framework/worker/orchestrator.py`,
  `tests/test_project_config.py`,
  `tests/worker/test_push_detail.py` (new),
  `docs/adoption.md`,
  `specs/pushover-push/spec.md` (Traceability rows)
- **Brief:** The project configuration gains an optional `[alerts]`
  table with one field, `push_detail`: `"pointer"` (the default, also
  when the table is absent) or `"full"`. Load and check it the way
  `[dispatch]` is loaded: an unknown field, a value of the wrong type
  and any other string are each refused when the file is loaded. In the
  worker, an escalation's alert passes the worker's question — the
  result's detail — to `notify` as the detail when `push_detail` is
  `"full"`, and passes none otherwise. No other alert passes a detail:
  not a timeout, not the spend limit, not a refused handoff, not
  anything the nudge or the dispatch tick raises. `agent-framework.toml`
  is a protected path and is not changed by this task. In
  `docs/adoption.md`, beside what it says of the webhook: the three
  environment names, that the push is off until all three are set, and
  what `push_detail` means and why a project that handles sensitive
  data leaves it alone (ADR 0011).
- **Done when:** tests citing SC-5 show that with no `[alerts]` table,
  and with `push_detail = "pointer"`, an escalation's decrypted
  Pushover message holds none of a marker placed in the worker's
  question; that with `push_detail = "full"` it holds the marker and
  the Home Assistant push sent for the same alert does not; that with
  `"full"` a timeout's and a refused handoff's decrypted messages hold
  nothing beyond the short line; and that `push_detail = "everything"`,
  `push_detail = 1` and an unknown field in `[alerts]` are each refused
  when the configuration is loaded. The gate passes.

### [ ] T-3 — Delivery: the three values, this repository's setting, the docs, the live check
- **Satisfies:** SC-1
- **Depends on:** T-2
- **Touches:** `agent-framework.toml`, `docs/architecture.md`,
  `specs/pushover-push/spec.md` (Status, the live check's record),
  `specs/pushover-push/tasks.md`; outside the repository: the env file
- **Brief:** Not for dispatch; done with vpc. In order: (1) vpc copies
  the application token, the user key and the encryption key from
  1Password into the env file under the three names; none is typed
  into a chat, a commit or an issue; (2) one alert sent by hand from
  the main checkout, with `push_detail` still at its default, and what
  the phone shows; (3) `[alerts] push_detail = "full"` in this
  repository's `agent-framework.toml`, by vpc's own pull request, since
  the file is a protected path; (4) the spec's live check, each line
  recorded in the spec with its date; (5) `docs/architecture.md` — the
  alerts row, and the three names and the Pushover account as settings
  outside the repository.
- **Done when:** the four lines of the spec's live check are recorded
  as seen; `docs/architecture.md` describes both pushes and where their
  settings live; and the pull request that records it marks the spec
  `Implemented`. SC-1 is claimed for the live half — a phone that reads
  the encrypted message; its tests are T-1's.
