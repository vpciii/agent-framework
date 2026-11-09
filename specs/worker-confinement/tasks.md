# Tasks: Worker confinement

- **Status:** Approved
- **Spec:** ./spec.md
- **Plan:** ./plan.md

PR-sized tasks derived from the plan. Each behavioural task traces to ≥1
success criterion — the tests it must make pass cite those ids — and
replaces its `*(pending)*` Traceability rows as its tests land. Mark a task
`[x]` with its merged PR number when done. Task PRs carry a `Satisfies:`
declaration and name `specs/worker-confinement/` in their body.

**DAG:** T-1 → T-2; T-1 → T-3 → T-4; T-5 after T-2 and T-4. T-2 and T-3
touch different files and can proceed in parallel once T-1 merges.

**Criterion coverage:** SC-8 → T-1 · SC-1, SC-2, SC-3, SC-4, SC-9 → T-2 ·
SC-5 → T-3 · SC-6, SC-7 → T-4 · T-5 is the delivery edge and closes out
the spec.

**Not for dispatch to a worker session.** These tasks change the worker's
own launch path and the gate on its output; until T-2 and T-4 merge, the
worker that would run them is the unconfined one they replace.

---

### [x] T-1 — Config fields for the profile and the handoff check (#68)
- **Satisfies:** SC-8
- **Depends on:** —
- **Touches:** `src/agent_framework/project.py`,
  `tests/test_project_config.py`,
  `specs/worker-confinement/spec.md` (Traceability row SC-8)
- **Brief:** Add `session_write_paths`, `session_read_paths`,
  `session_network`, `session_env` (each default empty) and
  `protected_paths` (default `.github/**`, `agent-framework.toml`) to
  `ProjectConfig` and the loader, with the plan's validation: paths
  absolute or `~/`-prefixed; a network entry a bare host name (no scheme,
  path or port); an environment entry a variable name; patterns non-empty.
  Give the `test_paths` path matcher a general name so `protected_paths`
  reuses it; `test_paths` behavior is unchanged. Additive: no caller reads
  the new fields yet.
- **Done when:** SC-8's tests pass citing it — each field parses, takes
  its default when absent, and raises `ProjectConfigError` naming the
  field for a non-list, an empty entry, a relative path, and a host given
  as a URL. Existing config tests pass unmodified.

### [x] T-2 — Launch every session under the confinement profile (#69)
- **Satisfies:** SC-1, SC-2, SC-3, SC-4, SC-9
- **Depends on:** T-1
- **Touches:** `src/agent_framework/worker/confinement.py` (new),
  `src/agent_framework/worker/{session,orchestrator,__main__,brief}.py`,
  `agent-framework.toml`, `tests/worker/test_confinement.py` (new),
  `tests/worker/{test_session,test_orchestrator,test_cli,test_brief}.py`,
  `specs/worker-confinement/spec.md` (Traceability rows)
- **Brief:** `confinement.py` computes, purely, the profile's arguments,
  inline sandbox settings and environment exactly as `plan.md` lists them.
  The session seam takes the environment and closes standard input;
  `session_args` is removed from `run_session`, `work()` and the CLI
  (`--session-arg` becomes an argument error). The brief gains the
  statement of limits and the instruction to escalate rather than work
  around them. Add this repo's declarations to `agent-framework.toml`
  (plan, API changes). **Breaking:** commit as `feat!`. Do not touch the
  handoff (`handoff.py`) — that is T-4.
- **Done when:** SC-1, SC-2, SC-3, SC-4 and SC-9's tests pass citing them.
  The fake session seam's recorded launch carries the whole profile; the
  rendered settings match the plan for a project with and without
  declarations; an environment holding secret-looking variables reaches
  the seam without them. Existing worker tests are updated only where the
  seam's signature changed.

### [x] T-3 — The handoff check (#70)
- **Satisfies:** SC-5
- **Depends on:** T-1
- **Touches:** `src/agent_framework/worker/handoff_check.py` (new),
  `src/agent_framework/artifacts.py`,
  `tests/worker/test_handoff_check.py` (new),
  `specs/worker-confinement/spec.md` (Traceability row SC-5)
- **Brief:** `check_handoff(worktree, project, specs_dir, run)` returns
  `HandoffFinding`s per the plan's rule table: base is the merge-base with
  `origin/main`; changed paths from `git diff --name-status --no-renames`;
  contract rules compare each `spec.md` with its Traceability section
  removed and each `tasks.md` with checkbox marks normalized, base against
  head; protected paths and deleted tests by pattern. The two text helpers
  go in `artifacts.py`. A pure function over the runner seam: it pushes
  nothing and is not yet called by the orchestrator. Follow the real-git
  fixture pattern in `tests/worker/test_worktree.py`.
- **Done when:** SC-5's tests pass citing it, against a real repository:
  a reworded criterion, a changed requirement, a `tasks.md` edit beyond a
  checkbox, a change under a protected path and a deleted test file are
  each refused naming the path; a diff that fills a Traceability row,
  ticks a checkbox and changes source and tests yields no finding.

### [x] T-4 — Refuse the handoff, alert, and never run hooks (#71)
- **Satisfies:** SC-6, SC-7
- **Depends on:** T-3
- **Touches:** `src/agent_framework/worker/{types,orchestrator,handoff,worktree,__main__}.py`,
  `src/agent_framework/status/card.py`,
  `tests/worker/test_handoff_refused.py` (new),
  `tests/worker/{test_orchestrator,test_cli}.py`,
  `tests/orientation/test_status_card.py`,
  `specs/worker-confinement/spec.md` (Traceability rows)
- **Brief:** Add the `HandoffRefused` outcome. The orchestrator runs
  `check_handoff` after a completed session and before `open_pr`; on any
  finding it raises a `refused` alert through `notify` (one issue per
  task, as escalation does), keeps the worktree, and returns the outcome;
  the CLI prints it and exits 4. `refused` joins the resume card's alert
  labels. Every post-session git command for the worktree carries
  `-c core.hooksPath=/dev/null`.
- **Done when:** SC-6 and SC-7's tests pass citing them: on a refusal no
  push and no `gh pr create` are issued, the worktree exists, the outcome
  carries every finding, the alert is raised once, and the card lists it;
  with a `pre-push` hook planted in a real repository, a successful
  handoff's push leaves no trace of the hook having run.

### [~] T-5 — Delivery: docs, glossary, the live run
- **Satisfies:** —
- **Depends on:** T-2, T-4
- **Touches:** `docs/glossary.md`, `docs/adoption.md`,
  `docs/architecture.md`, `tests/test_adoption_doc.py`,
  `specs/worker-confinement/{spec,tasks}.md`
- **Brief:** Add the two glossary terms as the spec words them. In
  `docs/adoption.md`, replace the `--dangerously-skip-permissions`
  dispatch command with the confined one, add the five fields with a
  worked example (uv; one non-Python toolchain), the refused outcome and
  exit code 4, and what to do when a gate command is refused. Rewrite the
  worker's entry under Trust boundaries in `docs/architecture.md` and add
  the new modules to the component table. Run the spec's *Live check*
  probe and dispatch one real task in this repository under the profile;
  quote both in the PR (R-12). Confirm the Traceability table has no
  pending row. Marking the spec `Implemented` is the human's sign-off, in
  its own PR.
- **Done when:** the adoption-doc test covers the new fields and no longer
  finds `--dangerously-skip-permissions`; the PR cites the live run and
  the probe result; spec coverage passes with zero pending rows.
