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


def without_section(text: str, title: str) -> str:
    """`text` with its `## <title>` section (heading and body) removed — for
    comparing two versions of a spec everywhere but that section."""
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", text, re.MULTILINE))
    for i, m in enumerate(matches):
        if m.group(1).strip().lower() == title.lower():
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            return text[: m.start()] + text[end:]
    return text


def normalize_checkboxes(text: str) -> str:
    """`text` with every list-item or heading checkbox mark (`[ ]`, `[~]`,
    `[x]`) made the same — for comparing two versions of a tasks file in
    everything but which tasks are ticked."""
    return re.sub(
        r"^(\s*(?:[-*]|#{1,6})\s+)\[[ ~xX]\]", r"\1[ ]", text, flags=re.MULTILINE
    )


def traceability(spec_text: str) -> dict[str, tuple[str, ...]]:
    """A spec's Traceability table: criterion id → the tests its row names.

    Reads the same conventions as the spec-coverage checker: one row per
    criterion (`| SC-n | R-… | `path::test_name`, … |`), references in
    backticks, and a `*(pending)*` cell meaning none yet. A criterion with
    no row is absent from the result; one with a pending or empty cell maps
    to an empty tuple.
    """
    table: dict[str, tuple[str, ...]] = {}
    for raw in section(spec_text, "Traceability").splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        refs = tuple(r.strip() for r in re.findall(r"`([^`]+)`", cells[2]))
        for sc_id in re.findall(r"\bSC-\d+\b", cells[0]):
            table[sc_id] = table.get(sc_id, ()) + refs
    return table
