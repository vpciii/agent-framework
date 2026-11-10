# Spec: A judgment that cannot be mistaken — a required answer, a stop reason, usage

- **Status:** Approved
- **Date:** 2026-11-09
- **Author:** Claude (draft) — vpc is author of record
- **Related ADRs:** ADR 0001 (model-agnostic roles; the provider interface
  stays thin and vendor-neutral), ADR 0005 (one per-PR gate — still one
  judgment call), ADR 0004 (which surface each role runs on)

> This spec is editable while `Draft` / `Under review` / `Approved`.
> When the PR that marks it `Implemented` merges it **freezes** into a
> historical record (methodology ADR 0027);
> a contradiction found later goes to a test, a new spec, or an ADR —
> not back into this file (methodology §2, §8).

## Problem

The validator's judgment is one model call that must come back as a call
to its `return_verdict` tool. Three things about that call are left to
chance today.

1. **Nothing asks the provider to enforce the answer's shape.** The
   request offers the tool and the prompt asks for it. A model that
   answers in prose instead produces a `JudgmentFormatError`.
2. **The response does not say why it stopped.** A response cut off at
   the output limit, and one a provider's safety system declined, both
   arrive as "no tool call" and raise the same format error. The
   Anthropic adapter caps output at 4,096 tokens, and on current Claude
   models thinking is always on and counts against that cap — so a
   roster edit that binds the validator to a Claude model would hit this
   on ordinary pull requests, and report it as a formatting failure.
3. **A failed judgment looks like a REJECT.** The gate's CLI does not
   catch that error; the process ends with a traceback and exit code 1,
   which is also the code for REJECT. Anything that reads the exit code —
   CI today, a chief later — cannot tell "this PR has a defect" from "the
   gate could not judge".

Token usage is also discarded, so a judgment's cost is unknown.

The model-roster spec deferred this ("streaming, retries/failover, and
cost/token accounting (later)") and the validator-gate plan chose "zero
extension to `Request`/`Response`". That was right for a first slice; the
swap the roster exists to allow is now the thing it does not support.

**A constraint found while drafting.** The obvious fix — force the tool
with the provider's tool-choice option — is not available everywhere: the
current Claude models in this repo's roster reject a forced tool choice
with an error, while Gemini enforces one. So the interface cannot carry
"tool choice"; it has to carry the *intent* and let each adapter enforce
it the way its provider can.

## Goals

1. A caller can say "the answer must be a call to this tool", and the
   provider — not the prompt — enforces it, on both providers.
2. A response says why it stopped, in one vocabulary across providers.
3. A judgment that could not be made is reported as that, with its
   reason, and is never mistaken for a REJECT.
4. Each judgment's token usage is visible.
5. Swapping the validator's model remains a roster edit.

## Non-goals

- Retries or failover. One judgment call per PR (ADR 0005); a judgment
  that could not be made is reported, not repeated.
- A per-role thinking or effort setting in the roster (see *Open
  questions*).
- Streaming, system prompts, multi-turn requests, sampling parameters.
- Recording usage anywhere durable, or pricing it: the run record is a
  separate finding. This spec makes the numbers exist and logs them.
- The fixed data fence in the judgment prompt and unfiltered diffs.
- Changing what a PASS or a REJECT is, or the verdict's JSON shape.

## Requirements

- **R-1 (MUST)** A request can name one of the tools it offers as its
  **required answer**. Naming a tool the request does not offer is an
  error raised when the request is built, before any provider is called.
- **R-2 (MUST)** Each adapter asks its provider to *enforce* a required
  answer, by a means that provider supports for every model the adapter
  serves, and returns the answer as a call to that tool. No model name or
  model-family test appears in adapter code.
- **R-3 (MUST)** A request can carry a maximum output size. When it
  carries none, the adapter's own documented default applies.
- **R-4 (MUST)** A response reports why generation stopped, normalized to
  one of: **complete**, **truncated** (the output limit was reached),
  **refused** (the provider declined to answer), **other** — together
  with the provider's own word for it.
- **R-5 (MUST)** A response reports the tokens the provider counted for
  input and for output, when the provider reports them.
- **R-6 (MUST)** The judgment names its verdict tool as the required
  answer. A response that was truncated, was refused, or carries no
  verdict call raises a typed error that says which of the three it was
  and includes the provider's own stop word. It is never turned into a
  verdict.
- **R-7 (MUST)** The gate's CLI reports a judgment that could not be made
  as exactly that: a JSON object on standard output naming the reason,
  and exit code **3**. No traceback.
- **R-8 (MUST)** For each judgment the gate logs the model that was
  called, the normalized stop reason, and the input and output token
  counts.
- **R-9 (MUST NOT)** The verdict's JSON shape and the CLI's exit codes for
  PASS (0) and REJECT (1) MUST NOT change. The provider interface,
  dispatch, the judgment and the gate name no vendor and no model. Code
  that builds a `Request` or returns a
  `Response` without the new fields — including every existing test fake
  — keeps working unchanged.
- **R-10 (SHOULD)** The delivery PR cites one live judgment through the
  Google adapter (the roster's validator) with the required answer in
  force. The Anthropic adapter is verified against a mocked transport
  only; no Anthropic API key is available to this project today.

## Success criteria

- **SC-1** — Google adapter, mocked transport: a request with a required
  answer and a maximum output size sends function calling restricted to
  that one tool in the provider's "must call" mode, and the size limit;
  the response's stop reason and token counts are reported — a response
  the provider marks as cut off is **truncated**. (R-2, R-3, R-4, R-5)
- **SC-2** — Anthropic adapter, mocked transport: a request with a
  required answer sends that tool's parameter schema as the required
  output format and no forced tool choice; the provider's JSON answer is
  returned as a call to that tool with those arguments; a stop at the
  output limit is **truncated** and a declined request is **refused**;
  token counts are reported; a request without a size limit sends the
  adapter's default, and one with a limit sends that. (R-2, R-3, R-4,
  R-5)
- **SC-3** — Building a request whose required answer is not among its
  tools raises a typed error; no provider is called. (R-1)
- **SC-4** — With a fake provider: the judgment's request names
  `return_verdict` as its required answer; a truncated response, a
  refused response and a response with no verdict call each raise the
  typed error, each message saying which and carrying the provider's stop
  word; none yields a verdict. (R-6)
- **SC-5** — The gate's CLI: a judgment that could not be made prints a
  JSON object naming the reason and exits 3, with nothing on standard
  error that looks like a traceback; a PASS still exits 0 and a REJECT 1,
  with the verdict JSON unchanged. (R-7, R-9)
- **SC-6** — A judgment logs one line carrying the model, the stop reason
  and both token counts. (R-8)
- **SC-7** — A provider fake that returns a response with only text and
  tool calls, and a request built with only a prompt and tools, behave as
  before through dispatch and the gate; the provider interface, dispatch,
  the judgment and the gate modules name no vendor and no model. (R-9)

## Approach

One PR.

- **Interface (`providers/base.py`).** `Request` gains two optional
  fields, `require_tool` (a tool name) and `max_output_tokens`;
  validation in the value makes an unknown `require_tool`
  unconstructible. `Response` gains `stop` (`"complete"`, `"truncated"`,
  `"refused"`, `"other"`; default `"complete"`), `stop_detail` (the
  provider's word) and `usage` (input and output token counts, or none).
  All defaulted, so existing callers and fakes are untouched. The
  interface carries intent — "this tool is the answer" — never a
  provider's option name.
- **Google adapter.** A required answer becomes function calling in
  `ANY` mode restricted to that tool's name; the size limit becomes
  `max_output_tokens`. `finish_reason` maps to `stop` (`STOP` →
  complete; `MAX_TOKENS` → truncated; the safety and prohibited-content
  family → refused; anything else → other). Usage comes from
  `usage_metadata` (output = candidates plus thoughts).
- **Anthropic adapter.** A required answer becomes a structured-output
  format whose schema is that tool's parameters; the JSON text that comes
  back is returned as a call to the tool. This is enforced on every
  current Claude model, including the ones that reject a forced tool
  choice, so the adapter needs no model list. `stop_reason` maps to
  `stop` (`end_turn`, `tool_use`, `stop_sequence` → complete;
  `max_tokens` → truncated; `refusal` → refused; else other). The default
  output limit rises from 4,096 to 16,000: thinking is always on for
  current Claude models and is counted against the limit.
- **Verdict tool schema.** Structured output requires closed schemas, so
  the verdict tool's parameter schema states `additionalProperties:
  false` at both levels. Nothing else about the tool changes.
- **Judgment.** Builds its request with the required answer. One new
  typed error carrying the reason (`truncated` / `refused` /
  `no-answer`) replaces the bare format error for these three cases; the
  malformed-findings checks stay as they are.
- **CLI.** Catches that error (and the existing format error), prints
  `{"verdict": "none", "reason": …, "detail": …}`, exits 3.
- **Logging.** One `INFO` line per judgment from the gate.

### Decisions

- *2026-11-09* — vpc accepted all five open questions as drafted.
- *2026-11-09* — **Correction to R-9 and SC-7, found implementing
  (awaiting vpc's sign-off).** They said no vendor or model name appears
  "outside the adapters". That was never true of the code and cannot be:
  the gate's CLI is the one place that registers the adapters by name
  (ADR 0004), and the roster currency check and the worker's session
  profile name providers by design. The requirement meant the modules
  this spec touches, and now says so: the provider interface, dispatch,
  the judgment and the gate. No behavior is weakened.
- *2026-11-09* — **Provider failures are "could not judge" too (awaiting
  vpc's sign-off).** The most likely reason a judgment cannot be made is
  not a cut-off answer but a rate limit or an outage — and that still
  ended the process with a traceback and exit code 1. Each adapter now
  raises one typed provider error with the vendor's own error chained,
  and the CLI reports it as `"reason": "provider-error"`, exit 3. This
  extends R-7's "a judgment that could not be made" to its commonest
  cause; it adds no retry.

## Rollout and undo

The gate is advisory (ADR 0005). Undo is reverting the PR. Visible
changes: a judgment that could not be made exits 3 instead of 1 (CI's
advisory job treats both as a failed, non-blocking step); the Anthropic
adapter's default output limit is higher, so a Claude-bound role can cost
more per call than before; a validator bound to Gemini is now held to a
tool call by the API rather than by the prompt.

After this repo's CI change of 2026-11-09 the advisory job runs the
merged validator, not the pull request's — so the new adapter code first
runs live on the PR *after* this one merges. R-10's live judgment is
therefore run by hand, with a key, before merge.

## Open questions

All resolved 2026-11-09 (human sign-off).

- [x] **How the Anthropic adapter enforces a required answer.**
  Structured output with the tool's schema, returned as a tool call —
  enforced by the API on every current Claude model. Rejected: offering
  the tool with a strict schema, leaving tool choice automatic and
  re-prompting once, which is not a guarantee and adds a second call.
- [x] **A judgment that could not be made: exit 3** with a JSON reason
  (R-7). A refused or truncated judgment is *not* counted as a REJECT:
  nothing was found wrong with the PR.
- [x] **The Anthropic adapter's default output limit: 16,000.** A default
  for when the caller sets none; the judgment sets none.
- [x] **A per-role thinking / effort setting in the roster: not in this
  spec.** It is a tuning knob, and the eval set it should be tuned
  against does not exist yet. The interface change here does not close it
  off.
- [x] **Verified without a live Anthropic call.** There is no Anthropic
  API key in this project. Transport-level tests are accepted for that
  adapter, and the PR says so.

## Out of scope (for now)

- A durable run record of judgments (model, usage, cost).
- An eval set for the validator's judgment.
- A per-request data fence and filtering what is sent as the diff.
- Posting the verdict on the pull request.

## Traceability

| Criterion | Requirement(s) | Verified by (test) |
|---|---|---|
| SC-1 | R-2, R-3, R-4, R-5 | `tests/test_required_answer.py::test_sc1_google_enforces_the_required_answer_and_reports_stop_and_usage`, `tests/test_required_answer.py::test_sc1_google_stop_reasons_are_normalized`, `tests/test_required_answer.py::test_sc1_google_without_the_new_fields_sends_neither` |
| SC-2 | R-2, R-3, R-4, R-5 | `tests/test_required_answer.py::test_sc2_anthropic_enforces_the_required_answer_as_structured_output`, `tests/test_required_answer.py::test_sc2_anthropic_truncated_and_refused_carry_no_answer`, `tests/test_required_answer.py::test_sc2_anthropic_output_limit_is_the_default_or_the_callers`, `tests/test_required_answer.py::test_sc2_anthropic_without_a_required_answer_offers_tools_as_before` |
| SC-3 | R-1 | `tests/test_required_answer.py::test_sc3_a_required_answer_that_is_not_offered_is_unconstructible` |
| SC-4 | R-6 | `tests/validator/test_no_verdict.py::test_sc4_the_judgment_requires_its_verdict_tool`, `tests/validator/test_no_verdict.py::test_sc4_truncated_refused_and_unanswered_are_each_named_never_a_verdict`, `tests/validator/test_no_verdict.py::test_sc4_a_truncated_response_is_not_trusted_even_with_a_call` |
| SC-5 | R-7, R-9 | `tests/validator/test_no_verdict.py::test_sc5_could_not_judge_prints_its_reason_and_exits_three`, `tests/validator/test_no_verdict.py::test_sc5_a_malformed_judgment_is_also_no_verdict`, `tests/validator/test_no_verdict.py::test_sc5_a_provider_failure_is_no_verdict_not_a_reject`, `tests/validator/test_no_verdict.py::test_sc5_pass_and_reject_keep_their_codes_and_their_json` |
| SC-6 | R-8 | `tests/validator/test_no_verdict.py::test_sc6_each_judgment_logs_model_stop_reason_and_token_counts`, `tests/validator/test_no_verdict.py::test_sc6_a_failed_judgment_is_logged_before_it_raises` |
| SC-7 | R-9 | `tests/test_required_answer.py::test_sc7_old_shaped_requests_and_responses_still_work` |
