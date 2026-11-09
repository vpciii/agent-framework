"""The adoption document.

Verifies SC-5 (R-5's machine-checkable half): docs/adoption.md exists and
covers every step the opn-mcp pilot actually required. R-6's half — the
cited pilot run — is live evidence in the delivery PR (#41): worker PR
opn-mcp#21, gated PASS in opn-mcp's CI.
"""

from __future__ import annotations

from pathlib import Path

_DOC = Path(__file__).parent.parent / "docs" / "adoption.md"


def test_sc5_adoption_doc_covers_every_pilot_required_step() -> None:
    """SC-5: each step the pilot needed is documented."""
    text = _DOC.read_text(encoding="utf-8")
    for required in (
        "agent-framework.toml",   # the config file
        "gate_commands",          # the per-project gate
        ".worktrees/",            # gitignore entry
        "GEMINI_API_KEY",         # the secret
        "continue-on-error",      # advisory, never blocking
        "agent-framework-worker", # the dispatch entry point
        "check names",            # the pilot's ignore-check lesson (opn-mcp#22)
        "escalation",             # first-task brief-authoring lessons
        "Touches",                # bookkeeping-in-the-brief lesson
    ):
        assert required in text, f"adoption doc is missing coverage of: {required}"


def test_adoption_doc_describes_the_confined_dispatch() -> None:
    """specs/worker-confinement R-13: the doc carries the confined dispatch
    command and every field that widens the profile — and no longer tells
    anyone to bypass permissions."""
    text = _DOC.read_text(encoding="utf-8")
    for required in (
        "session_write_paths", "session_read_paths", "session_network", "session_env",
        "protected_paths",
        "handoff refused",       # exit code 4
        "allow list",            # what a refused host looks like
        "macOS only",            # the platform limit
        "default branch",        # the keyed CI job never runs a PR's code
    ):
        assert required in text, f"adoption doc is missing coverage of: {required}"
    assert "--dangerously-skip-permissions" not in text
    assert "--session-arg" not in text
