"""Roster load + resolve.

Verifies spec success criteria:
- SC-1: each role resolves to the correct ModelRef.
- SC-5: a roster file containing a secret is rejected.
- SC-6: a validator/worker bound to different providers stays distinct.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from agent_framework.errors import RosterError, UnknownRoleError
from agent_framework.models import ModelRef
from agent_framework.roster import Roster

_ROSTER = """
[roles]
chief     = { provider = "anthropic", model = "claude-fable-5" }
worker    = { provider = "anthropic", model = "claude-sonnet-5" }
validator = { provider = "google",    model = "gemini-3-pro" }
"""


def _roster(text: str = _ROSTER) -> Roster:
    return Roster.from_dict(tomllib.loads(text))


def test_sc1_resolves_each_role_to_its_model_ref() -> None:
    """SC-1: each role resolves to the right {provider, model}."""
    r = _roster()
    assert r.resolve("chief") == ModelRef("anthropic", "claude-fable-5")
    assert r.resolve("worker") == ModelRef("anthropic", "claude-sonnet-5")
    assert r.resolve("validator") == ModelRef("google", "gemini-3-pro")


def test_sc5_roster_with_a_secret_field_is_rejected() -> None:
    """SC-5: a roster carrying an API key is rejected — secrets come from env."""
    leaky = """
    [roles]
    worker = { provider = "anthropic", model = "claude-sonnet-5", api_key = "sk-leak" }
    """
    with pytest.raises(RosterError):
        _roster(leaky)


def test_sc5_top_level_secret_is_rejected() -> None:
    """SC-5: a secret anywhere in the roster (not just a role) is rejected."""
    leaky = """
    token = "sk-top-level-leak"
    [roles]
    worker = { provider = "anthropic", model = "claude-sonnet-5" }
    """
    with pytest.raises(RosterError):
        _roster(leaky)


def test_sc6_distinct_providers_are_preserved() -> None:
    """SC-6: validator on a different provider than worker stays distinct."""
    r = _roster()
    assert r.resolve("worker").provider != r.resolve("validator").provider


def test_unknown_role_fails_loudly() -> None:
    """Roster-level loud failure (feeds SC-4 at dispatch): no silent default."""
    with pytest.raises(UnknownRoleError):
        _roster().resolve("nobody")


def test_missing_roles_table_is_rejected() -> None:
    with pytest.raises(RosterError):
        Roster.from_dict({"not_roles": {}})


def test_from_file_loads_the_example(tmp_path: Path) -> None:
    """from_file round-trips a TOML roster on disk."""
    p = tmp_path / "roster.toml"
    p.write_text(_ROSTER, encoding="utf-8")
    r = Roster.from_file(p)
    assert r.resolve("chief") == ModelRef("anthropic", "claude-fable-5")


def test_roster_loads_from_agent_framework_toml_with_project_table(tmp_path: Path) -> None:
    """Regression (project-portability plan risk): the combined
    agent-framework.toml carries a [project] table whose *content* may
    innocently mention words like "key" — the roster's secret-field
    rejection must scope to the roster, not trip on [project] values."""
    path = tmp_path / "agent-framework.toml"
    path.write_text(
        """
[roles]
worker = { provider = "anthropic", model = "m" }

[project]
gate_commands = ["make test"]
conventions_note = "The API key comes from the environment, never config."
""",
        encoding="utf-8",
    )
    roster = Roster.from_file(path)
    assert roster.resolve("worker").model == "m"
