"""Tests for src.geo — province normalisation and the ip-api batch resolver."""

from __future__ import annotations

import httpx
import pytest

from src.geo import GeoResolver, GeoResult, normalize_province


def test_normalize_province_short_and_full() -> None:
    assert normalize_province("山东") == "山东"
    assert normalize_province("北京市") == "北京"
    assert normalize_province("广东省") == "广东"
    assert normalize_province("广西壮族自治区") == "广西"
    assert normalize_province("新疆维吾尔自治区") == "新疆"
    assert normalize_province("香港特别行政区") == "香港"


def test_normalize_province_unknown_and_empty() -> None:
    assert normalize_province("") == ""
    assert normalize_province("   ") == ""
    assert normalize_province("California") == ""


def test_geo_resolver_enabled_and_base() -> None:
    resolver = GeoResolver("http://ip-api.com/json")
    assert resolver.enabled is True
    assert resolver._base == "http://ip-api.com"
    assert GeoResolver("").enabled is False


def test_province_node_confidence() -> None:
    """A resolved province should drive node name/group even with a bare IP."""
    from scripts.gen_clash import identify_node  # noqa: PLC0415

    name, group, code = identify_node("1.2.3.4", 8080, "http", "CN", "山东")
    assert "山东" in name
    assert group == "🌾 山东节点"
    assert code == "CN"


@pytest.mark.asyncio
async def test_resolve_many_parses_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver = GeoResolver("http://ip-api.com/json")
    async def fake_resolve_chunk(client, chunk, timeout):  # noqa: ANN001, ANN202, ARG001, ASYNC109
        data = [
            {"status": "success", "countryCode": "CN", "regionName": "浙江省", "city": "杭州"}
            for _ in chunk
        ]
        return {
            ip: GeoResult(
                country=item["countryCode"],
                province=normalize_province(item["regionName"]),
                city=item["city"],
            )
            for ip, item in zip(chunk, data, strict=False)
        }

    monkeypatch.setattr(resolver, "_resolve_chunk", fake_resolve_chunk)
    result = await resolver.resolve_many(["1.1.1.1", "2.2.2.2"])
    assert result["1.1.1.1"] == GeoResult(country="CN", province="浙江", city="杭州")
    assert result["2.2.2.2"].province == "浙江"


@pytest.mark.asyncio
async def test_resolve_chunk_handles_429() -> None:
    resolver = GeoResolver("http://ip-api.com/json")

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(429)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as c:
        out = await resolver._resolve_chunk(c, ["1.1.1.1"], 5.0)
    assert out == {}
