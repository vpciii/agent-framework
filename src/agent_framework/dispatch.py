"""Role-based dispatch: resolve a role to its model and invoke it.

`dispatch` ties the roster and the provider registry together — the single
call the chief/worker/validator roles go through to reach a model. It fails
loudly (no silent fallback): an unbound role or a provider with no adapter
raises before any invocation.
"""

from __future__ import annotations

from .providers.base import Request, Response
from .providers.registry import ProviderRegistry, default_registry
from .roster import Roster


async def dispatch(
    roster: Roster,
    role: str,
    request: Request,
    *,
    registry: ProviderRegistry | None = None,
) -> Response:
    """Resolve `role` via the roster and invoke its bound provider.

    Raises `UnknownRoleError` if the role is unbound, or `UnknownProviderError`
    if its provider has no registered adapter — in either case, nothing is
    invoked.
    """
    reg = registry if registry is not None else default_registry()
    ref = roster.resolve(role)
    provider = reg.get(ref.provider)
    return await provider.invoke(request, model=ref.model)
