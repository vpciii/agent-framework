"""The roster: the single place that binds each role to a concrete model.

Loaded from a TOML file (stdlib ``tomllib`` — no dependency). Secrets never
live here; provider API keys come from the environment (ADR 0001, §9).
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from .errors import RosterError, UnknownRoleError
from .models import ModelRef

# Field names that must never appear in a roster — they smell like a secret,
# and secrets belong in the environment, not in config (SC-5).
_SECRET_FIELDS = frozenset(
    {"api_key", "apikey", "key", "token", "secret", "password", "credential"}
)


def _reject_secret_fields(table: dict[str, Any], where: str) -> None:
    for field in table:
        if field.lower() in _SECRET_FIELDS:
            raise RosterError(
                f"{where} contains a secret-looking field {field!r}; "
                "API keys come from the environment, never the roster"
            )


class Roster:
    """Maps role names (e.g. "chief", "worker", "validator") to `ModelRef`s."""

    def __init__(self, roles: dict[str, ModelRef]) -> None:
        self._roles = dict(roles)

    @classmethod
    def from_file(cls, path: str | Path) -> Roster:
        """Load a roster from a TOML file."""
        return cls.from_dict(tomllib.loads(Path(path).read_text(encoding="utf-8")))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Roster:
        """Build a roster from already-parsed TOML data, validating as we go."""
        _reject_secret_fields(data, where="the roster")

        roles_table = data.get("roles")
        if not isinstance(roles_table, dict):
            raise RosterError("roster is missing a [roles] table")

        roles: dict[str, ModelRef] = {}
        for role, binding in roles_table.items():
            if not isinstance(binding, dict):
                raise RosterError(
                    f"role {role!r} must map to a table with 'provider' and 'model'"
                )
            _reject_secret_fields(binding, where=f"role {role!r}")

            provider = binding.get("provider")
            model = binding.get("model")
            if not isinstance(provider, str) or not isinstance(model, str):
                raise RosterError(
                    f"role {role!r} needs string 'provider' and 'model'"
                )
            roles[role] = ModelRef(provider=provider, model=model)

        if not roles:
            raise RosterError("roster defines no roles")
        return cls(roles)

    def resolve(self, role: str) -> ModelRef:
        """Resolve a role to its bound model, or fail loudly if unbound."""
        try:
            return self._roles[role]
        except KeyError:
            known = ", ".join(sorted(self._roles)) or "(none)"
            raise UnknownRoleError(
                f"no binding for role {role!r}; known roles: {known}"
            ) from None

    def roles(self) -> dict[str, ModelRef]:
        """A copy of the full role → model mapping."""
        return dict(self._roles)
