"""The roster currency workflow file.

Verifies spec success criteria (specs/roster-currency-check):
- SC-5: schedule + manual dispatch only; contents:read, issues:write and
  id-token:write only; credentials only from secrets.*/vars.*; not in ci.yml.
- SC-9: the federation step gets the federation variables and no API key;
  the fallback step gets the API key only when federation is not configured;
  the OIDC token is requested for audience https://api.anthropic.com.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _ROOT / ".github" / "workflows" / "roster-currency.yml"
_FEDERATION_VARS = {
    "ANTHROPIC_FEDERATION_RULE_ID",
    "ANTHROPIC_ORGANIZATION_ID",
    "ANTHROPIC_SERVICE_ACCOUNT_ID",
    "ANTHROPIC_IDENTITY_TOKEN_FILE",
}


def _workflow() -> dict[Any, Any]:
    data = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _steps() -> dict[str, dict[str, Any]]:
    steps = _workflow()["jobs"]["check"]["steps"]
    return {s["name"]: s for s in steps if "name" in s}


def test_sc5_triggers_permissions_and_isolation_from_the_gate() -> None:
    """SC-5: triggers, least-privilege token, and no reference from ci.yml."""
    wf = _workflow()
    triggers = wf[True]  # YAML 1.1 reads the bare key `on` as boolean True
    assert set(triggers) == {"schedule", "workflow_dispatch"}
    assert wf["permissions"] == {"contents": "read", "issues": "write", "id-token": "write"}
    ci = (_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "roster-currency" not in ci and "agent_framework.currency" not in ci


def test_sc5_credentials_come_only_from_secrets_and_vars() -> None:
    """SC-5: every credential-looking env value is a secrets.* or vars.* expression."""
    for step in _steps().values():
        for name, value in (step.get("env") or {}).items():
            if re.search(r"KEY|TOKEN|_ID$", name) and name != "ANTHROPIC_IDENTITY_TOKEN_FILE":
                assert re.fullmatch(r"\$\{\{ (secrets|vars)\.\w+ \}\}", value), (name, value)


def test_sc9_federation_and_api_key_are_never_combined() -> None:
    """SC-9: federation step has the four variables and no key; fallback has the key."""
    steps = _steps()
    federation, fallback = steps["Check (federation)"], steps["Check (API key fallback)"]
    assert federation["if"] == "vars.ANTHROPIC_FEDERATION_RULE_ID != ''"
    assert _FEDERATION_VARS <= set(federation["env"])
    assert "ANTHROPIC_API_KEY" not in federation["env"]
    assert fallback["if"] == "vars.ANTHROPIC_FEDERATION_RULE_ID == ''"
    assert "ANTHROPIC_API_KEY" in fallback["env"]
    assert not _FEDERATION_VARS & set(fallback["env"])


def test_sc9_oidc_token_requested_for_the_anthropic_audience() -> None:
    """SC-9: the identity token is fetched only for federation, with Anthropic's audience."""
    fetch = _steps()["Fetch GitHub OIDC token for Anthropic"]
    assert fetch["if"] == "vars.ANTHROPIC_FEDERATION_RULE_ID != ''"
    assert "audience=https://api.anthropic.com" in fetch["run"]
