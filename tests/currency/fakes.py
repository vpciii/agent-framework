"""Fake adapters for the roster currency check: no network, no credentials."""

from __future__ import annotations

from agent_framework.providers.base import Request, Response


class FakeCatalog:
    """Serves a fixed list of model IDs; optionally reports a serving model."""

    def __init__(self, served: tuple[str, ...], serving: dict[str, str] | None = None) -> None:
        self.served = served
        self.serving = serving

    async def invoke(self, request: Request, *, model: str) -> Response:
        return Response(text="")

    async def list_models(self) -> tuple[str, ...]:
        return self.served


class FakeProbingCatalog(FakeCatalog):
    async def probe_model(self, model: str) -> str | None:
        return (self.serving or {}).get(model, model)


class BrokenCatalog:
    """A provider whose listing fails, as with missing credentials."""

    async def invoke(self, request: Request, *, model: str) -> Response:
        return Response(text="")

    async def list_models(self) -> tuple[str, ...]:
        raise RuntimeError("Could not resolve authentication method")


class NoCatalog:
    """An adapter that predates `ModelCatalog`."""

    async def invoke(self, request: Request, *, model: str) -> Response:
        return Response(text="")
