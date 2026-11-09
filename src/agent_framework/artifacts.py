"""Reading the methodology's artifacts: one parser for `spec.md` / `tasks.md`.

Pure text functions shared by the worker's brief and the validator's
collector, so the two roles can never disagree about what a task or a
success criterion says (specs/validator-evidence, Approach).
"""

from __future__ import annotations

import re


def section(text: str, title: str) -> str:
    """Body of the `## <title>` section of a spec file, or ""."""
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", text, re.MULTILINE))
    for i, m in enumerate(matches):
        if m.group(1).strip().lower() == title.lower():
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            return text[m.end() : end].strip()
    return ""


def task_block(tasks_text: str, task_id: str) -> str | None:
    """The verbatim `### [ ] <task-id> …` block of a `tasks.md`, or None."""
    m = re.search(
        rf"^### \[.\] {re.escape(task_id)}\b.*?(?=^### |^---|\Z)",
        tasks_text,
        re.MULTILINE | re.DOTALL,
    )
    return m.group(0).strip() if m else None


def criterion_text(spec_text: str, sc_id: str) -> str | None:
    """The `**SC-n** …` entry of a spec's Success criteria section, or None."""
    m = re.search(
        rf"^- \*\*{re.escape(sc_id)}\*\*(.*?)(?=^- \*\*SC-|\Z)",
        section(spec_text, "Success criteria"),
        re.MULTILINE | re.DOTALL,
    )
    return f"**{sc_id}**{m.group(1).rstrip()}" if m else None
