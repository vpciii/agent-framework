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
