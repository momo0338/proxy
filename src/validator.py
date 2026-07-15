"""Proxy validator — tests proxies against check endpoints."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx

from src.models import Anonymity, ProxyRecord

if TYPE_CHECKING:
    from src.store import ProxyStore


class ProxyValidator:
    """Validate proxies concurrently using httpx."""

    def __init__(self, config: dict[str, object], store: ProxyStore) -> None:
        """Initialise validator with config and store."""
        self._config = config
        self._store = store

    @staticmethod
    def _proxy_dict(record: ProxyRecord) -> dict[str, str]:
        """Build httpx proxy mapping for a given record."""
        address = record.address
        return {"http": address, "https": address}

    async def _resolve_local_ip(self) -> str:
        """Best-effort fetch of our own public IP."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get("https://api.ipify.org")
                resp.raise_for_status()
                return resp.text.strip()
        except (httpx.HTTPError, OSError):
            return ""

    async def validate_one(
        self,
        record: ProxyRecord,
        client: httpx.AsyncClient,
        local_ip: str,
    ) -> ProxyRecord:
        """Validate a single proxy by routing a request through it."""
        anon_check_url = str(self._config.get("anon_check_url", "http://httpbin.org/ip"))
        country_url = str(self._config.get("country_url", "http://ip-api.com/json"))
        timeout_val = self._config.get("verify_timeout", 8.0)
        timeout = float(timeout_val) if isinstance(timeout_val, (int, float)) else 8.0

        start = time.monotonic()
        try:
            resp = await client.get(
                anon_check_url,
                proxies=self._proxy_dict(record),
                timeout=timeout,
            )
            resp.raise_for_status()
            elapsed = round(time.monotonic() - start, 3)

            data = resp.json()
            origin_ip = str(data.get("origin", ""))

            # Determine anonymity
            if origin_ip == local_ip:
                anon = Anonymity.TRANSPARENT
            elif origin_ip == record.ip:
                anon = Anonymity.ELITE
            else:
                anon = Anonymity.ANONYMOUS

            # Best-effort country lookup
            country = ""
            try:
                cresp = await client.get(
                    country_url,
                    params={"ip": record.ip},
                    timeout=5.0,
                )
                cresp.raise_for_status()
                cdata = cresp.json()
                country = str(cdata.get("country", ""))
            except (httpx.HTTPError, OSError):
                country = ""

            now = datetime.now(UTC).isoformat()
            return ProxyRecord(
                ip=record.ip,
                port=record.port,
                protocol=record.protocol,
                source=record.source,
                country=country,
                anonymity=anon,
                response_time=elapsed,
                last_verified=now,
                is_valid=True,
            )

        except (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.TimeoutException,
            httpx.ProxyError,
            httpx.HTTPStatusError,
            OSError,
        ):
            now = datetime.now(UTC).isoformat()
            return ProxyRecord(
                ip=record.ip,
                port=record.port,
                protocol=record.protocol,
                source=record.source,
                country="",
                anonymity=Anonymity.TRANSPARENT,
                response_time=0.0,
                last_verified=now,
                is_valid=False,
            )

    async def validate_all(
        self,
        records: list[ProxyRecord],
        max_concurrency: int,
    ) -> list[ProxyRecord]:
        """Validate many proxies concurrently. Updates store and returns valid ones."""
        if not records:
            return []

        local_ip = await self._resolve_local_ip()
        semaphore = asyncio.Semaphore(max_concurrency)
        valid: list[ProxyRecord] = []

        async def _guarded(record: ProxyRecord) -> None:
            async with semaphore:
                result = await self.validate_one(record, client, local_ip)
                self._store.record_validation(
                    record.key,
                    is_valid=result.is_valid,
                    response_time=result.response_time,
                    anonymity=result.anonymity,
                    country=result.country,
                    last_verified=result.last_verified,
                )
                if result.is_valid:
                    valid.append(result)

        async with httpx.AsyncClient() as client:
            await asyncio.gather(
                *[_guarded(r) for r in records],
                return_exceptions=True,
            )

        return valid
