"""FastAPI HTTP service for the proxy pool."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Annotated, Final

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from src.models import Anonymity, ProxyProtocol
from src.scheduler import RefreshService, run_refresh

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from src.store import ProxyStore


class ProxyOut(BaseModel):
    """Outbound proxy JSON representation."""

    model_config: Final[ConfigDict] = ConfigDict(frozen=True)

    ip: str
    port: int
    protocol: str
    source: str
    country: str
    anonymity: str
    response_time: float
    last_verified: str
    is_valid: bool
    address: str


class HealthOut(BaseModel):
    """Health check response."""

    model_config: Final[ConfigDict] = ConfigDict(frozen=True)

    status: str
    total: int
    valid: int


class MetricsOut(BaseModel):
    """Metrics response."""

    model_config: Final[ConfigDict] = ConfigDict(frozen=True)

    total: int
    valid: int
    by_protocol: dict[str, int]


class RefreshOut(BaseModel):
    """Refresh trigger response."""

    model_config: Final[ConfigDict] = ConfigDict(frozen=True)

    status: str


_store: ProxyStore | None = None
_config: dict[str, object] = {}
_refresh_task: asyncio.Task[None] | None = None


def create_app(store: ProxyStore, config: dict[str, object]) -> FastAPI:
    """Build and return the FastAPI application."""
    global _store, _config  # noqa: PLW0603
    _store = store
    _config = config

    refresh_service = RefreshService(store, config)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        """Run initial refresh on the server loop, then start the scheduler."""
        if config.get("refresh_on_startup", True):
            await refresh_service.refresh()
        refresh_service.start()
        try:
            yield
        finally:
            refresh_service.shutdown()

    fastapi_app = FastAPI(title="Proxy Pool Service", version="2.0.0", lifespan=lifespan)

    @fastapi_app.get("/proxies", response_model=list[ProxyOut])
    async def list_proxies(
        protocol: Annotated[str | None, Query(description="Filter by protocol")] = None,
        anon: Annotated[str | None, Query(description="Filter by anonymity")] = None,
        country: Annotated[str | None, Query(description="Filter by country")] = None,
        limit: Annotated[int | None, Query(description="Max results")] = None,
    ) -> list[ProxyOut]:
        """Return valid proxies matching the given filters."""
        assert _store is not None
        proto = ProxyProtocol(protocol) if protocol else None
        anonymity = Anonymity(anon) if anon else None
        expiry_val = _config.get("proxy_expiry_hours", 6)
        expiry = int(expiry_val) if isinstance(expiry_val, (int, float)) else 6
        records = _store.get_valid(
            protocol=proto,
            anonymity=anonymity,
            country=country,
            limit=limit,
            only_fresh=True,
            expiry_hours=expiry,
        )
        return [ProxyOut(**r.to_dict()) for r in records]

    @fastapi_app.get("/proxy/random", response_model=ProxyOut)
    async def random_proxy(
        protocol: Annotated[str | None, Query()] = None,
        anon: Annotated[str | None, Query()] = None,
        country: Annotated[str | None, Query()] = None,
    ) -> ProxyOut:
        """Return a single random valid proxy."""
        assert _store is not None
        proto = ProxyProtocol(protocol) if protocol else None
        anonymity = Anonymity(anon) if anon else None
        record = _store.random_valid(protocol=proto, anonymity=anonymity, country=country)
        if record is None:
            raise HTTPException(status_code=404, detail="No valid proxies available")
        return ProxyOut(**record.to_dict())

    @fastapi_app.get("/health", response_model=HealthOut)
    async def health() -> HealthOut:
        """Service health check."""
        assert _store is not None
        counts = _store.count()
        return HealthOut(status="ok", total=counts["total"], valid=counts["valid"])

    @fastapi_app.get("/metrics", response_model=MetricsOut)
    async def metrics() -> MetricsOut:
        """Detailed proxy counts."""
        assert _store is not None
        counts = _store.count()
        return MetricsOut(
            total=counts["total"],
            valid=counts["valid"],
            by_protocol=counts["by_protocol"],
        )

    @fastapi_app.post("/refresh", response_model=RefreshOut)
    async def refresh() -> RefreshOut:
        """Trigger a background proxy refresh."""
        assert _store is not None
        global _refresh_task  # noqa: PLW0603
        _refresh_task = asyncio.create_task(run_refresh(_store, _config))
        return RefreshOut(status="accepted")

    return fastapi_app
