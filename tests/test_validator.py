from __future__ import annotations

import tempfile
from pathlib import Path

import httpx
import pytest

from src.models import Anonymity, ProxyProtocol, ProxyRecord
from src.store import ProxyStore
from src.validator import ProxyValidator


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
    def __init__(self, responses: dict[str, tuple[dict, BaseException | None]]) -> None:
        self._responses = responses

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
