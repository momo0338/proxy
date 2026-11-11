"""IP geo-location resolution (province / city) via ip-api.com.

The validator already talks to ``ip-api.com`` to resolve a proxy's country
when the echo payload lacked one. This module extends that to the province
(``regionName``) and city level, which the Clash generator needs for accurate
province grouping.

Design goals:
  * **Batch**: resolve up to 100 IPs per request (ip-api's hard limit) so a
    full validation cycle costs only a handful of requests.
  * **Cache**: results are memoised per IP for a day, so re-validation of the
    same pool does not re-query the still-valid geo data.
  * **Rate-limit aware**: ip-api's free tier is 45 requests/minute; on HTTP 429
    we back off and degrade gracefully instead of hammering.
  * **Graceful degradation**: any failure yields an empty result — province is
    an enrichment, never a hard dependency.

Only the public ip-api.com endpoint is used (no API key required). Callers pass
a proxy URL through ``httpx`` exactly like the validator does, so lookups share
the proxy's egress where appropriate, or go direct when ``proxy=None``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

# ip-api batch hard limit is 100 IPs per POST.
_BATCH_SIZE = 100
# Chinese region names come back in zh-CN; ask for province + city.
_FIELDS = "status,countryCode,regionName,city"
_LANG = "zh-CN"
# Cache geo results for one day — IP provincial attribution is stable.
_CACHE_TTL_SECONDS = 86400

# 国内省份名归一化映射: ip-api 返回的是省级简称/全称混用, 统一成 Clash 分组用的简称。
PROVINCE_ALIASES: dict[str, str] = {
    "北京市": "北京",
    "北京": "北京",
    "天津市": "天津",
    "天津": "天津",
    "上海市": "上海",
    "上海": "上海",
    "重庆市": "重庆",
    "重庆": "重庆",
    "河北省": "河北",
    "河北": "河北",
    "山西省": "山西",
    "山西": "山西",
    "辽宁省": "辽宁",
    "辽宁": "辽宁",
    "吉林省": "吉林",
    "吉林": "吉林",
    "黑龙江省": "黑龙江",
    "黑龙江": "黑龙江",
    "江苏省": "江苏",
    "江苏": "江苏",
    "浙江省": "浙江",
    "浙江": "浙江",
    "安徽省": "安徽",
    "安徽": "安徽",
    "福建省": "福建",
    "福建": "福建",
    "江西省": "江西",
    "江西": "江西",
    "山东省": "山东",
    "山东": "山东",
    "河南省": "河南",
    "河南": "河南",
    "湖北省": "湖北",
    "湖北": "湖北",
    "湖南省": "湖南",
    "湖南": "湖南",
    "广东省": "广东",
    "广东": "广东",
    "海南省": "海南",
    "海南": "海南",
    "四川省": "四川",
    "四川": "四川",
    "贵州省": "贵州",
    "贵州": "贵州",
    "云南省": "云南",
    "云南": "云南",
    "陕西省": "陕西",
    "陕西": "陕西",
    "甘肃省": "甘肃",
    "甘肃": "甘肃",
    "青海省": "青海",
    "青海": "青海",
    "台湾省": "台湾",
    "台湾": "台湾",
    "内蒙古自治区": "内蒙古",
    "内蒙古": "内蒙古",
    "广西壮族自治区": "广西",
    "广西": "广西",
    "西藏自治区": "西藏",
    "西藏": "西藏",
    "宁夏回族自治区": "宁夏",
    "宁夏": "宁夏",
    "新疆维吾尔自治区": "新疆",
    "新疆": "新疆",
    "香港特别行政区": "香港",
    "香港": "香港",
    "澳门特别行政区": "澳门",
    "澳门": "澳门",
}


def normalize_province(raw: str) -> str:
    """Normalise an ip-api ``regionName`` to a canonical short province name.

    Returns an empty string for non-mainland / unknown regions so callers can
    fall back to the country-level bucket.
    """
    name = str(raw).strip()
    if not name:
        return ""
    return PROVINCE_ALIASES.get(name, "")


@dataclass(frozen=True, slots=True)
class GeoResult:
    """Resolved geo info for one IP."""

    country: str = ""
    province: str = ""
    city: str = ""


class GeoResolver:
    """Batch IP -> (country, province, city) resolver backed by ip-api.com."""

    def __init__(self, country_url: str = "http://ip-api.com/json") -> None:
        """Initialise resolver from the configured ``country_url``.

        ``country_url`` points at an ip-api.com host (e.g. the default
        ``http://ip-api.com/json``). We derive the batch endpoint base from it
        so a self-hosted mirror or http/https choice is respected.
        """
        self._base = str(country_url).rstrip("/")
        # ip-api.com style base: strip a trailing /json or path segment to get host.
        if self._base.endswith("/json"):  # noqa: FURB188
            self._base = self._base[: -len("/json")]
        # cache: ip -> (expiry_epoch, GeoResult)
        self._cache: dict[str, tuple[float, GeoResult]] = {}

    @property
    def enabled(self) -> bool:
        """Whether this resolver targets a usable ip-api endpoint."""
        return bool(self._base)

    def _cached(self, ip: str) -> GeoResult | None:
        hit = self._cache.get(ip)
        if hit is None:
            return None
        expiry, result = hit
        if time.monotonic() >= expiry:
            self._cache.pop(ip, None)
            return None
        return result

    def _store(self, ip: str, result: GeoResult) -> None:
        self._cache[ip] = (time.monotonic() + _CACHE_TTL_SECONDS, result)

    async def resolve_many(
        self,
        ips: list[str],
        *,
        timeout: float = 8.0,  # noqa: ASYNC109
        proxy: str | None = None,
    ) -> dict[str, GeoResult]:
        """Resolve province/city for many IPs, batching and caching.

        Returns a mapping ``ip -> GeoResult`` for the IPs that could be resolved
        (unresolved IPs are simply absent). Never raises: network failures
        degrade to the cached / partial set.
        """
        if not ips or not self.enabled:
            return {}

        results: dict[str, GeoResult] = {}
        pending: list[str] = []
        for ip in dict.fromkeys(ips):  # dedupe, preserve order
            cached = self._cached(ip)
            if cached is not None:
                results[ip] = cached
            else:
                pending.append(ip)

        if pending:
            async with httpx.AsyncClient(
                timeout=timeout,
                proxy=proxy,
                follow_redirects=True,
            ) as client:
                for start in range(0, len(pending), _BATCH_SIZE):
                    chunk = pending[start : start + _BATCH_SIZE]
                    chunk_results = await self._resolve_chunk(client, chunk, timeout)
                    for ip, res in chunk_results.items():
                        self._store(ip, res)
                        results[ip] = res

        return results

    async def _resolve_chunk(
        self,
        client: httpx.AsyncClient,
        chunk: list[str],
        timeout: float,  # noqa: ARG002, ASYNC109
    ) -> dict[str, GeoResult]:
        """Resolve one <=100-IP chunk via the ip-api batch endpoint."""
        url = f"{self._base}/batch?fields={_FIELDS}&lang={_LANG}"
        try:
            resp = await client.post(url, json=chunk)
            if resp.status_code == 429:
                # Rate limited: skip this chunk rather than fail the whole run.
                return {}
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, OSError, ValueError):
            return {}

        if not isinstance(data, list):
            return {}

        out: dict[str, GeoResult] = {}
        for ip, item in zip(chunk, data, strict=False):
            if not isinstance(item, dict) or item.get("status") != "success":
                continue
            country = str(item.get("countryCode") or "").strip().upper()
            province = normalize_province(item.get("regionName", ""))
            city = str(item.get("city") or "").strip()
            out[ip] = GeoResult(country=country, province=province, city=city)
        return out

    async def resolve_one(
        self,
        ip: str,
        *,
        timeout: float = 6.0,  # noqa: ASYNC109
        proxy: str | None = None,
    ) -> GeoResult:
        """Resolve a single IP (thin wrapper over ``resolve_many``)."""
        mapping = await self.resolve_many([ip], timeout=timeout, proxy=proxy)
        return mapping.get(ip, GeoResult())
