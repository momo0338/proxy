from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from src.diagnostics import _check_url, diagnose
from src.store import ProxyStore
from src.validator import ProxyValidator

if TYPE_CHECKING:
    from typing import Self

    import pytest


class _FakeResponse:
    status_code: int = 200

    def raise_for_status(self) -> None:
        return None


class _FakeAsyncClient:
    def __init__(
        self,
        response: _FakeResponse | None = None,
        exc: BaseException | None = None,
    ) -> None:
        self._response = response if response is not None else _FakeResponse()
        self._exc = exc

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> bool:
        return False

    async def get(self, _url: str, **_kwargs: object) -> _FakeResponse:
        if self._exc is not None:
            raise self._exc
        return self._response


def test_check_url_ok(monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[name-defined]
    monkeypatch.setattr(httpx, "AsyncClient", lambda *_, **__: _FakeAsyncClient())
    ok, detail = asyncio.run(_check_url("https://x", 5.0))
    assert ok is True
    assert "HTTP 200" in detail


def _down_client() -> object:
    return lambda *_, **__: _FakeAsyncClient(exc=httpx.ConnectError("down"))


def test_check_url_fail(monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[name-defined]
    monkeypatch.setattr(httpx, "AsyncClient", _down_client())
    ok, detail = asyncio.run(_check_url("https://x", 5.0))
    assert ok is False
    assert "ConnectError" in detail


def test_diagnose_empty(
    monkeypatch: pytest.MonkeyPatch,  # type: ignore[name-defined]
    capsys: pytest.CaptureFixture[str],  # type: ignore[name-defined]
) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _down_client())
    with tempfile.TemporaryDirectory() as tmp:
        store = ProxyStore(str(Path(tmp) / "d.db"))
        store.init_schema()
        cfg = {"verify_endpoints": ["https://ipinfo.io/json"]}
        validator = ProxyValidator(cfg, store)
        asyncio.run(diagnose(store, validator, cfg, sample=3))
    out = capsys.readouterr().out
    assert "Endpoint reachability" in out
    assert "no proxies to probe" in out
