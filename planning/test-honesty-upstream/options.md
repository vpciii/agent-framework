# Options: where a thin test is caught

- **Status:** Open
- **Date:** 2026-11-12 (revised the same day after the full Opus run and
  an online research pass; spike findings added 2026-11-13)
- **Author:** Claude (draft, from four independent divergers) — vpc is author of record

> At least two genuinely different approaches, kept alive until the last
> responsible moment (planning.md §3). The chosen option's rejected
> siblings become the ADR's "alternatives considered" (methodology.md §1).

## The decision

Where, and by what, is one class of real defect caught: **a PR claims a
criterion and cites a test for it, and the test verifies less than the
criterion's text says?** Forced by a day of measurement showing that the
validator's single reading catches it reliably only when it thinks for
minutes or runs on a paid model, and by vpc's judgment that minutes per
pull request is borderline unacceptable for a gate.

Seven of the eval set's 27 accepted pull requests carry a real
conformance defect. Five of the seven are this class (19% of accepted
work); the other two changed files outside their task.

- `pr-28` — the criterion says the PR *body* carries the task id; the
  test asserts it in the *title*.
- `pr-81` — "through dispatch and the gate"; the test calls only
  dispatch.
- `pr-59` — "a fixture for each rule branch"; one branch is shadowed by
  another fixture and never asserted.
- `pr-18` — "the verdict is REJECT carrying the finding"; the test
  checks the judgment, never the gate's verdict.
- `pr-39` — "exactly the configured commands"; the test asserts they are
  present, not that nothing else is.

In all five the code was right. None is known to have caused a bug.

**What was measured, 2026-11-12.** The first four cases, five runs each,
through the gate's own judgment (results under
`evals/validator/results/`, on the `feat/role-effort` branch):

| Validator | Caught | Per judgment | Cost of the 20 |
|---|---|---|---|
| `gemini-3.8-flash`, default effort (today's roster) | 5 of 20 | about 1 minute, 8,925 output tokens | free tier |
| `gemini-3.8-flash`, effort high | 18 of 20 | about 4 minutes, 37,191 output tokens | free tier |
| `claude-sonnet-5-5`, default effort | 8 of 20 | about 15 seconds, 1,381 output tokens | $1.22 |
| `claude-opus-5-5`, effort high | 16 of 20 | about 20 seconds, 1,761 output tokens | $2.59 |

Every finding in all four runs was the right one. Two full runs over the
36 cases, scored against today's answers (20 expected pass, 16 expected
reject):

| Validator | Accepted work passed | Expected rejects caught | Missed |
|---|---|---|---|
| `gemini-3.8-flash`, default effort | 20 of 20 | 12 of 16 | `pr-18`, `pr-27`, `pr-39`, `pr-59` |
| `claude-opus-5-5`, effort high ($3.20) | 19 of 20 | 14 of 16 | `pr-59`, `pr-81` |

The Opus run found `pr-27` and `pr-39`, which no earlier run had. Its
one wrong rejection, `pr-69`, is a plan edited inside its implementing
PR; the sign-off is recorded in the PR description, which the validator
is never shown. Both runs caught all nine planted defects.

**What these numbers cannot say.** 16 of 20 and 18 of 20 are not
distinguishable: the 20 are four pull requests run five times. The move
from 5 to 16 or 18 is real. **Not measured:** whether Gemini at high
effort wrongly rejects accepted work.

Options A, B, C and F were each drafted by a separate agent holding one
stance (boring / reuse / structural / contrarian), blind to the others
and given only the problem and the first three rows of the first table —
not the approaches vpc and Claude had already named. D is vpc's own, E
is what the measurements test, and G came out of the research. Edits are
for length, to correct facts and to add what the research found; the
substance of A, B, C and F is the divergers'.

## What published work says

Four research agents searched on 2026-11-12. ✓ marks a source Claude
read on its own page; the rest are as the agents reported them. Links
are under "Sources".

- **The problem is documented.** Judges of code feedback recognised
  valid work 96% of the time and invalid work under 25% [1 ✓]. The best
  configuration in one benchmark wrote passing tests for 82.8% of its
  instances; 33.8% were adequate, and the stated cause is
  under-specified requirements [2 ✓]. Tests written after seeing faulty
  code find fewer faults than tests written independently (14% against
  25%) [3 ✓].
- **Nobody has measured this class.** No source reports how often a
  judge catches a test weaker than its requirement. Our eval set is the
  only evidence there is.
- **List what the requirement demands, then check each item.** Checking
  a candidate against a list drawn from the *reference* beat one overall
  verdict by 12.5 to 21 points for about 28% more tokens; a list drawn
  from the *candidate* did worse than one verdict, because it never
  lists what is missing [4 ✓]. A pipeline that rebuilds the requirement,
  builds criteria and then judges on evidence agreed with experts 95.2%
  of the time [5 ✓]. Neither study is on code against tests.
- **Asking a judge to explain and propose fixes makes it reject correct
  code more often** [6 ✓].
- **Any rejection should count.** A minority veto beat majority voting
  across 14 judges [1 ✓]. Repeating one judge gains little, because its
  errors repeat (as reported).
- **Breaking the behaviour is the best-supported check.** A mutant
  written from the requirement, run against the test that claims it, is
  the measure one benchmark of requirement-based tests is built on
  [7 ✓ abstract only]. Told to kill every mutant, an agent wrote
  over-specified assertions (as reported).
- **Reviewer strength matters more than a different vendor.** Codex
  reviewing Claude's drafts lowered the pass rate from 91.4% to 82.8%;
  Claude reviewing Codex's raised it from 71.6% to 89.7% [8 ✓]. Puzzle
  tasks, and a reviewer that rewrites. A reviewer's bias toward its own
  work is mostly an effect of sharing the author's context, so a fresh
  session of the same model does about as well (as reported, small
  studies).
- **Reviewers that work are given more than the diff.** Repository
  access and execution made a stronger reviewer with fewer false alarms
  [9 ✓]. An evaluator "is still an LLM that is inclined to be generous";
  the one in that design was given a browser to exercise the work, and
  its findings went back to the author for 5 to 15 rounds [10 ✓].
- **Minutes are normal, and depth follows the change.** One blocking
  review has a median of 3 minutes 39 seconds and runs two, four or
  seven-plus agents by the size and nature of the diff [11 ✓].
- **A yes/no decision model is not the judge.** Jev is within three
  points of a reasoning judge where the verdict can be read off the
  text, and falls behind where it must be derived, as in code and logic
  [12 ✓ abstract only]. It returns no quotes, which the gate requires.

## Options

### Option A — A clause ledger inside the existing verdict *(boring)*
- **What** — One gate, same model. The verdict tool gains a required
  `coverage` list: for each claimed criterion, its separately checkable
  clauses, each with a verbatim quote of the assertion in a cited test
  that would fail if that clause broke, or nothing. Code decides, not
  the model: a clause with no quote, or a quote the existing quote check
  cannot find, becomes a test-honesty finding. **After the research:**
  the clauses are listed from the criterion's text before the test is
  read, never from the test; and the ledger asks for a quote, not an
  explanation.
- **Attractive because** — All five misses are an unasserted clause.
  The ledger turns "is this test honest?" into enumerate-and-point, the
  shape that measured 12 to 21 points better on another task [4]. It
  reuses the quote check, the schema and the eval, stays inside
  ADR 0008, and is undone by one revert.
- **Trade-offs / risks** — Unmeasured on code: the catch rate may not
  move. The quote check proves the line exists, not that it asserts the
  clause, so the model can still point at the title assertion.
  Over-splitting clauses could produce false REJECTs.
- **Wins when** — The 20-judgment check lands near 18 of 20 at about
  default latency, the nine planted cases are still caught and nothing
  is wrongly rejected.
- **Rough size** — About a day: a short spec, `validator/judgment.py`
  and its tests, the check rerun.

### Option B — Mutation testing on the changed lines *(reuse)*
- **What** — An existing mutation-testing tool as a dev dependency. A CI
  step runs it per claimed criterion: mutants only on lines the PR
  changed, tests only the ones the Traceability table cites. A surviving
  mutant is a changed line the cited test does not pin. No model call;
  advisory at first.
- **Attractive because** — It answers "would the test fail if the
  behaviour broke?" by running it, so the answer is the same every
  time. It fits "deterministic before model" and costs nothing.
- **Trade-offs / risks** — Its drafter put it at about two of the first
  four cases. The research is harsher: generic mutants on changed lines
  catch a test that asserts on a fake, and little else of this class —
  "exactly" against "present" needs a mutant nobody generates by
  default, and unchanged code yields no mutants at all. By the research
  agent's survey, only `cosmic-ray` among the Python tools filters to
  changed lines. It finds code no
  test pins, not criterion text no test meets. Equivalent mutants would
  be the first false findings. A new dependency needs an ADR.
- **Wins when** — The gaps are mostly new code the cited test never
  pins, and a noisy advisory signal read at merge is acceptable.
- **Rough size** — One to two days: a dependency and its ADR, a wrapper
  script, a CI step.

### Option C — Falsifiable clauses: every claim shown red, replayed by code *(structural)*
- **What** — (1) At the spec gate each criterion is written as atomic
  clauses (`SC-3.a` "the PR *body* carries the task id"), one observable
  at one surface, and the Traceability table maps clause to test. (2)
  The worker commits, for each clause it claims, a **break**: a small
  patch to non-test source that removes only that clause's behaviour.
  (3) A deterministic replay in the gate commands applies each break and
  runs the clause's cited tests: red with it, green without. (4) The
  gate's deterministic stage rejects a claim with no red; the model
  keeps one narrow question — does this break negate this clause?
- **Attractive because** — All five cases become mechanical. It is the
  check the research supports best [7], and precise criteria are what
  the test-adequacy studies say agents lack [2]. Language-agnostic.
- **Trade-offs / risks** — Heavier specs and more worker effort on every
  task. The worker writes both the test and its break, and an author's
  checks inherit the author's blind spots [3]; catching a break that
  misses its clause still rests on the model. Frozen specs are not
  retrofitted.
- **Wins when** — Worker PRs flow unattended and the human can no
  longer read each test against each criterion.
- **Rough size** — Two to three weeks across the spec template, the
  coverage checker, the worker's brief, a replay command, the collector,
  the deterministic checks, the judgment and the eval. A new ADR.

### Option D — A hostile review of the change before the pull request *(vpc)*
- **What** — After the worker's session reports success and before the
  PR is opened, a second, adversarial session in the same confined
  worktree tries to break each claim: change the behaviour a criterion
  describes, run the cited test, and report any claim whose test stays
  green. **After the research, a bounded form:** one break per claimed
  criterion, written from the criterion's text, run against the cited
  test alone, with the break and the test's output kept as the evidence.
- **Attractive because** — It checks a fact where the validator forms
  an opinion, and it has what the validator lacks: the whole repository
  and the ability to run things, which is what working reviewers are
  given [9, 10]. The break comes from someone other than the test's
  author [3]. It needs no change to how specs are written, and it runs
  on the subscription, not a paid API. It is the selective second
  reviewer on high-risk tasks that ADR 0008 already records.
- **Trade-offs / risks** — A second session per task, which ADR 0005
  and ADR 0008 declined as an effort sink — so it must be selective.
  Published systems choose by properties of the change (size, sensitive
  paths), not by the first reviewer's confidence [11]; we have no such
  rule yet. A session of the worker's own lineage was the other
  objection (ADR 0001); the research weakens it [8]. Whether a model
  writes a break that targets the right clause was measured once: see
  "Spike findings". It only covers work that comes through the worker.
- **Wins when** — The same conditions as C, with less appetite for
  changing the contract's format.
- **Rough size** — About a week: a reviewer brief, an orchestrator step,
  its outcome handling, tests. A new ADR.

### Option E — A different validator *(measured above)*
- **What** — Change what the validator runs on. Two candidates the
  numbers support: `gemini-3.8-flash` at effort high, or
  `claude-opus-5-5` at effort high. Either is a roster edit once the
  effort setting (specs/role-effort, draft PR #108) merges.
- **Attractive because** — It is measured, not argued: from 5 of 20 to
  18 or 16. No new machinery. Opus does it in about 20 seconds, found
  two defects no other run had, and its one wrong rejection came from an
  input it was not given.
- **Trade-offs / risks** — Gemini at high is about four minutes a
  judgment, came within 600 tokens of its output limit once and has had
  no full run. Opus is a paid API, 9 to 13 cents a judgment, where the
  validator is free today (ADR 0004), and it is the worker's own lineage
  (ADR 0001). Opus still missed two of the five in its full run. A
  decision model such as Jev is cheaper still and is the wrong tool
  here [12].
- **Wins when** — The catch has to happen at PR time, and either
  minutes or cents per PR are acceptable.
- **Rough size** — A roster line and an ADR revisiting 0004 and, for
  Opus, 0001.

### Option F — Don't move the catch: sweep merged work offline *(contrarian)*
- **What** — Leave the per-PR gate fast and at default effort. At spec
  close-out, before the human's `Implemented` sign-off, run the eval
  over that spec's merged pull requests at high effort; vpc rules on
  each rejection, and the fix is one added test, as #98's was for
  `pr-59`.
- **Attractive because** — Four minutes only hurts if the catch must
  happen at PR time, and nothing requires that: the job is advisory and
  blocks nothing, and all five defects were harmless. Offline, four
  minutes is free — and this is how all five were found. The evidence is
  thin to build on: five cases, measured on the cases that defined the
  class. Roughly 60% of the commits since 2026-11-09 concern the gate or
  its eval — the effort sink ADR 0005 named, relocated.
- **Trade-offs / risks** — A thin test sits on main for days, and a
  regression could slip past it in that window. The sweep is a habit
  that can lapse. It does nothing about compound criteria, which invite
  the defect.
- **Wins when** — The class keeps causing no bugs. It loses the day a
  thin test lets a real regression merge.
- **Rough size** — No code. A paragraph in the close-out routine.

### Option G — Send the verdict back to the worker *(from the research)*
- **What** — Not a place to catch the defect: what happens once it is
  caught. On a REJECT the findings, which already carry their quotes,
  are posted on the PR and given to the worker's session for a bounded
  number of further attempts before vpc is involved. Today the verdict
  is rendered by a function nothing calls.
- **Attractive because** — The harness designs the research found send
  findings back to the author [10]; these are experience reports, not
  measurements. It changes what the other options cost: a slow
  validator delays the worker, not vpc, and a wrong rejection costs one
  worker attempt, not the human's attention.
- **Trade-offs / risks** — It catches nothing by itself. A worker told
  its test is thin may over-specify the test, or answer a wrong finding
  as if it were right. Attempts cost budget and need a hard bound. The
  finding becomes an artifact one agent acts on from another, so it is
  ADR-worthy.
- **Wins when** — Any of A, D or E is adopted and work flows without vpc
  reading each rejection.
- **Rough size** — About a week, as its own spec.

## Comparison

| Option | Cost / appetite | Risk | Reversibility | Notes |
|---|---|---|---|---|
| A — clause ledger | About a day | Unmeasured on code; false REJECTs | One revert | The shape with the best measured gain on another task |
| B — mutation testing | 1–2 days and a dependency | Reaches little of this class; noise | Remove a CI step | No model, no variance |
| C — falsifiable clauses | 2–3 weeks | Authoring weight on every spec and task | Hard: it changes the contract's format | Makes the defect mechanical |
| D — hostile review | About a week | Effort sink unless selective; about half its flags are not thin tests | Remove an orchestrator step | Best-supported check, without changing the contract |
| E — different validator | A roster line and an ADR | Cost or latency; still misses some | A roster edit | 16–18 of 20, measured |
| F — offline sweep | None | A window on main; a habit | Nothing to undo | The route that found all five |
| G — verdict to the worker | About a week | Over-specified tests; budget | Remove an orchestrator step | Lowers the cost of every other option |

**Are they genuinely different?** Mostly. C and D are one idea — show
the test red by breaking the behaviour — with different authors of the
break (the worker, or an adversary) and different evidence (a replayed
artifact, or a report). A and C's first step both rest on splitting a
criterion into clauses; A asks the model to do it per PR, C asks the
spec to do it once. E and F are not alternatives to each other: one
picks the validator, the other picks when a slow one runs. G is not an
alternative to any of them.

## Spike findings — the hostile review by hand (2026-11-13)

Step 3 of the recommendation, run by Claude at vpc's word. The spike's
code and patches stayed in scratch space; only the findings are here.

**Method.** Ten pull requests at their head commits: the five defect
cases and, as clean controls, the next accepted case after each
(`pr-25`, `pr-31`, `pr-40`, `pr-65`, `pr-84`). For each, a fresh
`claude-sonnet-5-5` session was given the worktree and the text of the
claimed criteria, told not to read or run tests, and asked to split each
criterion into at most four clauses and write one break per clause. Each
break was then applied and only the tests the Traceability table cites
for its criterion were run. A break those tests do not notice is
"unnoticed". The sessions' tool calls were checked: none read a test.

**Counts.** 129 breaks, all applying cleanly and leaving the package
importable: 113 noticed, 16 unnoticed. About 850,000 tokens in all;
each session took between 23 seconds and 3 minutes.

**The five known thin tests.**

| Case | Result | Why |
|---|---|---|
| `pr-18` SC-4 | Found | The gate ignores a reported defect; the cited test stays green |
| `pr-28` SC-3 | Found | The PR body loses the task id; the cited test stays green |
| `pr-59` SC-2 | Flagged by another route | Two breaks to the precedence rule went unnoticed; none touched the open-task branch on record |
| `pr-39` SC-2 | Missed | The break dropped a command; "exactly" needed one that adds a command |
| `pr-81` SC-7 | Missed | The break changed dispatch, which the test checks; it needed to break only the gate leg |

**The 16 unnoticed breaks, sorted by Claude.**

| Break | What it changed | Reading |
|---|---|---|
| `pr-18` SC-4.a | The gate never rejects on a reported defect | Known thin test |
| `pr-28` SC-3.b | The PR body has no task id | Known thin test |
| `pr-59` SC-2.a | A Draft spec no longer leads to sign-off | Known criterion; the fixture uses only "Under review" |
| `pr-59` SC-2.b | An alert no longer outranks an open PR | Known criterion; no fixture has both |
| `pr-28` SC-2.d | The session gets the raw task section, not the brief | **New.** The test's sentinel is in both |
| `pr-59` SC-6.a | Only the session's leader is killed | **New.** The test waits 60 seconds for the children to exit by themselves, then finds none |
| `pr-59` SC-7.a | The note prints the budget as the elapsed time | **New.** The test asserts the label, not the value |
| `pr-18` SC-3.b | The collector counts missing checks as green | Mis-aimed: the criterion is about the gate; another test notices |
| `pr-28` SC-4.b | One line of the escalation loses the task id | Mis-aimed: the heading still names the task |
| `pr-59` SC-3.b | The GitHub heading is dropped | Mis-aimed: the card still states the status is unavailable |
| `pr-59` SC-6.b | Children that ignore SIGTERM are not killed | Partial: the fixture's children do not ignore it |
| `pr-81` SC-4.c | A refusal that carries text is not a refusal | Partial: the test's refusal carries none |
| `pr-40` SC-3.c | The default pattern loses its multi-line flag | Clean case. The whole suite stays green; not checked further |
| `pr-40` SC-3.d | The CLI stops passing the project config to the gate | Clean case. Outside the criterion, which speaks of the check; no test anywhere notices |
| `pr-65` SC-5.d | The CLI stops passing `test_paths` to the collector | Clean case. Outside the criterion; no test anywhere notices |
| `pr-65` SC-1.c | Several changed spec directories resolve to the first | Clean case. The clause covers exactly one; no test covers several |

**Clean cases.** 4 of 50 breaks went unnoticed, in 2 of the 5 pull
requests. None is a test weaker than its criterion.

**On main at `9dba794`.** With the break applied the whole suite still
passes for four of these: the PR body without a task id, the leader-only
kill, the elapsed value, and several spec directories. `pr-18`'s is now
caught. Three patches no longer apply and were not checked.

**What it settles.**

- A model can aim a break from the criterion's text alone when the
  clause names a surface (the body, the gate's verdict).
- It misses when the break must be the exact difference between the
  clause and the obvious test: a quantifier ("exactly") broken in the
  permissive direction, or one leg of "A and B". A sharper brief may fix
  this; that is not measured.
- An unnoticed break is a lead, not a verdict. Seven of the 16 pointed
  at a real thin test and nine did not. Rejecting on any unnoticed break
  would have wrongly rejected two of five clean pull requests.

**Limits.** One run, one model, ten pull requests. Claude sorted the 16
knowing which cases were defects, and "mis-aimed" and "partial" are
readings vpc may rule differently.

## Recommendation

*Drafted by Claude for vpc to change. The choice is vpc's.*

The research moved this recommendation toward vpc's instinct. The first
draft deferred D; this one tests it next to A, because breaking the
behaviour is the check with the best support and reading harder is the
one with a known ceiling.

1. **E is measured; do not choose on it yet.** A stronger model helps
   and neither candidate catches everything. The set cannot rank 16
   against 18.
2. **Spike A in its criterion-first shape** on the same 20-judgment
   check, with the rule the role-effort spec already uses: it counts
   only at 15 of 20 or better and at least 5 more than the same model
   without it. Free-tier Gemini first, then Opus.
3. **Spike D by hand before building it.** *Done 2026-11-13; see "Spike
   findings".* It found two of the five known thin tests squarely and
   three new ones, missed two, and flagged two of five clean pull
   requests. So D is worth building only with a judging step: the
   unnoticed breaks go to the validator as evidence, and it answers one
   narrow question each — does this break negate this clause?
4. **Then one ADR** that names the validator, records which of A and D
   was adopted, and answers cost (ADR 0004) and lineage (ADR 0001,
   restated in ADR 0008) in the open. The research says the lineage
   rule rests on thin evidence; our own runs are the better guide.
5. **Spec G after that.** It is worth having whichever option wins, and
   it is what makes a slower or stricter check tolerable.
6. **Two habits, starting now:** F's sweep at spec close-out, and
   criteria written one clause at a time. Under-specified requirements
   are the published cause of weak tests [2].

Not now: **B**, which reaches little of this class; **C in full**,
which changes the contract's format before D has shown the check works;
**repeat runs and voting**, which multiply cost for a small gain; and a
decision model as the judge. One adjacent gap deserves its own small
spec: the validator is not shown the PR description, which is what
wrongly rejected `pr-69`.

**The contrarian's case, answered.** The research strengthens one half
of it: the evidence is five cases, and the eval cannot rank close
results. It weakens the other: this is the commonest documented failing
of agent-written tests, not a quirk of ours [2], and a gate that passes
it four times in five is misdescribing itself. Step 6 takes the sweep.
Steps 2 and 3 cost two days and say whether the gate can do the job it
claims.

## Sources

1. Beyond Consensus (14 judges, 366 Python programs) —
   https://arxiv.org/abs/2510.11822
2. Req2Test-Bench — https://arxiv.org/abs/2610.36584
3. On the risk of coding before testing —
   https://arxiv.org/abs/2607.05139
4. Atomic and Holistic LLM Judges (AACL 2026; a question-answering
   task) — https://aclanthology.org/2026.aacl-long.60.pdf
5. PACE-Bench — https://arxiv.org/abs/2610.26394
6. Are LLMs Reliable Code Reviewers? — https://arxiv.org/abs/2603.00539
7. RESTestBench — https://arxiv.org/abs/2604.25862
8. Cross-Model LLM Code Review (116 puzzle tasks) —
   https://arxiv.org/abs/2607.21656
9. OpenAI, A Practical Approach to Verifying Code at Scale —
   https://alignment.openai.com/scaling-code-verification/
10. Anthropic, Harness design for long-running apps —
    https://www.anthropic.com/engineering/harness-design-long-running-apps
11. Cloudflare, Orchestrating AI Code Review at scale —
    https://blog.cloudflare.com/ai-code-review/
12. JEV-as-a-Judge — https://arxiv.org/abs/2609.26550
