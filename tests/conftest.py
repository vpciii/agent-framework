"""Suite-wide guards."""

from __future__ import annotations

import pytest

from agent_framework.alerts import WEBHOOK_ENV


@pytest.fixture(autouse=True)
def _no_real_phone_push(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let a test reach vpc's phone, even when the webhook is configured
    in the shell that runs the suite."""
    monkeypatch.delenv(WEBHOOK_ENV, raising=False)
