# Problem brief: agent-framework only moves while vpc is driving it

- **Status:** Exploring
- **Date:** 2026-10-26
- **Author:** Claude (draft) — vpc is author of record

> Solution-free on purpose. Describe the problem; do not name a remedy —
> if a solution creeps in, move it to `options.md` (planning.md §1).

## The problem

agent-framework exists to let agents do the building while the human
stays author of record. In practice, nothing in it advances unless vpc is
present and driving. The chief's seat is a human-driven interactive
session (ADR 0004); each worker is launched by hand and runs as a single
synchronous session that is killed when its budget expires; and when a
worker needs a human decision, it writes an escalation file that waits
until someone happens to look. The pipeline's progress is bounded by
vpc's attention, not by the work.

The second half of the problem is what happens when vpc *isn't* watching.
A session that is interrupted — by its time budget, a crash, a reboot, or
a lost terminal — loses its in-flight work and has to start over, so
there is no safe way to leave long or multi-phase work running
unattended. And the moments where vpc's judgment genuinely matters (signing
off a spec, a task decomposition, a PR) have no way to reach him
asynchronously and then let the work resume from where it paused. Today
the only choices are "vpc sits in the loop for all of it" or "the work
doesn't happen."

## Who feels it

- **vpc**, as the sole author of record across projects: every phase
  needs him at a keyboard to start it, notice its outcome, and start the
  next. Verification he would willingly give in two minutes from a phone
  instead costs a full sit-down session.
- **The worker role**: a session that hits its 1800 s budget is killed
  (`worker/session.py`, `orchestrator.py`), and a killed or crashed
  session leaves no resumable state — only a kept worktree.
- **Projects adopting the methodology** (via project-portability): they
  inherit the same ceiling — the framework is only as active as the
  person driving it.

## Evidence

- **Measured:** the repo's whole history (49 merged PRs, 26 human
  sign-off commits) falls on **4 distinct days** since 2026-07-10, and
  nothing has landed since 2026-07-19. Work happens in bursts when vpc
  sits down, then stops.
- **Measured:** the chief does not exist as code; its seat is an
  interactive session by decision (`docs/architecture.md`, ADR 0004).
- **Measured:** worker sessions run as one blocking `claude -p`
  subprocess with a time budget; on expiry the session is killed
  (`worker/session.py`). No code path resumes an interrupted session.
- **Measured:** escalations are written to
  `specs/<slug>/escalations/*.md` (`worker/handoff.py`); nothing in
  `src/` notifies anyone that one exists.
- **Measured (2026-10-26):** a local coding model with working tool
  calls now runs on defiant (Qwen3-Coder-Next via `mlx_lm.server`,
  ~41 tok/s). Unattended capacity exists that the framework cannot use.
- **Confirmed by vpc (2026-10-26):** the July stop was not a deliberate
  pause — the project stalled. By October, vpc no longer remembered
  where it had left off; reconstructing that took a session of its own.
- **Suspected:** a meaningful share of tasks is routine enough to finish
  without vpc, and the ones that are not can be recognized and paused.
  Unmeasured; no task outcomes have been tallied.
- **Suspected:** local models are good enough for some of that share.
  Only a smoke test exists, no task-level evidence.

## Why now

- Local inference capacity was set up on defiant today and sits idle
  between chats; the framework is the obvious consumer and cannot reach it.
- ADR 0004 runs the worker on Claude Max "while supported" — a dependency
  whose terms the project does not control. Whether unattended operation
  must survive that going away is easier to decide before more is built
  on the current shape.
- The framework is still small (three slices, no chief code). Decisions
  about where long-running state and human checkpoints live are cheapest
  before a chief is written against today's shape.
- The cost of stalling is compounding: three months idle was enough to
  lose the thread entirely, and every stall now ends in a re-orientation
  session before any work resumes.
- **Not forcing:** there is no external deadline; the pressure is the
  growing cost above, not a date.

## Not the problem

- **Removing the human as author of record.** Sign-offs between stages,
  merges, and the bet decision stay vpc's (methodology.md). The problem
  is how sign-off *reaches* him and how work *waits* for it — not
  whether he gives it.
- **Model quality or choice.** Which model fills which role is already
  solved by the roster (ADR 0001); this brief is not a model evaluation.
- **Merging without review.** Unattended work ends at an open PR or a
  question, never at `main`.
- **The planning phase.** Orchestrating planning artifacts is the
  separate `planning-orchestration` bet.
- **Multi-machine or multi-user operation.** One owner, one host
  (defiant) is the frame; scaling out is out of scope.
