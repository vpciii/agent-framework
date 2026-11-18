# Glossary — agent-framework

The project's ubiquitous language. Use these terms exactly, in code, docs,
and agent prompts. Add a term here before inventing a name for a concept.

- **Chief agent** — the coordinating agent. Decomposes a signed-off
  `spec.md` into `tasks.md`, dispatches tasks, and runs the aggregate
  requirements-met check. Does **not** write feature code, and is **not**
  the final acceptance authority (the human is).
- **Worker agent** — executes exactly one **task** → one PR with tests.
  May be a cheaper model. Reads its task + the spec, not the chief's
  context.
- **Validator agent** — gates a worker's PR against its criteria via the
  **cite-the-test gate**. A *different model* than the worker, for
  blind-spot coverage.
- **Task** — a PR-sized (~<300-line) unit of work in `tasks.md`, tracing to
  **≥1 success criterion**, with explicit dependencies (the tasks form a
  DAG) and an explicit "done when" (the tests that must pass).
- **Success criterion (`SC-…`)** — a stable-id, testable signal defined in
  the spec. The **coordination thread**: it ties chief intent → worker
  output → validator check → the chief's requirements-met verdict.
- **Cite-the-test gate** — the validator's rule: a **PASS** must cite the
  passing test for each claimed criterion (plus red→green for a fix, green
  CI, and the review checklist); it never asserts "looks correct." Output
  is a structured `PASS{criteria:[SC-…✓(test)]}` or `REJECT{finding,
  evidence}`.
- **Ready frontier** — the set of tasks whose DAG dependencies are all
  satisfied, dispatchable in parallel.
- **Escalation** — when a worker finds the spec wrong (or a term/boundary
  is unspecified), it stops and escalates to the chief; a contract change
  is its own diff for human sign-off, never a quiet `tasks.md` edit.
- **Role** — a model-agnostic slot (chief / worker / validator), bound to a
  concrete model by the **roster**. The framework hardcodes no vendor
  (ADR 0001).
- **Roster** — the single config that binds each role to a model (e.g.
  a high-end model as chief, a cheaper one as worker, a different-lineage
  model as validator). Swapping a model is a roster edit, not a code
  change; it is the one source of truth for the role→model mapping.
- **Effort** — how much reasoning a role's model is asked to spend on a
  request: `low`, `medium` or `high`. Set per role in the roster; each
  provider adapter translates it to its provider's own control. Unset
  means the provider's default (specs/role-effort).
- **Roster currency check** — the scheduled CI check that each model the
  roster binds is still served by its provider (failing if not, or if the
  provider silently routes it elsewhere), reporting newer models in the
  same family as advisory. It detects; it never edits the roster
  (specs/roster-currency-check).
- **Resume card** — a generated summary of where a project stands: specs in
  progress, open tasks, bets, escalations, open PRs and alert issues, and
  exactly one **next action** chosen by a fixed precedence rule. Derived
  from the artifacts, never hand-written (specs/orientation-and-alerts).
- **Nudge** — the weekly push of the resume card: it updates one GitHub
  issue labelled `status` and sends vpc the next action by phone. It only
  reports; it never dispatches work.
- **Confinement profile** — the fixed limits the orchestrator launches
  every worker session under: its tools, and what its commands may read,
  write and reach on the network. Owned by the framework; a project widens
  it only by declaring paths, hosts and variable names in
  `agent-framework.toml`. No caller can widen it at dispatch (ADR 0007).
- **Handoff check** — the orchestrator's deterministic check of a
  completed session's diff, run before anything is pushed: the contract
  text unchanged, protected paths untouched, no test file deleted. A
  finding refuses the handoff (ADR 0007).
- **Handoff note** — the `HANDOFF.md` the orchestrator writes into a kept
  worktree when a worker session is stopped at its time budget or its
  **spend limit**: task, budget, elapsed time, the spend limit and reported
  cost when that is what stopped it, git state and any progress notes, so
  the next human or run can pick up without guessing. Written by the
  orchestrator because a killed session can't write its own.
- **Spend limit** — the most a single worker session may spend, in US
  dollars at the provider's list price, set at dispatch ($10 unless the
  dispatch says otherwise). Claude Code measures it and checks it after
  each turn, so a session can overrun it by up to one turn. On the Max plan
  it measures use of the plan's allowance, not money
  (specs/worker-spend-and-record).
- **Session record** — the file of everything a worker session wrote to its
  output (its turns, tool calls and results, and a final entry with its
  cost and why it ended), kept on the dispatching machine in
  `.worktrees/records/`, outside every worktree. Never published
  (specs/worker-spend-and-record).
- **Dispatch issue** — an open GitHub issue labelled `dispatch`, opened by
  the account the project names, whose title is a spec slug and a task id.
  It asks for one worker run. It is a pointer to a task on `main`; nothing
  in it is read by a session (ADR 0010, specs/dispatch-from-issue).
- **Dispatch tick** — the command, run on a schedule, that makes one pass:
  it finds a **dispatch issue**, starts the run it asks for, and reports
  back on the issue (specs/dispatch-from-issue).
- **Heartbeat** — the signal a **dispatch tick** sends when a pass
  completes, so that its absence can be noticed from outside
  (specs/dispatch-from-issue).
- **Eval set** — the fixed collection of eval cases the validator's
  judgment is measured on (specs/validator-eval-set).
- **Eval case** — one frozen evidence bundle with the outcome a human
  expects of the judgment, `pass` or `reject`. Either an **accepted
  case** (a merged pull request as it was) or a **seeded-defect case**
  (an accepted case with one deliberate defect).
- **Scorecard** — the result of running the judgment over the eval set:
  how many accepted cases it passed or wrongly rejected, how many seeded
  defects it caught or missed, and how many it could not judge.
- **Inputs fingerprint** — a short hash of what every case in the eval
  set sends the judgment. Two results with the same inputs fingerprint
  judged the same cases, whatever answers were expected at the time
  (specs/eval-rescore).
- **Worker eval case** — one past task the worker is measured on: the
  task, the commit its accepted pull request started from, that **reference
  pull request**, and the tests it added for the task's criteria
  (specs/worker-eval).
- **Reference pull request** — the merged pull request that completed a
  worker eval case's task, accepted by the human. Its start commit is
  where the worker begins; its tests are run against what the worker
  produced. It shows one accepted result, not the only one.
- **Ready for review** — a worker run that completed with every gate
  command passing and no handoff finding: a pull request the human would
  be asked to review.
- **Worker scorecard** — the result of running the worker over the
  worker eval cases (the validator's is the **scorecard**).
- **Regression claim** — the token `regression` in a PR's Satisfies
  declaration: the author's explicit claim that the PR fixes a bug with a
  cited red→green regression test. The gate verifies the evidence
  discipline (honest test, red→green, scoped diff), never the fix's
  approach or method.
- **Satisfies declaration** — the structured `Satisfies: SC-…` line in a
  task PR's body: the worker's explicit claim of which success criteria the
  PR delivers. The validator's collector reads claims from it exclusively
  when present; prose mentions of `SC-` ids are not claims.
- **Provider adapter** — a thin per-provider (Anthropic, Google, …) shim
  behind a common interface (prompt + tools in, response out), so models are
  pluggable. Adding a provider = a new adapter + a roster entry.
