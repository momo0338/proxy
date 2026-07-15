"""Proxy validator — tests proxies against echo endpoints concurrently."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx

from src.models import Anonymity, ProxyRecord

if TYPE_CHECKING:
    from src.store import ProxyStore

# Endpoints tried, in order, until one succeeds. Both JSON shapes are
# supported: {"ip": ...} (ipify / ipinfo) and {"origin": ...} (httpbin).
# ipinfo is preferred because its payload also carries the country.
_DEFAULT_ENDPOINTS = [
    "https://ipinfo.io/json",
    "https://api.ipify.org?format=json",
    "http://httpbin.org/ip",
]


class ProxyValidator:
    """Validate proxies concurrently using httpx."""

    def __init__(self, config: dict[str, object], store: ProxyStore) -> None:
        """Initialise validator with config and store."""
        self._config = config
        self._store = store

    @staticmethod
    def _proxy_url(record: ProxyRecord) -> str:
        """Return the proxy URL (already protocol-prefixed) for httpx."""
        return record.address

    def _echo_endpoints(self) -> list[str]:
        """Resolve the ordered list of echo endpoints to test against."""
        endpoints: list[str] = []
        eps = self._config.get("verify_endpoints")
        if isinstance(eps, list):
            endpoints = [str(e) for e in eps if e]
        if not endpoints:
            anon = self._config.get("anon_check_url")
            if anon:
                endpoints.append(str(anon))
        if not endpoints:
            endpoints = list(_DEFAULT_ENDPOINTS)
        # Always append anon_check_url as a final fallback for compatibility.
        anon = self._config.get("anon_check_url")
        if anon and str(anon) not in endpoints:
            endpoints.append(str(anon))
        return endpoints

    async def _resolve_local_ip(self) -> str:
        """Best-effort fetch of our own public IP."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get("https://api.ipify.org")
                resp.raise_for_status()
                return resp.text.strip()
        except (httpx.HTTPError, OSError):
            return ""

    @staticmethod
    def _classify(origin_ip: str, local_ip: str, record_ip: str) -> Anonymity:
        """Classify anonymity from the IP the echo endpoint saw."""
        if origin_ip == local_ip:
            return Anonymity.TRANSPARENT
        if origin_ip == record_ip:
            return Anonymity.ELITE
        return Anonymity.ANONYMOUS

    async def _lookup_country(self, client: httpx.AsyncClient, ip: str) -> str:
        """Best-effort country lookup (only when the echo payload lacked one)."""
        country_url = self._config.get("country_url")
        if not country_url:
            return ""
        try:
            resp = await client.get(str(country_url), params={"ip": ip}, timeout=5.0)
            resp.raise_for_status()
            return str(resp.json().get("country", "")).strip()
        except (httpx.HTTPError, OSError, ValueError):
            return ""

    async def _attempt(
        self,
        record: ProxyRecord,
        client: httpx.AsyncClient,
        local_ip: str,
        endpoint: str,
        timeout_sec: float,
    ) -> ProxyRecord | None:
        """One validation attempt through `endpoint`.

        Returns a ProxyRecord on success, or None if this endpoint could not
        validate the proxy (network error, bad payload, etc.).
        """
        start = time.monotonic()
        try:
            resp = await client.get(endpoint, timeout=timeout_sec)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, OSError, ValueError):
            return None

        origin_ip = str(data.get("ip") or data.get("origin") or "").strip()
        if not origin_ip:
            return None

        anonymity = self._classify(origin_ip, local_ip, record.ip)
        country = str(data.get("country") or "").strip()
        if not country:
            country = await self._lookup_country(client, record.ip)
        elapsed = round(time.monotonic() - start, 3)
        now = datetime.now(UTC).isoformat()
        return ProxyRecord(
            ip=record.ip,
            port=record.port,
            protocol=record.protocol,
            source=record.source,
            country=country,
            anonymity=anonymity,
            response_time=elapsed,
            last_verified=now,
            is_valid=True,
        )

    async def _validate_with_fallback(
        self,
        record: ProxyRecord,
        client: httpx.AsyncClient,
        local_ip: str,
        endpoints: list[str],
        timeout_sec: float,
    ) -> ProxyRecord:
        """Try each echo endpoint in order; return the first successful result."""
        for endpoint in endpoints:
            result = await self._attempt(record, client, local_ip, endpoint, timeout_sec)
            if result is not None:
                return result
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
        endpoints = self._echo_endpoints()
        timeout_val = self._config.get("verify_timeout", 8.0)
        timeout_sec = float(timeout_val) if isinstance(timeout_val, (int, float)) else 8.0
        semaphore = asyncio.Semaphore(max_concurrency)
        valid: list[ProxyRecord] = []

        async def _guarded(record: ProxyRecord) -> None:
            async with semaphore:
                proxy_url = self._proxy_url(record)
                async with httpx.AsyncClient(proxy=proxy_url, timeout=timeout_sec) as client:
                    result = await self._validate_with_fallback(
                        record, client, local_ip, endpoints, timeout_sec
                    )
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

        await asyncio.gather(
            *[_guarded(r) for r in records],
            return_exceptions=True,
        )

        return valid
