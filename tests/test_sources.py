"""Tests for src.sources — TextSource and build_sources."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.config import parse_protocol
from src.models import ProxyProtocol, SourceFetchError
from src.sources import TextSource, build_sources


class TestParseProtocol:
    """Tests for parse_protocol."""

    def test_http(self) -> None:
        assert parse_protocol("http") == ProxyProtocol.HTTP

    def test_https(self) -> None:
        assert parse_protocol("https") == ProxyProtocol.HTTPS

    def test_socks4(self) -> None:
        assert parse_protocol("socks4") == ProxyProtocol.SOCKS4

    def test_socks5(self) -> None:
        assert parse_protocol("socks5") == ProxyProtocol.SOCKS5

    def test_case_insensitive(self) -> None:
        assert parse_protocol("HTTP") == ProxyProtocol.HTTP
        assert parse_protocol("Socks5") == ProxyProtocol.SOCKS5

    def test_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown protocol"):
            parse_protocol("grpc")


class TestTextSource:
    """Tests for TextSource.fetch with mocked HTTP."""

    def test_fetch_success(self) -> None:
        source = TextSource(
            name="TestSource",
            url="https://example.com/proxies.txt",
            protocol=ProxyProtocol.HTTP,
        )

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.text = "1.2.3.4:8080\n5.6.7.8:3128\n# comment\n\n9.9.9.9:80"
        mock_response.raise_for_status = MagicMock()

        with patch("src.sources.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            records = source.fetch()

        assert len(records) == 3
        assert records[0].ip == "1.2.3.4"
        assert records[0].port == 8080
        assert records[1].ip == "5.6.7.8"
        assert records[2].ip == "9.9.9.9"

    def test_fetch_network_error(self) -> None:
        source = TextSource(
            name="BadSource",
            url="https://example.com/fail.txt",
            protocol=ProxyProtocol.HTTP,
        )

        with patch("src.sources.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.side_effect = httpx.ConnectError("connection refused")
            mock_client_cls.return_value = mock_client

            with pytest.raises(SourceFetchError, match="BadSource"):
                source.fetch()

    def test_fetch_empty(self) -> None:
        source = TextSource(
            name="EmptySource",
            url="https://example.com/empty.txt",
            protocol=ProxyProtocol.HTTP,
        )

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.text = ""
        mock_response.raise_for_status = MagicMock()

        with patch("src.sources.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            records = source.fetch()

        assert records == []


class TestBuildSources:
    """Tests for build_sources."""

    def test_build_from_config(self) -> None:
        config: dict[str, object] = {
            "timeout": 10,
            "sources": [
                {
                    "name": "Test HTTP",
                    "url": "https://example.com/http.txt",
                    "protocol": "http",
                    "format": "ip:port",
                    "enabled": True,
                },
                {
                    "name": "Test SOCKS5",
                    "url": "https://example.com/socks5.txt",
                    "protocol": "socks5",
                    "format": "ip:port",
                    "enabled": True,
                },
            ],
        }
        sources = build_sources(config)
        assert len(sources) == 2
        assert sources[0].name == "Test HTTP"
        assert sources[0].protocol == ProxyProtocol.HTTP
        assert sources[0].timeout == 10.0
        assert sources[1].protocol == ProxyProtocol.SOCKS5

    def test_build_skips_disabled(self) -> None:
        config: dict[str, object] = {
            "sources": [
                {
                    "name": "Disabled",
                    "url": "https://example.com/x.txt",
                    "protocol": "http",
                    "enabled": False,
                },
            ],
        }
        assert build_sources(config) == []

    def test_build_empty_sources(self) -> None:
        assert build_sources({}) == []

    def test_build_invalid_entry(self) -> None:
        config: dict[str, object] = {
            "sources": ["not-a-dict", 42],
        }
        assert build_sources(config) == []
