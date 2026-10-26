"""Roster currency check core and CLI exit code.

Verifies spec success criteria (specs/roster-currency-check):
- SC-1: an unserved model is a failing finding; the run exits non-zero.
- SC-2: an all-served roster has no failing finding; the run exits zero.
- SC-3: an unlistable provider leaves its roles unchecked, never passing.
- SC-6: providers are resolved through the registry, so a new adapter needs no check change.
- SC-7: a newer model in the same family is advisory and does not fail the run.
- SC-8: a probe reporting a different serving model is a failing finding naming both.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_framework.currency import __main__ as cli
from agent_framework.currency.check import (
    Finding,
    Severity,
    check_roster,
    family_and_version,
    newest_sibling,
)
from agent_framework.providers.base import Provider
from agent_framework.providers.registry import ProviderRegistry
from agent_framework.roster import Roster

from .fakes import BrokenCatalog, FakeCatalog, FakeProbingCatalog, NoCatalog


def _roster(**roles: tuple[str, str]) -> Roster:
    return Roster.from_dict(
        {"roles": {r: {"provider": p, "model": m} for r, (p, m) in roles.items()}}
    )


def _registry(**providers: Provider) -> ProviderRegistry:
    registry = ProviderRegistry()
    for name, adapter in providers.items():
        registry.register(name, adapter)
    return registry


async def test_sc1_unserved_model_is_a_failing_finding() -> None:
    """SC-1: role, provider and model are named in the failing finding."""
    findings = await check_roster(
        _roster(validator=("google", "gemini-3-pro")),
        _registry(google=FakeCatalog(("gemini-3.8-flash",))),
    )
    assert findings == [
        Finding(Severity.FAILING, "validator", "google", "gemini-3-pro",
                "google does not serve 'gemini-3-pro'")
    ]


async def test_sc2_all_served_roster_has_no_failing_finding() -> None:
    """SC-2: every bound model listed → no failing or unchecked findings."""
    findings = await check_roster(
        _roster(worker=("anthropic", "claude-sonnet-5-5"), validator=("google", "gemini-3.8-flash")),
        _registry(anthropic=FakeCatalog(("claude-sonnet-5-5",)),
                  google=FakeProbingCatalog(("gemini-3.8-flash",))),
    )
    assert findings == []


@pytest.mark.parametrize("adapter", [BrokenCatalog(), NoCatalog()])
async def test_sc3_unlistable_provider_leaves_roles_unchecked(adapter: Provider) -> None:
    """SC-3: a listing error or a catalog-less adapter → unchecked for each of its roles."""
    findings = await check_roster(
        _roster(chief=("anthropic", "claude-fable-5-1"), worker=("anthropic", "claude-sonnet-5-5")),
        _registry(anthropic=adapter),
    )
    assert [(f.role, f.severity) for f in findings] == [
        ("chief", Severity.UNCHECKED), ("worker", Severity.UNCHECKED)
    ]


async def test_sc3_unregistered_provider_is_unchecked() -> None:
    """SC-3: a provider with no adapter at all is unchecked, not an error or a pass."""
    findings = await check_roster(_roster(worker=("local", "qwen3-coder")), _registry())
    assert [f.severity for f in findings] == [Severity.UNCHECKED]


async def test_sc6_new_provider_needs_only_a_registered_adapter() -> None:
    """SC-6: an adapter under a new provider name is checked through the registry."""
    findings = await check_roster(
        _roster(worker=("mlx", "qwen3-coder-next-4bit")),
        _registry(mlx=FakeCatalog(("qwen3-coder-next-4bit",))),
    )
    assert findings == []


async def test_sc7_newer_sibling_is_advisory_only() -> None:
    """SC-7: the candidate is named, and the run still passes."""
    findings = await check_roster(
        _roster(worker=("anthropic", "claude-sonnet-5")),
        _registry(anthropic=FakeCatalog(("claude-sonnet-5", "claude-sonnet-5-5", "claude-opus-5-5"))),
    )
    assert [(f.severity, f.message) for f in findings] == [
        (Severity.ADVISORY, "newer model in the same family: 'claude-sonnet-5-5'")
    ]


def test_sc7_family_parsing_ignores_snapshots_and_other_tiers() -> None:
    """SC-7: families group by shape; date snapshots and other tiers are never candidates."""
    assert family_and_version("gemini-3.8-flash") == ("gemini-*-flash", (3, 8))
    assert family_and_version("claude-sonnet-5-5") == ("claude-sonnet-*", (5, 5))
    assert family_and_version("claude-opus-4-1-20250805") is None
    served = ("gemini-3.8-flash", "gemini-3.9-flash-lite", "gemini-4-argon")
    assert newest_sibling("gemini-3.6-flash", served) == "gemini-3.8-flash"
    assert newest_sibling("gemini-3.8-flash", served) is None


async def test_sc8_rerouted_model_is_a_failing_finding() -> None:
    """SC-8: bound and serving model are both named."""
    findings = await check_roster(
        _roster(validator=("google", "gemini-3.5-flash")),
        _registry(google=FakeProbingCatalog(
            ("gemini-3.5-flash",), serving={"gemini-3.5-flash": "gemini-3.6-flash"}
        )),
    )
    assert [(f.severity, f.message) for f in findings] == [
        (Severity.FAILING, "'gemini-3.5-flash' is served by 'gemini-3.6-flash'")
    ]


@pytest.mark.parametrize(
    ("severity", "exit_code"),
    [(Severity.FAILING, 1), (Severity.UNCHECKED, 1), (Severity.ADVISORY, 0)],
)
def test_sc1_sc2_cli_exit_code_follows_findings(
    severity: Severity, exit_code: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SC-1 / SC-2: non-zero only for failing or unchecked findings."""
    roster = tmp_path / "agent-framework.toml"
    roster.write_text('[roles]\nworker = { provider = "anthropic", model = "m-1" }\n')

    async def fake_check(r: Roster, reg: ProviderRegistry) -> list[Finding]:
        return [Finding(severity, "worker", "anthropic", "m-1", "x")]

    monkeypatch.setattr(cli, "check_roster", fake_check)
    assert cli.main(["--roster", str(roster)]) == exit_code
