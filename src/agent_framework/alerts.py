"""One way to reach vpc: a GitHub issue of record plus a best-effort phone push.

`notify` opens (or finds) one issue per alert key, labelled by kind, then
POSTs a short message to a Home Assistant webhook (R-3, R-4, R-6). It never
raises: every channel's outcome comes back in an `AlertReport` for the caller
to print (R-7). The webhook URL comes only from the environment (R-9).
"""

from __future__ import annotations

import json
import os
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from .proc import Runner, run_command

WEBHOOK_ENV = "AF_HA_WEBHOOK_URL"

# Sends (title, message) to vpc's phone; raises on failure.
Push = Callable[[str, str], None]


@dataclass(frozen=True)
class AlertReport:
    issue: str  # e.g. "opened #12", "found #12", "updated #12", "failed: ..."
    push: str  # "sent", "skipped: ...", "failed: ..."
    url: str | None = None

    def lines(self) -> tuple[str, ...]:
        return (f"github issue: {self.issue}", f"phone push: {self.push}")


class IssueTracker(Protocol):
    def find_open(self, label: str, marker: str) -> tuple[int, str] | None: ...
    def create(self, title: str, body: str, label: str) -> str: ...
    def update(self, number: int, body: str) -> None: ...


def marker(kind: str, key: str) -> str:
    """The title prefix that makes an alert findable again (one issue per key)."""
    return f"[{kind}:{key}]"


def notify(
    kind: str,
    key: str,
    title: str,
    body: str,
    push_message: str,
    *,
    tracker: IssueTracker,
    push: Push | None,
    update_existing: bool = False,
) -> AlertReport:
    """Record the alert as a GitHub issue, then push; report each outcome."""
    tag = marker(kind, key)
    url: str | None = None
    try:
        found = tracker.find_open(kind, tag)
        if found is None:
            url = tracker.create(f"{tag} {title}", body, kind)
            issue = f"opened #{url.rsplit('/', 1)[-1]}"
        else:
            number, url = found
            if update_existing:
                tracker.update(number, body)
                issue = f"updated #{number}"
            else:
                issue = f"found #{number}"
    except Exception as e:  # noqa: BLE001 — a failed channel is reported, never fatal (R-7)
        issue = f"failed: {_one_line(e)}"

    if push is None:
        return AlertReport(issue, f"skipped: {WEBHOOK_ENV} not set", url)
    try:
        push(f"{tag} {title}", f"{push_message} {url}" if url else push_message)
        sent = "sent"
    except Exception as e:  # noqa: BLE001 — the push is best-effort (R-7)
        sent = f"failed: {_one_line(e)}"
    return AlertReport(issue, sent, url)


def _one_line(e: Exception) -> str:
    return (str(e).splitlines() or [type(e).__name__])[0]


def ha_push(url: str, *, timeout_s: float = 10.0) -> Push:
    """A `Push` that POSTs {"title", "message"} to a Home Assistant webhook."""

    def send(title: str, message: str) -> None:
        data = json.dumps({"title": title, "message": message}).encode()
        req = urllib.request.Request(url, data, {"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            if resp.status >= 300:
                raise RuntimeError(f"webhook answered HTTP {resp.status}")

    return send


def push_from_env(env: Mapping[str, str] = os.environ) -> Push | None:
    """The configured phone push, or None when the webhook isn't set (R-9)."""
    url = env.get(WEBHOOK_ENV, "").strip()
    return ha_push(url) if url else None


class GhIssueTracker:
    """An `IssueTracker` over the `gh` CLI, through the shared subprocess seam."""

    def __init__(self, run: Runner = run_command) -> None:
        self._run = run

    def find_open(self, label: str, marker: str) -> tuple[int, str] | None:
        raw = self._run(["gh", "issue", "list", "--state", "open", "--label", label,
                         "--json", "number,title,url", "--limit", "100"])
        for item in json.loads(raw or "[]"):
            if str(item["title"]).startswith(marker):
                return int(item["number"]), str(item["url"])
        return None

    def create(self, title: str, body: str, label: str) -> str:
        self._run(["gh", "label", "create", label, "--force",
                   "--description", f"agent-framework {label} alerts"])
        url = self._run(["gh", "issue", "create", "--title", title, "--body", body,
                         "--label", label]).strip()
        if not url.startswith("http"):
            raise RuntimeError(f"gh issue create returned no URL: {url!r}")
        return url

    def update(self, number: int, body: str) -> None:
        self._run(["gh", "issue", "edit", str(number), "--body", body])
