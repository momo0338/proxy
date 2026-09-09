"""Proxy validator — tests proxies against echo endpoints concurrently."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import TYPE_CHECKING

import httpx

from src.models import Anonymity, ProxyRecord

if TYPE_CHECKING:
    from collections.abc import Callable

    from src.store import ProxyStore

# Endpoints tried, in order, until one succeeds. Both JSON shapes are
# supported: {"ip": ...} (ipify / ipinfo / ipip) and {"origin": ...} (httpbin).
# ipinfo is preferred because its payload also carries the country.
# This list is only a fallback when config has no verify_endpoints;
# keep it in sync with config.DEFAULT_CONFIG["verify_endpoints"].
# All endpoints MUST use https:// to reject proxies without encrypted tunnel (CONNECT) support.
_DEFAULT_ENDPOINTS = [
    "https://api.ipify.org?format=json",
    "https://ipinfo.io/json",
    "https://ip.my-ip.io/json",
]

# 国内稳定 CDN / 高可用 HTTPS 端点: 专用于国内 IP 验证, 保证在境内高可用且验证加密隧道
_DEFAULT_CHINA_ENDPOINTS = [
    "https://connect.rom.miui.com/generate_204",
    "https://connectivitycheck.platform.hicloud.com/generate_204",
    "https://myip.ipip.net/json",
    "https://www.baidu.com",
]


def is_china_ip(ip: str, country: str = "") -> bool:
    """Check whether an IP is located in Mainland China."""
    c = str(country).upper().strip()
    if c in ("CN", "CHINA", "中国"):
        return True

    parts = (
        [int(p) for p in ip.split(".")]
        if ip.count(".") == 3 and all(p.isdigit() for p in ip.split("."))
        else [0, 0, 0, 0]
    )
    first = parts[0]

    # 中国大陆主要 IPv4 网段
    if first in (
        14, 27, 36, 39, 42, 49, 58, 59, 60, 61, 101, 106, 110, 111, 112, 113,
        114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 171, 175,
        180, 182, 183, 211, 218, 219, 220, 221, 222, 223,
    ):
        return True

    # 常见国内云厂商特定 IP
    return ip in (
        "39.106.165.196", "39.106.170.168", "47.95.206.224", "123.57.213.24",
        "111.229.76.29", "101.132.170.8", "120.26.171.55", "47.121.139.13",
        "47.107.107.24", "47.107.82.96", "8.138.217.152", "49.234.4.115",
    )


def _to_float(value: object, default: float) -> float:
    """Coerce a config value to float, falling back to ``default``."""
    return float(value) if isinstance(value, (int, float)) else default


def _httpx_timeout(seconds: float) -> httpx.Timeout:
    """Explicit timeout covering connect/read/write/pool so stalls are bounded.

    A bare ``timeout=seconds`` float only loosely maps to these; spelling them
    out makes the connect (incl. DNS) cap unambiguous. DNS black-holes are still
    additionally guarded by the asyncio.wait_for hard cap in _probe_or_full.
    """
    return httpx.Timeout(seconds, connect=seconds, read=seconds, write=seconds, pool=seconds)


class _Progress:
    """Track validation progress and print a line every 100 records."""

    def __init__(self, total: int) -> None:
        self.total = total
        self.done = 0
        self.valid = 0
        self.valid_list: list[ProxyRecord] = []
        self.cycle_start = time.monotonic()

    def tick(self, result: ProxyRecord) -> None:
        self.done += 1
        if result.is_valid:
            self.valid += 1
            self.valid_list.append(result)
        if self.done % 100 == 0:
            elapsed = time.monotonic() - self.cycle_start
            rate = self.done / elapsed if elapsed > 0 else 0.0
            print(
                f"  [validate] {self.done}/{self.total} checked, {self.valid} valid "
                f"({elapsed:.0f}s, {rate:.1f}/s)",
                flush=True,
            )


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

    def _echo_endpoints(self, record: ProxyRecord | None = None) -> list[str]:
        """Resolve the ordered list of echo endpoints to test against.

        If the record is identified as a China IP, prioritises reliable
        domestic CDN / HTTPS endpoints.
        """
        if record is not None and is_china_ip(record.ip, record.country):
            china_eps = self._config.get("china_verify_endpoints")
            if isinstance(china_eps, list) and china_eps:
                return [str(e) for e in china_eps if e and str(e).startswith("https://")]
            return list(_DEFAULT_CHINA_ENDPOINTS)

        endpoints: list[str] = []
        eps = self._config.get("verify_endpoints")
        if isinstance(eps, list):
            endpoints = [str(e) for e in eps if e and str(e).startswith("https://")]
        if not endpoints:
            anon = self._config.get("anon_check_url")
            if anon and str(anon).startswith("https://"):
                endpoints.append(str(anon))
        if not endpoints:
            endpoints = list(_DEFAULT_ENDPOINTS)
        # Always append anon_check_url as a final fallback for compatibility.
        anon = self._config.get("anon_check_url")
        if anon and str(anon) not in endpoints and str(anon).startswith("https://"):
            endpoints.append(str(anon))
        return [e for e in endpoints if e.startswith("https://")]

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
        except (httpx.HTTPError, OSError, ValueError):
            return None

        origin_ip = ""
        country = ""
        status_code = getattr(resp, "status_code", 200)
        # 1. 国内极速 CDN 204 端点 (如 connect.rom.miui.com)
        if status_code == 204 or endpoint.endswith("generate_204"):
            origin_ip = record.ip
            country = "CN" if is_china_ip(record.ip, record.country) else (record.country or "CN")
        else:
            try:
                data = resp.json()
                if isinstance(data, dict):
                    # 2. 常见回显结构 {"ip": ...} 或 {"origin": ...}
                    origin_ip = str(data.get("ip") or data.get("origin") or "").strip()
                    country = str(data.get("country") or "").strip()
                    # 3. 国内 myip.ipip.net 结构
                    if not origin_ip and isinstance(data.get("data"), dict):
                        inner = data["data"]
                        origin_ip = str(inner.get("ip", "")).strip()
                        loc = inner.get("location", [])
                        if isinstance(loc, list) and loc and ("中国" in loc or loc[0] == "中国"):
                            country = "CN"
            except (ValueError, AttributeError):
                # 4. 国内网页探测 (如 baidu.com)
                content = getattr(resp, "content", b"")
                if status_code == 200 and ("baidu.com" in endpoint or len(content) > 100):
                    origin_ip = record.ip
                    country = "CN"
                else:
                    return None

        if not origin_ip:
            return None

        anonymity = self._classify(origin_ip, local_ip, record.ip)
        if not country:
            country = await self._lookup_country(client, record.ip)
        elapsed = round(time.monotonic() - start, 3)
        now = datetime.now().isoformat()
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
        now = datetime.now().isoformat()
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

    async def _probe_or_full(  # noqa: PLR0913
        self,
        record: ProxyRecord,
        quick_probe: bool,
        client_factory: Callable[..., httpx.AsyncClient],
        probe_endpoint: str,
        probe_timeout: float,
        timeout_sec: float,
        hard_timeout: float,
        local_ip: str,
        endpoints: list[str],
    ) -> ProxyRecord:
        """First-pass short probe, then full verification only for survivors.

        Every network call is wrapped in asyncio.wait_for(hard_timeout) so a
        black-holed DNS or half-open TCP connection cannot hang past the cap and
        stall the whole batch. httpx's own timeout only covers connect/read/write,
        not all stall modes, so the hard cap is the real safety net.
        """
        proxy_url = self._proxy_url(record)
        if not quick_probe:
            client = client_factory(proxy=proxy_url, timeout=_httpx_timeout(timeout_sec))
            async with client:
                return await self._safe_validate(
                    record, client, local_ip, endpoints, timeout_sec, hard_timeout
                )
        # 首轮: 单端点 + 短超时快筛。通了才算"疑似活", 进入完整复验。
        try:
            async with client_factory(
                proxy=proxy_url, timeout=_httpx_timeout(probe_timeout)
            ) as client:
                probe = await asyncio.wait_for(
                    self._attempt(record, client, local_ip, probe_endpoint, probe_timeout),
                    timeout=hard_timeout,
                )
        except (httpx.HTTPError, OSError, ValueError, TimeoutError):
            probe = None
        if probe is None:
            # 快筛即死: 直接返回死标记, 不跑多端点回退。
            return ProxyRecord(
                ip=record.ip,
                port=record.port,
                protocol=record.protocol,
                source=record.source,
                country="",
                anonymity=Anonymity.TRANSPARENT,
                response_time=0.0,
                last_verified=datetime.now().isoformat(),
                is_valid=False,
            )
        return probe

    async def _safe_validate(  # noqa: PLR0913
        self,
        record: ProxyRecord,
        client: httpx.AsyncClient,
        local_ip: str,
        endpoints: list[str],
        timeout_sec: float,
        hard_timeout: float,
    ) -> ProxyRecord:
        """Full validation with a hard per-call timeout cap."""
        try:
            return await asyncio.wait_for(
                self._validate_with_fallback(record, client, local_ip, endpoints, timeout_sec),
                timeout=hard_timeout,
            )
        except (httpx.HTTPError, OSError, ValueError, TimeoutError):
            now = datetime.now().isoformat()
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
        quick_probe: bool = True,
        client_factory: Callable[..., httpx.AsyncClient] = httpx.AsyncClient,
    ) -> list[ProxyRecord]:
        """Validate many proxies concurrently. Updates store and returns valid ones.

        With ``quick_probe`` (default) dead proxies are filtered cheaply first:
        a single short-timeout probe (one endpoint) is tried before the full
        multi-endpoint validation. Only proxies that pass the probe are re-tested
        with the slow, thorough path. This cuts wall-clock drastically because
        most proxies are dead and would otherwise burn the full per-endpoint
        timeout for every endpoint.

        ``client_factory`` is injectable for tests; production uses httpx.AsyncClient.
        """
        if not records:
            return []

        local_ip = await self._resolve_local_ip()
        endpoints = self._echo_endpoints()
        timeout_val = self._config.get("verify_timeout", 8.0)
        timeout_sec = _to_float(timeout_val, 8.0)
        probe_timeout_val = self._config.get("quick_probe_timeout", 3.0)
        probe_timeout = _to_float(probe_timeout_val, 3.0)
        # 硬性总超时: 兜底任何黑洞 DNS/半开连接, 不让单代理拖垮整批。
        hard_val = self._config.get("verify_hard_timeout", 0)
        hard_timeout = _to_float(hard_val, 0.0) if hard_val else timeout_sec * 2
        probe_endpoint = endpoints[0] if endpoints else "https://ipinfo.io/json"
        # 单代理经代理链访问外部 echo 服务很慢, 靠高并发掩盖延迟而非堆超时。
        # 默认 100 兼容 macOS ulimit -n=256; 服务器可配更高(需先放 fd 上限)。
        if max_concurrency <= 0:
            max_concurrency = 100
        semaphore = asyncio.Semaphore(max_concurrency)
        total = len(records)
        progress = _Progress(total=total)

        async def _validate_one(record: ProxyRecord) -> None:
            async with semaphore:
                rec_endpoints = self._echo_endpoints(record)
                rec_probe_endpoint = (
                    rec_endpoints[0]
                    if rec_endpoints
                    else (
                        "https://connect.rom.miui.com/generate_204"
                        if is_china_ip(record.ip, record.country)
                        else probe_endpoint
                    )
                )
                result = await self._probe_or_full(
                    record,
                    quick_probe,
                    client_factory,
                    rec_probe_endpoint,
                    probe_timeout,
                    timeout_sec,
                    hard_timeout,
                    local_ip,
                    rec_endpoints,
                )
                self._store.record_validation(
                    record.key,
                    is_valid=result.is_valid,
                    response_time=result.response_time,
                    anonymity=result.anonymity,
                    country=result.country,
                    last_verified=result.last_verified,
                )
                progress.tick(result)

        print(
            f"  validating {total} proxies @ concurrency={max_concurrency}"
            f"{' (quick-probe on)' if quick_probe else ''} ...",
            flush=True,
        )
        await asyncio.gather(
            *[_validate_one(r) for r in records],
            return_exceptions=True,
        )
        print(
            f"  [validate] {progress.done}/{total} checked, {progress.valid} valid",
            flush=True,
        )

        return progress.valid_list
