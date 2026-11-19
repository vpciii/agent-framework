"""Suite-wide guards."""

from __future__ import annotations

import pytest

from agent_framework.alerts import PUSHOVER_ENV, WEBHOOK_ENV


@pytest.fixture(autouse=True)
def _no_real_phone_push(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let a test reach vpc's phone, even when the webhook or Pushover
    is configured in the shell that runs the suite."""
    for name in (WEBHOOK_ENV, *PUSHOVER_ENV):
        monkeypatch.delenv(name, raising=False)
