"""One way to reach vpc: a GitHub issue of record plus a best-effort phone push.

`notify` opens (or finds) one issue per alert key, labelled by kind, then
POSTs a short message to a Home Assistant webhook (R-3, R-4, R-6). It never
raises: every channel's outcome comes back in an `AlertReport` for the caller
to print (R-7). The webhook URL comes only from the environment (R-9).

When Pushover's three names are set, the same alert also goes to Pushover,
each text field encrypted end to end before the request is built
(specs/pushover-push, ADR 0011). Its values are read at the moment of
sending and appear nowhere but in that request.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import hmac
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .proc import Runner, run_command

WEBHOOK_ENV = "AF_HA_WEBHOOK_URL"
PUSHOVER_TOKEN_ENV = "AF_PUSHOVER_TOKEN"
PUSHOVER_USER_ENV = "AF_PUSHOVER_USER"
PUSHOVER_KEY_ENV = "AF_PUSHOVER_KEY"
PUSHOVER_ENV = (PUSHOVER_TOKEN_ENV, PUSHOVER_USER_ENV, PUSHOVER_KEY_ENV)
PUSHOVER_URL = "https://api.pushover.net/1/messages.json"
PUSHOVER_URL_TITLE = "Open the GitHub issue"
CUT_MARK = " [cut]"
# Pushover's limits, applied before encrypting (specs/pushover-push R-10).
_MAX_MESSAGE, _MAX_TITLE, _MAX_URL, _MAX_URL_TITLE = 1024, 250, 512, 100
_HEX_KEY = re.compile(r"[0-9a-fA-F]{64}")

# Sends (title, message) to vpc's phone; raises on failure.
Push = Callable[[str, str], None]

# POSTs (url, form body, timeout) and returns (HTTP status, response body);
# raises only when there is no answer (a timeout, no connection).
Post = Callable[[str, bytes, float], tuple[int, bytes]]


@dataclass(frozen=True)
class AlertReport:
    issue: str  # e.g. "opened #12", "found #12", "updated #12", "failed: ..."
    push: str  # "sent", "skipped: ...", "failed: ..."
    url: str | None = None
    pushover: str | None = None  # None when none of Pushover's names is set

    def lines(self) -> tuple[str, ...]:
        lines = (f"github issue: {self.issue}", f"phone push: {self.push}")
        return lines if self.pushover is None else (*lines, f"pushover: {self.pushover}")


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
    quiet_if_open: bool = False,
    detail: str | None = None,
    pushover_post: Post | None = None,
) -> AlertReport:
    """Record the alert as a GitHub issue, then push; report each outcome.

    With `quiet_if_open`, a condition whose issue is already open is not
    pushed again: a check that raises it on every pass reaches the phone once.
    `detail`, a longer text, goes only to Pushover, which encrypts it; the
    Home Assistant push never carries it.
    """
    tag = marker(kind, key)
    url: str | None = None
    already_open: int | None = None
    try:
        found = tracker.find_open(kind, tag)
        if found is None:
            url = tracker.create(f"{tag} {title}", body, kind)
            issue = f"opened #{url.rsplit('/', 1)[-1]}"
        else:
            number, url = found
            already_open = number
            if update_existing:
                tracker.update(number, body)
                issue = f"updated #{number}"
            else:
                issue = f"found #{number}"
    except Exception as e:  # noqa: BLE001 — a failed channel is reported, never fatal (R-7)
        issue = f"failed: {_one_line(e)}"

    configured = any(os.environ.get(name, "").strip() for name in PUSHOVER_ENV)
    if quiet_if_open and already_open is not None:
        quiet = f"skipped: already reported in #{already_open}"
        return AlertReport(issue, quiet, url, quiet if configured else None)
    if push is None:
        sent = f"skipped: {WEBHOOK_ENV} not set"
    else:
        try:
            push(f"{tag} {title}", f"{push_message} {url}" if url else push_message)
            sent = "sent"
        except Exception as e:  # noqa: BLE001 — the push is best-effort (R-7)
            sent = f"failed: {_one_line(e)}"
    over: str | None = None
    if configured:
        message = push_message if detail is None else f"{push_message}\n\n{detail}"
        over = _pushover(f"{tag} {title}", message, url, pushover_post or _post)
    return AlertReport(issue, sent, url, over)


def _one_line(e: Exception) -> str:
    return (str(e).splitlines() or [type(e).__name__])[0]


def _pushover(title: str, message: str, url: str | None, post: Post) -> str:
    """Send one encrypted push to Pushover; return its report line, never raise.

    The three values are read here, at the moment of sending, and go only into
    the request; no line returned quotes them, the response, or an error's text.
    """
    values = {name: os.environ.get(name, "").strip() for name in PUSHOVER_ENV}
    missing = [name for name, value in values.items() if not value]
    if missing:
        return f"skipped: {', '.join(missing)} not set"
    if not _HEX_KEY.fullmatch(values[PUSHOVER_KEY_ENV]):
        return f"skipped: {PUSHOVER_KEY_ENV} is not 64 hexadecimal characters"
    try:
        key = bytes.fromhex(values[PUSHOVER_KEY_ENV])
        if len(message) > _MAX_MESSAGE:
            message = message[: _MAX_MESSAGE - len(CUT_MARK)] + CUT_MARK
        fields = {
            "token": values[PUSHOVER_TOKEN_ENV],
            "user": values[PUSHOVER_USER_ENV],
            "encrypted": "1",
            "title": encrypt(title[:_MAX_TITLE], key),
            "message": encrypt(message, key),
        }
        if url:
            fields["url"] = encrypt(url[:_MAX_URL], key)
            fields["url_title"] = encrypt(PUSHOVER_URL_TITLE[:_MAX_URL_TITLE], key)
        status, raw = post(PUSHOVER_URL, urllib.parse.urlencode(fields).encode(), 10.0)
    except Exception as e:  # noqa: BLE001 — the kind only, never its text (R-4, R-8)
        return f"failed: {_kind(e)}"
    if status == 200 and _status_is_one(raw):
        return "sent"
    return f"failed: HTTP {status}"


def _status_is_one(raw: bytes) -> bool:
    try:
        answer = json.loads(raw)
    except ValueError:
        return False
    return isinstance(answer, dict) and answer.get("status") == 1


def _kind(e: Exception) -> str:
    reason = e.reason if isinstance(e, urllib.error.URLError) else e
    if isinstance(reason, TimeoutError):
        return "timeout"
    if isinstance(reason, OSError):
        return "no connection"
    return type(e).__name__


def encrypt(text: str, key: bytes) -> str:
    """Pushover's end-to-end scheme for one field: gzip, AES-256-CBC with PKCS7
    under a fresh IV, HMAC-SHA256 over IV + ciphertext; base64(IV|ct|HMAC)."""
    iv = os.urandom(16)
    padder = padding.PKCS7(128).padder()
    padded = padder.update(gzip.compress(text.encode("utf-8"))) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    mac = hmac.new(key, iv + ciphertext, hashlib.sha256).digest()
    return base64.b64encode(iv + ciphertext + mac).decode("ascii")


def _post(url: str, body: bytes, timeout_s: float) -> tuple[int, bytes]:
    """The network call: one POST of a form, no retry."""
    req = urllib.request.Request(
        url, body, {"Content-Type": "application/x-www-form-urlencoded"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return int(resp.status), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, b""


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
