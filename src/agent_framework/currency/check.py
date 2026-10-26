"""The roster currency check's core: roster + provider catalogs → findings.

Pure over its inputs (the roster and a provider registry), so every success
criterion is a unit test over fake adapters. A model the provider no longer
serves, or one it silently routes elsewhere, is *failing*; a provider that
cannot be asked is *unchecked* — never passing (R-4); a newer model in the
same family is *advisory* (R-9).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from ..errors import UnknownProviderError
from ..providers.base import ModelCatalog, ModelProbe
from ..providers.registry import ProviderRegistry
from ..roster import Roster


class Severity(StrEnum):
    FAILING = "failing"
    UNCHECKED = "unchecked"
    ADVISORY = "advisory"


@dataclass(frozen=True)
class Finding:
    severity: Severity
    role: str
    provider: str
    model: str
    message: str


_VERSION_TOKEN = re.compile(r"^\d+(?:\.\d+)*$")
_SNAPSHOT_TOKEN = re.compile(r"^\d{6,}$")  # date-stamped snapshots, e.g. 20250805


def family_and_version(model_id: str) -> tuple[str, tuple[int, ...]] | None:
    """Split an ID into its family and version: `claude-sonnet-5-5` →
    (`claude-sonnet-*`, (5, 5)); `gemini-3.8-flash` → (`gemini-*-flash`, (3, 8)).
    None for IDs without a version or with a date snapshot (never a candidate)."""
    shape: list[str] = []
    version: list[int] = []
    for token in model_id.split("-"):
        if _SNAPSHOT_TOKEN.match(token):
            return None
        if _VERSION_TOKEN.match(token):
            version.extend(int(n) for n in token.split("."))
            if not shape or shape[-1] != "*":
                shape.append("*")
        else:
            shape.append(token)
    return ("-".join(shape), tuple(version)) if version else None


def newest_sibling(model: str, served: tuple[str, ...]) -> str | None:
    """The highest-versioned served model in `model`'s family, if newer than it."""
    bound = family_and_version(model)
    if bound is None:
        return None
    best: tuple[tuple[int, ...], str] | None = None
    for candidate in served:
        parsed = family_and_version(candidate)
        if parsed and parsed[0] == bound[0] and parsed[1] > bound[1]:
            if best is None or parsed[1] > best[0]:
                best = (parsed[1], candidate)
    return best[1] if best else None


async def check_roster(roster: Roster, registry: ProviderRegistry) -> list[Finding]:
    """Check every role's bound model against its provider's catalog."""
    findings: list[Finding] = []
    catalogs: dict[str, tuple[str, ...] | str] = {}  # served IDs, or why unchecked
    for role, ref in sorted(roster.roles().items()):
        if ref.provider not in catalogs:
            catalogs[ref.provider] = await _catalog(ref.provider, registry)
        catalog = catalogs[ref.provider]
        for severity, message in await _check_binding(ref.provider, ref.model, catalog, registry):
            findings.append(Finding(severity, role, ref.provider, ref.model, message))
    return findings


async def _check_binding(
    provider: str, model: str, catalog: tuple[str, ...] | str, registry: ProviderRegistry
) -> list[tuple[Severity, str]]:
    if isinstance(catalog, str):
        return [(Severity.UNCHECKED, catalog)]
    if model not in catalog:
        return [(Severity.FAILING, f"{provider} does not serve {model!r}")]
    results: list[tuple[Severity, str]] = []
    adapter = registry.get(provider)
    if isinstance(adapter, ModelProbe):
        try:
            serving = await adapter.probe_model(model)
        except Exception as e:  # a probe is best-effort (R-10, a SHOULD)
            results.append((Severity.ADVISORY, f"routing probe failed: {e}"))
        else:
            if serving and not serving.startswith(model):
                results.append((Severity.FAILING, f"{model!r} is served by {serving!r}"))
    newer = newest_sibling(model, catalog)
    if newer:
        results.append((Severity.ADVISORY, f"newer model in the same family: {newer!r}"))
    return results


async def _catalog(provider: str, registry: ProviderRegistry) -> tuple[str, ...] | str:
    try:
        adapter = registry.get(provider)
    except UnknownProviderError as e:
        return str(e)
    if not isinstance(adapter, ModelCatalog):
        return f"the {provider} adapter cannot list models"
    try:
        return await adapter.list_models()
    except Exception as e:  # missing credentials, outage: unchecked, never passing
        return f"could not list {provider} models: {type(e).__name__}: {e}"
