"""Tests for src.models — ProxyRecord, ProxyProtocol, Anonymity, SourceFetchError."""

from __future__ import annotations

import pytest

from src.models import Anonymity, ProxyProtocol, ProxyRecord, SourceFetchError


class TestProxyProtocol:
    """Tests for ProxyProtocol enum."""

    def test_values(self) -> None:
        assert ProxyProtocol.HTTP == "http"
        assert ProxyProtocol.HTTPS == "https"
        assert ProxyProtocol.SOCKS4 == "socks4"
        assert ProxyProtocol.SOCKS5 == "socks5"

    def test_is_str_enum(self) -> None:
        assert isinstance(ProxyProtocol.HTTP, str)


class TestAnonymity:
    """Tests for Anonymity enum."""

    def test_values(self) -> None:
        assert Anonymity.TRANSPARENT == "transparent"
        assert Anonymity.ANONYMOUS == "anonymous"
        assert Anonymity.ELITE == "elite"


class TestProxyRecord:
    """Tests for ProxyRecord value object."""

    def test_address_property(self) -> None:
        rec = ProxyRecord(
            ip="1.2.3.4",
            port=8080,
            protocol=ProxyProtocol.HTTP,
            source="test",
        )
        assert rec.address == "http://1.2.3.4:8080"

    def test_key_property(self) -> None:
        rec = ProxyRecord(
            ip="1.2.3.4",
            port=8080,
            protocol=ProxyProtocol.HTTP,
            source="test",
        )
        assert rec.key == "1.2.3.4:8080:http"

    def test_key_includes_protocol(self) -> None:
        rec1 = ProxyRecord(ip="1.2.3.4", port=8080, protocol=ProxyProtocol.HTTP, source="")
        rec2 = ProxyRecord(ip="1.2.3.4", port=8080, protocol=ProxyProtocol.SOCKS5, source="")
        assert rec1.key != rec2.key

    def test_to_dict(self) -> None:
        rec = ProxyRecord(
            ip="10.0.0.1",
            port=3128,
            protocol=ProxyProtocol.HTTPS,
            source="test-source",
            country="US",
            anonymity=Anonymity.ELITE,
            response_time=0.5,
            last_verified="2025-01-01T00:00:00+00:00",
            is_valid=True,
        )
        d = rec.to_dict()
        assert d["ip"] == "10.0.0.1"
        assert d["port"] == 3128
        assert d["protocol"] == "https"
        assert d["source"] == "test-source"
        assert d["country"] == "US"
        assert d["anonymity"] == "elite"
        assert d["response_time"] == 0.5
        assert d["is_valid"] is True
        assert d["address"] == "https://10.0.0.1:3128"

    def test_frozen(self) -> None:
        rec = ProxyRecord(ip="1.2.3.4", port=80, protocol=ProxyProtocol.HTTP, source="")
        with pytest.raises(AttributeError):
            rec.ip = "5.6.7.8"  # type: ignore[misc]

    def test_from_line_valid(self) -> None:
        rec = ProxyRecord.from_line("192.168.1.1:8080", ProxyProtocol.HTTP, "test")
        assert rec is not None
        assert rec.ip == "192.168.1.1"
        assert rec.port == 8080
        assert rec.protocol == ProxyProtocol.HTTP
        assert rec.source == "test"

    def test_from_line_blank(self) -> None:
        assert ProxyRecord.from_line("", ProxyProtocol.HTTP, "test") is None
        assert ProxyRecord.from_line("   ", ProxyProtocol.HTTP, "test") is None

    def test_from_line_comment(self) -> None:
        assert ProxyRecord.from_line("# comment", ProxyProtocol.HTTP, "test") is None

    def test_from_line_invalid_format(self) -> None:
        assert ProxyRecord.from_line("not-an-ip", ProxyProtocol.HTTP, "test") is None
        assert ProxyRecord.from_line("1.2.3.4", ProxyProtocol.HTTP, "test") is None

    def test_from_line_bad_octet(self) -> None:
        assert ProxyRecord.from_line("999.1.1.1:80", ProxyProtocol.HTTP, "test") is None

    def test_from_line_bad_port(self) -> None:
        assert ProxyRecord.from_line("1.2.3.4:0", ProxyProtocol.HTTP, "test") is None
        assert ProxyRecord.from_line("1.2.3.4:99999", ProxyProtocol.HTTP, "test") is None

    def test_from_line_valid_port_range(self) -> None:
        rec = ProxyRecord.from_line("1.2.3.4:1", ProxyProtocol.SOCKS5, "src")
        assert rec is not None
        assert rec.port == 1
        rec2 = ProxyRecord.from_line("1.2.3.4:65535", ProxyProtocol.SOCKS5, "src")
        assert rec2 is not None
        assert rec2.port == 65535


class TestSourceFetchError:
    """Tests for SourceFetchError."""

    def test_str(self) -> None:
        err = SourceFetchError(source="MySource", reason="timeout")
        assert str(err) == "Failed to fetch source 'MySource': timeout"

    def test_is_exception(self) -> None:
        err = SourceFetchError(source="X", reason="Y")
        assert isinstance(err, Exception)
