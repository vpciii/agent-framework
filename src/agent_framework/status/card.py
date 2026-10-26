"""The resume card: where the project stands and its one next action.

Derived from the repository's artifacts alone (R-1) plus an optional GitHub
snapshot (R-2). Pure over its inputs, so the same repository state renders
the same card; the GitHub snapshot is fetched separately through the shared
subprocess seam.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from ..proc import Runner

TERMINAL = frozenset({"Implemented", "Retired", "Superseded", "Withdrawn"})
ALERT_LABELS = ("escalation", "timeout")

_STATUS_RE = re.compile(r"^\s*-\s*\*\*Status:\*\*\s*(.+?)\s*$", re.MULTILINE)
_OPEN_TASK_RE = re.compile(r"^### \[ \] (\S+) — (.+?)\s*(?:\((?:this PR|#\d+)\))?\s*$", re.MULTILINE)


@dataclass(frozen=True)
class SpecState:
    slug: str
    status: str
    open_tasks: tuple[tuple[str, str], ...]  # (task id, summary)
    has_tasks: bool  # False for a compact spec (no tasks.md)


@dataclass(frozen=True)
class BetState:
    slug: str
    status: str
    has_spec: bool  # some spec names planning/<slug>/ as its planning record


@dataclass(frozen=True)
class EscalationState:
    path: str  # repo-relative
    status: str


@dataclass(frozen=True)
class RepoState:
    name: str
    specs: tuple[SpecState, ...]
    bets: tuple[BetState, ...]
    escalations: tuple[EscalationState, ...]


@dataclass(frozen=True)
class GitHubItem:
    number: int
    title: str
    url: str


@dataclass(frozen=True)
class GitHubSnapshot:
    open_prs: tuple[GitHubItem, ...]
    open_alerts: tuple[GitHubItem, ...]  # open issues labelled escalation / timeout


def _status(text: str) -> str:
    m = _STATUS_RE.search(text)
    if m is None:
        return "Unknown"
    return m.group(1).split(" (")[0].split(" — ")[0].strip()


def read_repo(root: Path) -> RepoState:
    """Collect specs, bets and escalations from the artifacts under `root`."""
    spec_texts = {
        p.parent.name: p.read_text(encoding="utf-8")
        for p in sorted((root / "specs").glob("*/spec.md"))
    }
    specs = []
    for slug, text in spec_texts.items():
        tasks_path = root / "specs" / slug / "tasks.md"
        open_tasks: tuple[tuple[str, str], ...] = ()
        if tasks_path.is_file():
            tasks_text = tasks_path.read_text(encoding="utf-8")
            open_tasks = tuple((m.group(1), m.group(2)) for m in _OPEN_TASK_RE.finditer(tasks_text))
        specs.append(SpecState(slug, _status(text), open_tasks, tasks_path.is_file()))

    bets = tuple(
        BetState(
            p.parent.name,
            _status(p.read_text(encoding="utf-8")),
            any(f"planning/{p.parent.name}/" in t for t in spec_texts.values()),
        )
        for p in sorted((root / "planning").glob("*/bet.md"))
    )
    escalations = tuple(
        EscalationState(str(p.relative_to(root)), _status(p.read_text(encoding="utf-8")))
        for p in sorted((root / "specs").glob("*/escalations/*.md"))
    )
    return RepoState(root.resolve().name, tuple(specs), bets, escalations)


def github_snapshot(run: Runner) -> GitHubSnapshot:
    """Open PRs and open escalation/timeout issues; raises if `gh` fails."""
    fields = ["--json", "number,title,url", "--limit", "100"]

    def items(raw: str) -> list[GitHubItem]:
        return [GitHubItem(int(i["number"]), str(i["title"]), str(i["url"]))
                for i in json.loads(raw or "[]")]

    prs = items(run(["gh", "pr", "list", "--state", "open", *fields]))
    alerts: dict[int, GitHubItem] = {}
    for label in ALERT_LABELS:
        for item in items(run(["gh", "issue", "list", "--state", "open", "--label", label, *fields])):
            alerts[item.number] = item
    return GitHubSnapshot(
        tuple(sorted(prs, key=lambda i: i.number)),
        tuple(alerts[n] for n in sorted(alerts)),
    )


def active_specs(state: RepoState) -> tuple[SpecState, ...]:
    return tuple(s for s in state.specs if s.status not in TERMINAL)


def next_action(state: RepoState, github: GitHubSnapshot | None) -> str:
    """Exactly one next action, by a fixed precedence (spec Approach)."""
    if github is not None and github.open_alerts:
        item = github.open_alerts[0]
        return f"Answer #{item.number}: {item.title} ({item.url})"
    if github is None:
        open_files = [e for e in state.escalations if e.status == "Open"]
        if open_files:
            return f"Answer the escalation in {open_files[0].path}"
    for spec in active_specs(state):
        if spec.status in ("Draft", "Under review"):
            return f"Sign off spec {spec.slug} ({spec.status})"
    for spec in active_specs(state):
        if spec.status == "Approved" and spec.open_tasks:
            task_id, summary = spec.open_tasks[0]
            return f"Next task {task_id} of {spec.slug}: {summary}"
        if spec.status == "Approved" and not spec.has_tasks:
            return f"Implement spec {spec.slug} (compact spec)"
    if github is not None and github.open_prs:
        pr = github.open_prs[0]
        return f"Review PR #{pr.number}: {pr.title} ({pr.url})"
    for bet in state.bets:
        if bet.status == "Placed" and not bet.has_spec:
            return f"Write the spec for bet {bet.slug}"
    return "Nothing pending"


def render(state: RepoState, github: GitHubSnapshot | None, github_error: str | None = None) -> str:
    """The card as Markdown."""
    lines = [f"# {state.name} — resume card", "",
             f"**Next action:** {next_action(state, github)}", "", "## Specs in progress", ""]
    specs = active_specs(state)
    lines += [f"- `{s.slug}` — {s.status}" for s in specs] or ["- none"]
    tasks = [(s.slug, t, summary) for s in specs for t, summary in s.open_tasks]
    lines += ["", "## Open tasks", ""]
    lines += [f"- `{slug}` {t} — {summary}" for slug, t, summary in tasks] or ["- none"]
    lines += ["", "## Bets", ""]
    lines += [f"- `{b.slug}` — {b.status}" for b in state.bets] or ["- none"]
    lines += ["", "## Escalation files", ""]
    lines += [f"- `{e.path}` — {e.status}" for e in state.escalations] or ["- none"]
    lines += ["", "## GitHub", ""]
    if github is None:
        reason = f": {github_error}" if github_error else ""
        lines.append(f"- Pull request and issue status unavailable{reason}")
    else:
        lines += [f"- PR #{p.number} — {p.title}" for p in github.open_prs] or ["- no open PRs"]
        lines += [f"- Issue #{i.number} — {i.title}" for i in github.open_alerts] or [
            "- no open escalation or timeout issues"]
    return "\n".join(lines) + "\n"
