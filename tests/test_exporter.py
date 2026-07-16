"""Tests for the validated-proxy exporter."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.exporter import export_valid
from src.models import Anonymity, ProxyProtocol, ProxyRecord
from src.store import ProxyStore


@pytest.fixture()
def store() -> ProxyStore:
    with tempfile.TemporaryDirectory() as tmp:
        s = ProxyStore(str(Path(tmp) / "v.db"))
        s.init_schema()
        yield s


def _mark_valid(store: ProxyStore, rec: ProxyRecord, anon: Anonymity, country: str) -> None:
    store.record_validation(
        rec.key,
        is_valid=True,
        response_time=1.0,
        anonymity=anon,
        country=country,
        last_verified=__import__("datetime").datetime.now().isoformat(),
    )


def test_export_classifies_by_protocol_and_anonymity(store: ProxyStore) -> None:
    store.upsert(ProxyRecord("1.1.1.1", 80, ProxyProtocol.HTTP, "s"))
    store.upsert(ProxyRecord("2.2.2.2", 1080, ProxyProtocol.SOCKS5, "s"))
    _mark_valid(store, ProxyRecord("1.1.1.1", 80, ProxyProtocol.HTTP, "s"), Anonymity.ELITE, "US")
    _mark_valid(
        store,
        ProxyRecord("2.2.2.2", 1080, ProxyProtocol.SOCKS5, "s"),
        Anonymity.ANONYMOUS,
        "DE",
    )

    with tempfile.TemporaryDirectory() as tmp:
        summary = export_valid(store, tmp, expiry_hours=6)
        assert summary["total"] == 2  # type: ignore[attr-defined]

        # JSON 结构
        json_text = Path(tmp, "valid_proxies.json").read_text(encoding="utf-8")
        obj = json.loads(json_text)
        assert obj["total"] == 2
        assert obj["by_protocol"]["http"]["total"] == 1  # type: ignore[attr-defined]
        assert obj["by_protocol"]["socks5"]["total"] == 1  # type: ignore[attr-defined]
        assert "http://1.1.1.1:80" in obj["proxies"][0]["address"]  # type: ignore[attr-defined]

        # TXT 分段含分类标题
        txt = Path(tmp, "valid_proxies.txt").read_text(encoding="utf-8")
        assert "HTTP / elite" in txt
        assert "SOCKS5 / anonymous" in txt

        # 单协议扁平文件
        assert Path(tmp, "valid_http.txt").read_text(encoding="utf-8").strip() == "http://1.1.1.1:80"
        assert Path(tmp, "valid_socks5.txt").read_text(encoding="utf-8").strip() == "socks5://2.2.2.2:1080"


def test_export_empty_store_writes_nothing(store: ProxyStore) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        summary = export_valid(store, tmp)
        assert summary["total"] == 0  # type: ignore[attr-defined]


def test_export_includes_stale_valid_by_default(store: ProxyStore) -> None:
    rec = ProxyRecord("3.3.3.3", 3128, ProxyProtocol.HTTP, "s")
    store.upsert(rec)
    # 故意写一个远早于新鲜度窗口的 last_verified
    old = __import__("datetime").datetime(2020, 1, 1, 0, 0, 0).isoformat()
    store.record_validation(
        rec.key, is_valid=True, response_time=2.0, anonymity=Anonymity.ELITE,
        country="US", last_verified=old,
    )
    with tempfile.TemporaryDirectory() as tmp:
        # 默认 fresh_only=False -> 过期但仍有效的代理也导出
        summary = export_valid(store, tmp)
        assert summary["total"] == 1  # type: ignore[attr-defined]
        assert Path(tmp, "valid_http.txt").exists()

        # 显式 fresh_only=True -> 被新鲜度过滤掉, 且残留文件被清理
        summary2 = export_valid(store, tmp, fresh_only=True, expiry_hours=6)
        assert summary2["total"] == 0  # type: ignore[attr-defined]
        assert not Path(tmp, "valid_proxies.json").exists()
        assert not Path(tmp, "valid_http.txt").exists()
        assert not Path(tmp, "valid_proxies.json").exists()
