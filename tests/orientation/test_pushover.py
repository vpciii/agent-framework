"""The Pushover sender: encrypted, reported on its own line, never fatal.

Verifies spec success criteria (specs/pushover-push):
- SC-1: one POST with the token, the user key and the encrypted mark; the
  fields decrypt to the alert's text; a quieted alert makes no request.
- SC-2: no plain text in the body; a missing or malformed key → no request.
- SC-3: the three values appear in no log line, report line or issue body.
- SC-4: the link is the issue's address, not repeated in the message.
- SC-6: refused, limited or unanswered → reported, never fatal, one request.
- SC-7: the Home Assistant push and report unchanged; both send when both set.
- SC-8: a long detail is cut to 1,024 characters ending with the cut mark.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import hmac
import logging
import shutil
import urllib.parse
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from worker.test_orchestrator import _GitGh, _roster, _session, repo  # noqa: F401

from agent_framework import alerts
from agent_framework.alerts import CUT_MARK, PUSHOVER_URL, notify
from agent_framework.worker.orchestrator import work
from agent_framework.worker.types import Escalated

from .test_alerts import FakePush, FakeTracker

KEY = "0123456789abcdef" * 4
TOKEN, USER = "TOKEN-MARKER-a1b2", "USER-MARKER-c3d4"
TITLE, MESSAGE = "T-1 needs a decision", "T-1 needs a decision."


class FakePost:
    """Stands in for the network call: records each request, answers as told."""

    def __init__(self, status: int = 200, body: bytes = b'{"status":1}',
                 error: Exception | None = None) -> None:
        self.status, self.body, self.error = status, body, error
        self.requests: list[tuple[str, bytes, float]] = []

    def __call__(self, url: str, body: bytes, timeout_s: float) -> tuple[int, bytes]:
        self.requests.append((url, body, timeout_s))
        if self.error is not None:
            raise self.error
        return self.status, self.body

    def fields(self) -> dict[str, str]:
        [(_, body, _)] = self.requests
        return dict(urllib.parse.parse_qsl(body.decode()))


def decrypt(field: str, key_hex: str = KEY) -> str:
    """Reverse Pushover's scheme: check the HMAC, decrypt, unpad, gunzip."""
    key, raw = bytes.fromhex(key_hex), base64.b64decode(field)
    iv, ciphertext, mac = raw[:16], raw[16:-32], raw[-32:]
    assert hmac.compare_digest(mac, hmac.new(key, iv + ciphertext, hashlib.sha256).digest())
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return gzip.decompress(unpadder.update(padded) + unpadder.finalize()).decode()


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AF_PUSHOVER_TOKEN", TOKEN)
    monkeypatch.setenv("AF_PUSHOVER_USER", USER)
    monkeypatch.setenv("AF_PUSHOVER_KEY", KEY)


def _alert(post: FakePost, tracker: FakeTracker | None = None, push: FakePush | None = None,
           **kw: object) -> alerts.AlertReport:
    return notify("escalation", "spec/T-1", TITLE, "body", MESSAGE, tracker=tracker or FakeTracker(),
                  push=push, pushover_post=post, **kw)  # type: ignore[arg-type]


def test_sc1_one_encrypted_post_that_decrypts_to_the_alert(configured: None) -> None:
    """SC-1: one POST to the endpoint with token, user and encrypted=1; the
    title, message, link and link's title decrypt; two sends differ."""
    post = FakePost()
    report = _alert(post)

    assert report.pushover == "sent" and report.lines()[2] == "pushover: sent"
    [(url, _, timeout)] = post.requests
    assert url == PUSHOVER_URL == "https://api.pushover.net/1/messages.json" and timeout == 10.0
    f = post.fields()
    assert (f["token"], f["user"], f["encrypted"]) == (TOKEN, USER, "1")
    assert decrypt(f["title"]) == f"[escalation:spec/T-1] {TITLE}"
    assert decrypt(f["message"]) == MESSAGE
    assert decrypt(f["url"]) == "https://gh/i/40"
    assert decrypt(f["url_title"]) == alerts.PUSHOVER_URL_TITLE

    again = FakePost()
    _alert(again)
    assert again.fields()["message"] != f["message"]  # a fresh IV every time
    assert decrypt(again.fields()["message"]) == MESSAGE


def test_sc1_an_alert_quieted_because_its_issue_is_open_makes_no_request(configured: None) -> None:
    """SC-1: quiet_if_open with the issue open → no request; the line says
    what the Home Assistant line says."""
    post = FakePost()
    tracker = FakeTracker({"[escalation:spec/T-1]": (7, "https://gh/i/7")})
    report = _alert(post, tracker, FakePush(), quiet_if_open=True)

    assert post.requests == []
    assert report.pushover == report.push == "skipped: already reported in #7"


def test_sc2_no_plain_text_and_a_bad_key_makes_no_request(
    configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SC-2: the body holds no title, message or link in plain text; a missing
    or malformed key → no request, `skipped` naming it, Home Assistant still sent."""
    post = FakePost()
    _alert(post)
    [(_, body, _)] = post.requests
    for plain in (TITLE, MESSAGE, "gh/i/40", "decision"):
        assert plain not in body.decode() and plain not in urllib.parse.unquote_plus(body.decode())

    for bad in ("", "ab" * 31, "zz" * 32):
        if bad:
            monkeypatch.setenv("AF_PUSHOVER_KEY", bad)
        else:
            monkeypatch.delenv("AF_PUSHOVER_KEY")
        post, push = FakePost(), FakePush()
        report = _alert(post, push=push)
        assert post.requests == []
        assert report.pushover is not None and report.pushover.startswith("skipped:")
        assert "AF_PUSHOVER_KEY" in report.pushover
        assert (bad or "x") not in report.pushover
        assert report.push == "sent" and len(push.sent) == 1


def test_sc3_the_three_values_appear_in_no_log_report_or_issue(
    configured: None, caplog: pytest.LogCaptureFixture
) -> None:
    """SC-3: with marker values, none reaches a log record, a report line or
    the issue's body, even when the call fails quoting the whole request."""
    class BodyTracker(FakeTracker):
        def __init__(self) -> None:
            super().__init__()
            self.bodies: list[str] = []

        def create(self, title: str, body: str, label: str) -> str:
            self.bodies.append(title + body)
            return super().create(title, body, label)

    caplog.set_level(logging.DEBUG)
    seen: list[str] = []

    def leaky(url: str, body: bytes, timeout_s: float) -> tuple[int, bytes]:
        seen.append(body.decode())
        raise RuntimeError(f"POST {url} {body.decode()} refused")

    for post in (FakePost(), FakePost(400, b'{"token":"%s"}' % TOKEN.encode()), leaky):
        tracker = BodyTracker()
        report = notify("escalation", "spec/T-1", TITLE, "body", MESSAGE, tracker=tracker,
                        push=None, pushover_post=post)
        logging.getLogger("agent_framework").info("%s", "; ".join(report.lines()))
        text = "\n".join([*report.lines(), *tracker.bodies, *(r.getMessage() for r in caplog.records)])
        for value in (TOKEN, USER, KEY):
            assert value not in text
    assert TOKEN in seen[0]  # the leaky call really was handed the request
    assert report.pushover == "failed: RuntimeError"


def test_sc4_the_link_is_the_issue_and_not_in_the_message(configured: None) -> None:
    """SC-4: decrypted link = the issue's address, absent from the message;
    no issue → no link fields."""
    post = FakePost()
    report = _alert(post)
    f = post.fields()
    assert decrypt(f["url"]) == report.url == "https://gh/i/40"
    assert "https://gh/i/40" not in decrypt(f["message"])

    post = FakePost()
    _alert(post, FakeTracker(fail=True))
    assert "url" not in post.fields() and "url_title" not in post.fields()


@pytest.mark.parametrize("post, line", [
    (FakePost(400, b'{"status":0,"errors":["x"]}'), "failed: HTTP 400"),
    (FakePost(429, b"{}"), "failed: HTTP 429"),
    (FakePost(500, b"oops"), "failed: HTTP 500"),
    (FakePost(200, b'{"status":0}'), "failed: HTTP 200"),
    (FakePost(error=TimeoutError("timed out after 10s")), "failed: timeout"),
    (FakePost(error=ConnectionRefusedError("refused")), "failed: no connection"),
])
def test_sc6_a_refused_limited_or_silent_pushover_is_one_failed_line(
    configured: None, post: FakePost, line: str
) -> None:
    """SC-6: notify returns normally, one request, a `failed` line with the
    status or the kind of error and nothing else."""
    report = _alert(post, push=FakePush())
    assert len(post.requests) == 1
    assert report.pushover == line and report.push == "sent"


@pytest.mark.parametrize("status, error", [
    (400, None), (429, None), (500, None), (200, TimeoutError("no answer")),
])
def test_sc6_a_failing_pushover_does_not_change_a_worker_run(
    repo: Path, monkeypatch: pytest.MonkeyPatch,  # noqa: F811
    status: int, error: Exception | None,
) -> None:
    """SC-6: an escalation meeting a failing Pushover ends as one with Pushover unset."""
    def run() -> tuple[Escalated, list[str]]:
        _, session = _session({"status": "escalated", "detail": "which way?",
                               "spec_location": "spec.md#r-1"})
        tracker = FakeTracker()
        outcome = work("fixture", "T-1", _roster(), specs_dir=repo / "specs", run=_GitGh(),
                       session_run=session, tracker=tracker, push_factory=lambda: None)
        assert isinstance(outcome, Escalated)
        return outcome, [t for t, _ in tracker.created]

    unset, unset_issues = run()
    # Start again from the same state: no worktree, no escalation numbered yet.
    shutil.rmtree(repo / ".worktrees")
    shutil.rmtree(repo / "specs" / "fixture" / "escalations")
    post = FakePost(status, b'{"status":0}', error)
    monkeypatch.setattr(alerts, "_post", post)
    monkeypatch.setenv("AF_PUSHOVER_TOKEN", TOKEN)
    monkeypatch.setenv("AF_PUSHOVER_USER", USER)
    monkeypatch.setenv("AF_PUSHOVER_KEY", KEY)
    failing, failing_issues = run()

    assert failing == unset and failing_issues == unset_issues
    assert len(post.requests) == 1


def test_sc7_only_the_webhook_set_gives_todays_two_lines() -> None:
    """SC-7: with no Pushover name set → today's push and two lines, no request."""
    post, push = FakePost(), FakePush()
    report = _alert(post, push=push)
    assert post.requests == [] and report.pushover is None
    assert report.lines() == ("github issue: opened #40", "phone push: sent")
    assert push.sent == [(f"[escalation:spec/T-1] {TITLE}", f"{MESSAGE} https://gh/i/40")]


def test_sc7_both_configured_both_are_sent_with_a_line_each(configured: None) -> None:
    """SC-7: both sent, three lines; the detail never reaches Home Assistant."""
    post, push = FakePost(), FakePush()
    report = _alert(post, push=push, detail="the worker's question")
    assert report.lines() == ("github issue: opened #40", "phone push: sent", "pushover: sent")
    assert push.sent == [(f"[escalation:spec/T-1] {TITLE}", f"{MESSAGE} https://gh/i/40")]
    assert decrypt(post.fields()["message"]) == f"{MESSAGE}\n\nthe worker's question"


def test_sc8_a_long_detail_is_cut_to_the_limit_with_the_mark(configured: None) -> None:
    """SC-8: a 3,000-character detail decrypts to at most 1,024 characters
    ending with the cut mark."""
    post = FakePost()
    _alert(post, detail="q" * 3000)
    message = decrypt(post.fields()["message"])
    assert len(message) <= 1024 and message.endswith(CUT_MARK)
    assert message.startswith(MESSAGE)
    assert len(message) == 1024
