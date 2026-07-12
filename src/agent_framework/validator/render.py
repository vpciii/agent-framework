"""Render a verdict to human-readable markdown (spec verdict-rendering R-1, R-2).

Derived purely from the verdict value — no I/O, no second representation to
keep in sync with the JSON form in `verdict.py`.
"""

from __future__ import annotations

from .verdict import Pass, Reject, Verdict


def render_verdict(verdict: Verdict) -> str:
    """Render a `Pass` or `Reject` verdict to markdown."""
    if isinstance(verdict, Pass):
        lines = [f"# PASS — {verdict.task_id}", ""]
        for citation in verdict.citations:
            lines.append(f"- {citation.criterion}: `{citation.test}`")
        lines.append("")
        lines.append(f"CI: {verdict.ci}")
        return "\n".join(lines)

    assert isinstance(verdict, Reject)
    lines = [f"# REJECT — {verdict.task_id}", ""]
    for finding in verdict.findings:
        lines.append(f"- check: {finding.check}")
        lines.append(f"  finding: {finding.finding}")
        lines.append(f"  evidence: {finding.evidence}")
    return "\n".join(lines)
