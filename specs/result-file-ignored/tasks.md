# Tasks: The worker's result file never lands in a pull request

- **Status:** Draft
- **Spec:** ./spec.md

One task, one PR. It is the first task dispatched to a worker session
under the confinement profile (specs/worker-confinement R-12).

---

### [ ] T-1 — Ignore the result file in every session's worktree
- **Satisfies:** SC-1, SC-2, SC-3
- **Depends on:** —
- **Touches:** `src/agent_framework/worker/worktree.py`,
  `tests/worker/test_worktree.py`, `tests/worker/test_orchestrator.py`
  (its `_GitGh` fake only), `specs/result-file-ignored/spec.md` (the three
  Traceability rows only)
- **Brief:** In `create_worktree`, before the `git worktree add` call, ask
  git where the repository's exclude file is —
  `git rev-parse --path-format=absolute --git-path info/exclude`, through
  the `run` seam — and append the line `.worker-result.json` to that file
  unless a line already equals it (create the file and its directory if
  missing; keep every existing line; end the file with a newline). If git
  answers with an empty string, raise `WorktreeError` naming the exclude
  file and do not add the worktree. Take the file name from
  `session.RESULT_FILE` if that does not create an import cycle; otherwise
  define the constant once in `worktree.py` and import it from there in
  `session.py`.
  Tests: follow the real-git pattern already in
  `tests/worker/test_worktree.py` (the `stale_clone` fixture and `_git`
  helper build a real clone with a remote in `tmp_path`; `create_worktree`
  is then called with the default runner). Cite each criterion id in the
  docstring of the test that verifies it. Two existing fakes answer every
  unknown git command with an empty string and will now hit the new
  error: the `run` fakes inside `tests/worker/test_worktree.py`, and
  `_GitGh` in `tests/worker/test_orchestrator.py` — make each answer the
  new `rev-parse` call with a path under `tmp_path` (for `_GitGh`, a path
  under the current directory, which its fixture has already switched to
  a temporary one). Do not weaken or delete any existing assertion.
  Fill in the three Traceability rows in the spec with the full
  `tests/...::test_name` of each test; change nothing else in the spec.
  Do **not** modify `agent-framework.toml`, anything under `.github/`,
  `.gitignore`, or any file not listed in Touches. If the gate cannot be
  made green within those files, escalate.
- **Done when:** tests citing SC-1, SC-2 and SC-3 pass; the whole gate is
  green; the Traceability table has no pending row.
