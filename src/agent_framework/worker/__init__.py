"""Worker agent: one task to one gated PR (ADR 0004 — orchestrated headless
Claude Code, not a bespoke API loop).

The orchestrator around a headless session: brief → worktree → session →
result → handoff. A worker reads its brief, never a conversation; its PR
carries the Satisfies declaration and faces the cite-the-test gate.
"""
