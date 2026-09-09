from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Self

import httpx
import pytest

from src.models import Anonymity, ProxyProtocol, ProxyRecord
from src.store import ProxyStore
from src.validator import ProxyValidator, is_china_ip

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture()
def store() -> ProxyStore:
    with tempfile.TemporaryDirectory() as tmp:
        s = ProxyStore(str(Path(tmp) / "v.db"))
        s.init_schema()
        yield s


class _FakeResponse:
    def __init__(self, data: dict, exc: BaseException | None = None) -> None:
        self._data = data
        self._exc = exc

    def raise_for_status(self) -> None:
        if self._exc is not None:
            raise self._exc

    def json(self) -> dict:
        if self._exc is not None:
            raise self._exc
        return self._data


class _FakeClient:
    def __init__(
        self, responses: dict[str, tuple[dict, BaseException | None]], **_cfg: object
    ) -> None:
        self._responses = responses

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    async def get(self, url: str, **_kwargs: object) -> _FakeResponse:
        data, exc = self._responses.get(url, ({}, None))
        return _FakeResponse(data, exc)


def test_classify() -> None:
    assert ProxyValidator._classify("1.1.1.1", "1.1.1.1", "2.2.2.2") == Anonymity.TRANSPARENT
    assert ProxyValidator._classify("2.2.2.2", "1.1.1.1", "2.2.2.2") == Anonymity.ELITE
    assert ProxyValidator._classify("3.3.3.3", "1.1.1.1", "2.2.2.2") == Anonymity.ANONYMOUS


@pytest.mark.asyncio
async def test_fallback_to_working_endpoint(store: ProxyStore) -> None:
    cfg = {
        "verify_endpoints": ["https://ipinfo.io/json", "https://api.ipify.org?format=json"],
        "country_url": "",
    }
    v = ProxyValidator(cfg, store)
    rec = ProxyRecord("1.2.3.4", 8080, ProxyProtocol.HTTP, "t")
    client = _FakeClient({
        "https://ipinfo.io/json": ({}, httpx.ConnectError("down")),
        "https://api.ipify.org?format=json": ({"ip": "9.9.9.9"}, None),
    })
    result = await v._validate_with_fallback(rec, client, "5.5.5.5", v._echo_endpoints(), 8.0)
    assert result.is_valid is True
    assert result.anonymity == Anonymity.ANONYMOUS


@pytest.mark.asyncio
async def test_all_endpoints_fail(store: ProxyStore) -> None:
    cfg = {"verify_endpoints": ["https://ipinfo.io/json"], "country_url": ""}
    v = ProxyValidator(cfg, store)
    rec = ProxyRecord("1.2.3.4", 8080, ProxyProtocol.HTTP, "t")
    client = _FakeClient({"https://ipinfo.io/json": ({}, httpx.ConnectError("down"))})
    result = await v._validate_with_fallback(rec, client, "", v._echo_endpoints(), 8.0)
    assert result.is_valid is False


@pytest.mark.asyncio
async def test_country_from_echo(store: ProxyStore) -> None:
    cfg = {"verify_endpoints": ["https://ipinfo.io/json"], "country_url": ""}
    v = ProxyValidator(cfg, store)
    rec = ProxyRecord("1.2.3.4", 8080, ProxyProtocol.HTTP, "t")
    client = _FakeClient({"https://ipinfo.io/json": ({"ip": "9.9.9.9", "country": "DE"}, None)})
    result = await v._validate_with_fallback(rec, client, "5.5.5.5", v._echo_endpoints(), 8.0)
    assert result.is_valid is True
    assert result.country == "DE"


def _fake_factory(
    responses: dict[str, tuple[dict, BaseException | None]],
) -> "Callable[..., _FakeClient]":  # noqa: UP037
    def _make(**_cfg: object) -> _FakeClient:
        return _FakeClient(responses)

    return _make


@pytest.mark.asyncio
async def test_quick_probe_dead_marked(store: ProxyStore, monkeypatch: pytest.MonkeyPatch) -> None:
    # 快筛端点即失败 -> 直接判死, 不再跑完整多端点验证。
    cfg = {
        "verify_endpoints": ["https://ipinfo.io/json"],
        "country_url": "",
        "quick_probe_timeout": 3.0,
    }
    async def _fake_local_ip(_: object) -> str:
        return ""

    monkeypatch.setattr(ProxyValidator, "_resolve_local_ip", _fake_local_ip)
    v = ProxyValidator(cfg, store)
    rec = ProxyRecord("1.2.3.4", 8080, ProxyProtocol.HTTP, "t")
    store.upsert(rec)
    factory = _fake_factory({"https://ipinfo.io/json": ({}, httpx.ConnectError("down"))})
    await v.validate_all([rec], 10, quick_probe=True, client_factory=factory)

    with store._connect() as conn:
        row = conn.execute(
            "SELECT is_valid, last_verified FROM proxies WHERE key = ?", (rec.key,)
        ).fetchone()
    assert row["is_valid"] == 0
    assert row["last_verified"] != ""  # 已标记, 普通 validate 不再重测


@pytest.mark.asyncio
async def test_quick_probe_alive_full_verify(
    store: ProxyStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 快筛通过 -> 走完整验证, 结果入库为有效。
    cfg = {
        "verify_endpoints": ["https://ipinfo.io/json"],
        "country_url": "",
        "quick_probe_timeout": 3.0,
    }
    async def _fake_local_ip(_: object) -> str:
        return ""

    monkeypatch.setattr(ProxyValidator, "_resolve_local_ip", _fake_local_ip)
    v = ProxyValidator(cfg, store)
    rec = ProxyRecord("1.2.3.4", 8080, ProxyProtocol.HTTP, "t")
    store.upsert(rec)
    resp = {"https://ipinfo.io/json": ({"ip": "9.9.9.9", "country": "DE"}, None)}
    factory = _fake_factory(resp)
    valid = await v.validate_all([rec], 10, quick_probe=True, client_factory=factory)

    assert len(valid) == 1
    with store._connect() as conn:
        row = conn.execute(
            "SELECT is_valid, country FROM proxies WHERE key = ?", (rec.key,)
        ).fetchone()
    assert row["is_valid"] == 1
    assert row["country"] == "DE"


def test_is_china_ip() -> None:
    # 国内典型电信/联通/移动/阿里云 IP
    assert is_china_ip("58.210.1.1") is True
    assert is_china_ip("120.193.1.1") is True
    assert is_china_ip("114.249.1.1") is True
    assert is_china_ip("39.106.165.196") is True
    assert is_china_ip("8.8.8.8", country="CN") is True

    # 海外 IP
    assert is_china_ip("8.8.8.8", country="US") is False
    assert is_china_ip("185.214.101.27", country="GB") is False


def test_china_endpoints_routing(store: ProxyStore) -> None:
    cfg = {
        "verify_endpoints": ["https://api.ipify.org?format=json"],
        "china_verify_endpoints": ["https://connect.rom.miui.com/generate_204"],
    }
    v = ProxyValidator(cfg, store)
    china_rec = ProxyRecord("58.210.1.1", 1080, ProxyProtocol.SOCKS5, "t")
    overseas_rec = ProxyRecord("8.8.8.8", 1080, ProxyProtocol.SOCKS5, "t", country="US")

    assert v._echo_endpoints(china_rec) == ["https://connect.rom.miui.com/generate_204"]
    assert v._echo_endpoints(overseas_rec) == ["https://api.ipify.org?format=json"]


@pytest.mark.asyncio
async def test_china_cdn_204_verification(store: ProxyStore) -> None:
    cfg = {
        "china_verify_endpoints": ["https://connect.rom.miui.com/generate_204"],
        "country_url": "",
    }
    v = ProxyValidator(cfg, store)
    rec = ProxyRecord("58.210.1.1", 1080, ProxyProtocol.HTTP, "t")

    class _Fake204Response:
        status_code = 204
        def raise_for_status(self) -> None:
            pass
        def json(self) -> dict:
            raise ValueError("No JSON in 204")

    class _Fake204Client:
        async def __aenter__(self) -> Self:
            return self
        async def __aexit__(self, *_exc: object) -> bool:
            return False
        async def get(self, _url: str, **_kwargs: object) -> _Fake204Response:
            return _Fake204Response()

    result = await v._validate_with_fallback(
        rec, _Fake204Client(), "1.1.1.1", v._echo_endpoints(rec), 5.0
    )
    assert result.is_valid is True
    assert result.country == "CN"
