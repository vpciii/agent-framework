"""The roster currency check's one tracking issue (R-5, R-11).

`sync_issue` decides; an `IssueTracker` acts. The `gh`-backed tracker shells
out through the shared subprocess seam; tests pass a fake.
"""

from __future__ import annotations

from typing import Protocol

from ..proc import Runner, run_command
from .check import Finding, Severity

LABEL = "roster-currency"
TITLE = "Roster currency check: a bound model needs attention"


class IssueTracker(Protocol):
    def find_open(self, label: str) -> int | None: ...
    def create(self, title: str, body: str, label: str) -> int: ...
    def update(self, number: int, body: str) -> None: ...
    def close(self, number: int, comment: str) -> None: ...


def needs_attention(findings: list[Finding]) -> bool:
    """Failing or unchecked findings keep the issue open; advisories alone do not."""
    return any(f.severity is not Severity.ADVISORY for f in findings)


def render(findings: list[Finding], run_url: str | None = None) -> str:
    lines = [f"- **{f.severity}** — `{f.role}` ({f.provider}, `{f.model}`): {f.message}"
             for f in findings] or ["- every bound model is served; nothing to report"]
    if run_url:
        lines.append(f"\nLatest run: {run_url}")
    return "\n".join(lines)


def sync_issue(findings: list[Finding], tracker: IssueTracker, run_url: str | None = None) -> str:
    """Open, update, or close the tracking issue; returns what it did."""
    existing = tracker.find_open(LABEL)
    body = render(findings, run_url)
    if needs_attention(findings):
        if existing is None:
            return f"opened #{tracker.create(TITLE, body, LABEL)}"
        tracker.update(existing, body)
        return f"updated #{existing}"
    if existing is not None:
        tracker.close(existing, f"Resolved: no failing or unchecked findings.\n\n{body}")
        return f"closed #{existing}"
    return "no issue needed"


class GhIssueTracker:
    """An `IssueTracker` over the `gh` CLI (GH_TOKEN from the environment)."""

    def __init__(self, run: Runner = run_command) -> None:
        self._run = run

    def find_open(self, label: str) -> int | None:
        out = self._run(["gh", "issue", "list", "--label", label, "--state", "open",
                         "--json", "number", "--jq", ".[0].number // empty"]).strip()
        return int(out) if out else None

    def create(self, title: str, body: str, label: str) -> int:
        self._run(["gh", "label", "create", label, "--force",
                   "--description", "Roster currency check findings"])
        url = self._run(["gh", "issue", "create", "--title", title, "--body", body,
                         "--label", label]).strip()
        return int(url.rsplit("/", 1)[-1])

    def update(self, number: int, body: str) -> None:
        self._run(["gh", "issue", "edit", str(number), "--body", body])

    def close(self, number: int, comment: str) -> None:
        self._run(["gh", "issue", "close", str(number), "--comment", comment])
