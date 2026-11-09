# Spec: The worker's result file never lands in a pull request

- **Status:** Implemented
- **Date:** 2026-11-09
- **Author:** Claude (draft) — vpc is author of record
- **Related ADRs:** ADR 0004 (the worker is a headless session), ADR 0007
  (worker session confinement — the handoff this feeds)

> This spec is editable while `Draft` / `Under review` / `Approved`.
> When the PR that marks it `Implemented` merges it **freezes** into a
> historical record (methodology ADR 0027);
> a contradiction found later goes to a test, a new spec, or an ADR —
> not back into this file (methodology §2, §8).

## Problem

A worker session reports its outcome by writing `.worker-result.json` in
the root of its worktree. Nothing tells git to ignore that file: it is
untracked, so a session that stages its work with `git add -A` commits it,
and the orchestrator pushes it in the task's pull request. The file is the
session's message to the orchestrator, not part of the change. It has not
yet been seen in a merged PR, but only because sessions so far have staged
files by name.

A target project could list the file in its own `.gitignore`, but that
makes every adopting repository carry a line for the framework's
bookkeeping, and a repository that forgets gets the file in its history.

## Goals

1. A session cannot commit its result file by accident, however it stages.
2. No adopting repository has to change a tracked file for this.

## Non-goals

- The other files the orchestrator or a session may leave in a kept
  worktree (`HANDOFF.md`, progress notes): they are written only when
  nothing is pushed.
- Changing where the result file lives or how it is read.
- A handoff-check rule for a result file that was committed anyway.

## Requirements

- **R-1 (MUST)** When the orchestrator creates a session's worktree,
  `.worker-result.json` is ignored by git in that worktree: it is not
  reported as untracked, and `git add -A` does not stage it.
- **R-2 (MUST NOT)** The orchestrator MUST NOT change any tracked file of
  the repository to achieve R-1.
- **R-3 (MUST)** Repeated dispatches leave the ignore entry present
  exactly once, and leave every line already in the repository's exclude
  file untouched.
- **R-4 (MUST)** If the place to record the ignore entry cannot be
  determined, creating the worktree fails with a `WorktreeError` that says
  so, and no worktree is created.

## Success criteria

- **SC-1** — Against a real git repository: after the orchestrator
  creates a worktree, with a `.worker-result.json` and another new file
  written in it, `git status --porcelain` lists the other file and not the
  result file, `git add -A` stages the other file and not the result file,
  and no tracked file differs from the commit the tree was cut from.
  (R-1, R-2)
- **SC-2** — Against a real git repository whose exclude file already has
  content: after worktrees are created for two different tasks, that
  content is still there, unchanged, and the result file's entry appears
  exactly once. (R-3)
- **SC-3** — When git reports no location for the exclude file, creating
  the worktree raises `WorktreeError` naming the exclude file, and no
  `git worktree add` is issued. (R-4)

## Approach

git keeps a per-repository ignore list outside the working tree, in
`info/exclude` under the repository's git directory; a linked worktree
shares it. `create_worktree` asks git for its path
(`git rev-parse --path-format=absolute --git-path info/exclude`), appends
`.worker-result.json` on its own line if no line already equals it, and
only then adds the worktree. The entry is written before the worktree
exists so that a failure leaves nothing behind (R-4).

The entry stays after the worktree is removed: it names a file only the
framework writes, and removing it would race a second session.

### Decisions

- *2026-11-09* — vpc approved the spec and its task as drafted.

## Rollout and undo

One PR. Undo is reverting it; the one line left in a repository's
`info/exclude` is inert and can be deleted by hand.

## Open questions

- [x] None open. Signed off 2026-11-09.

## Out of scope (for now)

- Ignoring `HANDOFF.md` and session progress notes the same way.

## Traceability

| Criterion | Requirement(s) | Verified by (test) |
|---|---|---|
| SC-1 | R-1, R-2 | `tests/worker/test_worktree.py::test_sc1_result_file_is_ignored_in_a_fresh_worktree` |
| SC-2 | R-3 | `tests/worker/test_worktree.py::test_sc2_existing_exclude_content_kept_and_entry_added_once` |
| SC-3 | R-4 | `tests/worker/test_worktree.py::test_sc3_no_exclude_location_raises_and_adds_no_worktree` |
