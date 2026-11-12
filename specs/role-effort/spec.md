# Spec: A role's effort is set in the roster

- **Status:** Draft
- **Date:** 2026-11-12
- **Author:** Claude (draft) — vpc is author of record
- **Related ADRs:** ADR 0001 (roles are bound by the roster; no vendor
  in the framework), ADR 0008 (what the validator judges), ADR 0004
  (which surface each role runs on)

> This spec is editable while `Draft` / `Under review` / `Approved`.
> When the PR that marks it `Implemented` merges it **freezes** into a
> historical record (methodology ADR 0027);
> a contradiction found later goes to a test, a new spec, or an ADR —
> not back into this file (methodology §2, §8).

## Problem

The validator catches one kind of real defect about one time in three,
and how hard it thought looks like the reason.

Four accepted pull requests in the eval set — `pr-18`, `pr-28`, `pr-59`
and `pr-81` — each cite a test that verifies less than its criterion
says. Across the three recorded runs that is twelve judgments. Four
caught the defect and eight passed it. Output tokens, which include the
model's thinking, tell them apart:

| | Judgments | Output tokens |
|---|---|---|
| Caught | 4 | 12,960 to 15,270 |
| Missed | 8 | seven between 2,745 and 5,246; one at 13,280 |

Every catch came with long thinking, and seven of the eight misses with
short. Twelve judgments is thin, and one miss thought long and still
passed, so this is a lead and not a finding.

The framework has no way to follow it. The judgment's request says
nothing about how much to think, so the validator runs at its provider's
default — `medium` on `gemini-3.8-flash`, where the model decides how
much of that allowance to use. A per-role effort setting was put off in
specs/judgment-reliability because the eval set it should be tuned
against did not exist yet. It does now.

Two limits are known before starting. The provider documents `high` as
the most the model *may* think, not what it must: it could still think
briefly and miss. And more thinking is more output tokens and more time
on every judgment the gate makes.

## Goals

1. How much reasoning a role's model is asked to spend is a roster
   setting, like the model itself: changed by a config edit, never a
   code change, and with no vendor's vocabulary outside the adapters.
2. Whether a higher setting steadies the validator on those four cases
   is measured, before and after, on the eval's own cases.
3. The roster in this repository changes only if the measurement says
   it should.

## Non-goals

- Changing this repository's roster. That is its own one-line PR,
  after the check, citing both results (see *Rollout and undo*).
- Effort per request, or chosen by the judgment's code.
- Levels beyond `low`, `medium` and `high`, and numeric thinking
  budgets.
- An effort setting for the worker session, which does not go through
  the provider adapters (ADR 0004).
- Asking the judgment more than once, or showing it whole files.

## Requirements

- **R-1 (MUST)** A role's binding in the roster may carry `effort`: one
  of `low`, `medium`, `high`. Any other value is a roster error naming
  the role and the three values. A binding without it is what it is
  today.
- **R-2 (MUST)** When a role with an effort is dispatched, the request
  its provider adapter receives carries that effort. When the role has
  none, the adapter receives the request exactly as it was given.
- **R-3 (MUST)** Each adapter asks its provider for the effort in that
  provider's own way: the Google adapter as the thinking level, the
  Anthropic adapter as the output effort — alongside the answer format
  when the request names a required answer. With no effort, neither
  adapter sends any such option: the provider's default applies, as
  today.
- **R-4 (MUST)** The provider interface, dispatch, the judgment and the
  gate carry the effort as intent only. No provider's option name
  appears in them.
- **R-5 (MUST)** The worker orchestrator refuses a `worker` binding that
  carries an effort, before a worktree or a session is created. The
  session does not take the setting, and a setting that is silently
  ignored is worse than an error.
- **R-6 (MUST)** A judgment's log line names the effort it ran at, and
  an eval result records it; the scorecard's first lines show it. A
  result with no such record reads as "provider default".
- **R-7 (SHOULD)** The delivery records the check described under
  *Rollout and undo*: the four cases, five runs each, at the provider's
  default and at `high`, and one full run at `high`.

## Success criteria

- **SC-1** — A roster whose `validator` binding carries `effort =
  "high"` resolves to a binding with that effort; one without it
  resolves to none; one with `effort = "maximum"` fails to load, naming
  the role and the allowed values. (R-1)
- **SC-2** — Dispatching through a role bound with an effort, a fake
  provider receives the request with that effort and otherwise equal to
  the one given; through a role without one, it receives the very
  request it was given. (R-2)
- **SC-3** — Given a request with effort `high`, the Google adapter's
  call to its SDK carries the thinking level `high`; given none, the
  call carries no thinking option. (R-3)
- **SC-4** — Given a request with effort `high`, the Anthropic adapter's
  call carries the output effort `high`, together with the answer
  format when the request names a required answer; given none, the call
  carries no effort. (R-3)
- **SC-5** — The provider interface, dispatch, judgment and gate modules
  contain no provider's name for the option. (R-4)
- **SC-6** — With a `worker` binding that carries an effort, the worker
  orchestrator fails before any git or session command is run, and the
  error names the setting. (R-5)
- **SC-7** — A judgment made through a validator bound with effort
  `high` logs that effort; an eval run through it writes a result that
  records `high` and a scorecard that shows it; a result written before
  this change loads and shows "provider default". (R-6)

## Glossary additions (proposed with this spec)

Added to `docs/glossary.md` in the implementing PR.

- **Effort** — how much reasoning a role's model is asked to spend on a
  request: `low`, `medium` or `high`. Set per role in the roster; each
  provider adapter translates it to its provider's own control. Unset
  means the provider's default.

## Approach

One PR if it stays near 300 lines; otherwise two — the setting from
roster to adapter, then the eval's record of it.

- `models.py`, `roster.py` — `ModelRef` gains `effort`, optional;
  the roster validates it against the three values.
- `providers/base.py` — `Request` gains `effort`, optional, described as
  intent beside `require_tool`.
- `dispatch.py` — copies the role's effort onto the request it passes
  on. Callers do not set it; the judgment's `build_request` is
  untouched, so the instructions' fingerprint does not move.
- `providers/google.py` — `thinking_config` with the level.
  `providers/anthropic.py` — `effort` inside `output_config`, which it
  already builds for a required answer.
- `worker/orchestrator.py` — the refusal, where it resolves the worker's
  model.
- `validator/judgment.py` — the log line. `evals/` — `Result` gains
  `effort`, written by `run`, shown in the scorecard's head; absent in
  an older file means the default.
- Docs in the same PR: the roster section of `docs/adoption.md`, the
  roster, adapter and eval rows of `docs/architecture.md`, the glossary.
- Not touched: `agent-framework.toml`, the judgment's instructions and
  schema, the deterministic stage, the eval's cases.

Verified against the installed SDKs on 2026-11-12: `google-genai` 2.11
has `ThinkingConfig.thinking_level` with `low`, `medium`, `high`
(`gemini-3.8-flash` rejects `minimal`); `anthropic` 0.116 has
`output_config.effort`. The Anthropic path is tested at the transport
level only — this project has no Anthropic API key, as before.

### Decisions

- *(none yet)*

## Rollout and undo

Off by default: a roster with no `effort` sends what it sends today.
Undo is reverting the PR; removing the field from a roster undoes a
setting.

**The check (R-7).** Run by vpc, with the key, from the implementing
branch before it merges. `run --roster FILE` takes a roster other than
the repository's, so nothing in the repository's roster changes:

1. Before: `--only pr-18 pr-28 pr-59 pr-81 --runs 5` with the roster as
   it is. 20 judgments.
2. After: the same with a copy of the roster whose validator has
   `effort = "high"`. 20 judgments.
3. A full run with that copy. 36 judgments, to see whether more
   thinking wrongly rejects accepted work.

Read each by its scorecard's "caught n of 20"; `compare` lines up a
case's runs in order, so on multi-run results it is not the tool for
this.

**Cost.** 76 judgments in all, against a free-tier daily limit that has
been shown to allow 36 and may not allow much more: spread over two or
three days unless the limit page says otherwise. At `high` each
judgment will take longer and use more output tokens — roughly three to
five times as many on these cases, if it thinks as it did when it
caught them. The advisory CI job would slow by the same factor once the
roster is changed.

## Open questions

Each has a drafted answer; all are vpc's to accept or change.

- [ ] **When the roster is changed.** Drafted rule, fixed before the
  numbers are in: set `effort = "high"` for the validator if the after
  check catches at least 15 of 20, at least 5 more than the before
  check, and the full run rejects no accepted work on a finding vpc
  rules false. Anything short of that, the roster stays as it is and
  the next lever is tried. In between is vpc's call.
- [ ] **Whether the setting merges if the check shows no gain.**
  Drafted: no. An unused setting is clutter; the branch is closed and
  the spec marked `Withdrawn` with the numbers recorded in it.
- [ ] **Three levels, not the providers' full ranges.** `low`, `medium`
  and `high` are the levels both providers share. Anthropic's higher
  levels can be added when a role needs them.
- [ ] **No ADR.** The setting extends what a roster binding says and
  changes none of ADR 0001's decisions; it is undone by deleting a
  field.
- [ ] **The worker refuses the setting rather than passing it on**
  (R-5). Passing it to the session is a separate piece of work on a
  different surface.

## Out of scope (for now)

- Per-case tallies for multi-run results ("caught 3 of 5").
- Asking the judgment more than once, whole changed files for the
  judge, a stronger validator model.
- An effort for the chief, which has no code yet.

## Traceability

| Criterion | Requirement(s) | Verified by (test) |
|---|---|---|
| SC-1 | R-1 | *(pending)* |
| SC-2 | R-2 | *(pending)* |
| SC-3 | R-3 | *(pending)* |
| SC-4 | R-3 | *(pending)* |
| SC-5 | R-4 | *(pending)* |
| SC-6 | R-5 | *(pending)* |
| SC-7 | R-6 | *(pending)* |
