"""Tests for src.sources — TextSource and build_sources."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.config import parse_protocol
from src.models import ProxyProtocol, SourceFetchError
from src.sources import TextSource, build_sources, split_line


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


class TestSplitLine:
    """Tests for split_line format normalisation."""

    def test_plain_ip_port(self) -> None:
        assert split_line("1.2.3.4:8080", ProxyProtocol.HTTP) == (
            "1.2.3.4:8080",
            ProxyProtocol.HTTP,
        )

    def test_scheme_prefix(self) -> None:
        assert split_line("socks5://1.2.3.4:1080", ProxyProtocol.HTTP) == (
            "1.2.3.4:1080",
            ProxyProtocol.SOCKS5,
        )

    def test_scheme_suffix(self) -> None:
        assert split_line("1.2.3.4:80:HTTPS", ProxyProtocol.HTTP) == (
            "1.2.3.4:80",
            ProxyProtocol.HTTPS,
        )

    def test_blank_and_comment(self) -> None:
        assert split_line("", ProxyProtocol.HTTP) is None
        assert split_line("# comment", ProxyProtocol.HTTP) is None

    def test_garbage_line(self) -> None:
        assert split_line("error code: 1015", ProxyProtocol.HTTP) is None


class TestTextSourceCap:
    """Tests for per-source max_records truncation."""

    def test_max_records(self) -> None:
        source = TextSource(
            name="Cap",
            url="https://example.com/p.txt",
            protocol=ProxyProtocol.HTTP,
            max_records=2,
        )
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.text = "1.1.1.1:80\n2.2.2.2:81\n3.3.3.3:82"
        mock_response.raise_for_status = MagicMock()
        with patch("src.sources.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client
            records = source.fetch()
        assert len(records) == 2
        assert records[0].ip == "1.1.1.1"

    def test_prefix_and_suffix_parsed(self) -> None:
        source = TextSource(
            name="Mixed",
            url="https://example.com/p.txt",
            protocol=ProxyProtocol.HTTP,
        )
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.text = "socks5://9.9.9.9:1080\n8.8.8.8:80:HTTPS"
        mock_response.raise_for_status = MagicMock()
        with patch("src.sources.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client
            records = source.fetch()
        by_ip = {r.ip: r for r in records}
        assert by_ip["9.9.9.9"].protocol == ProxyProtocol.SOCKS5
        assert by_ip["8.8.8.8"].protocol == ProxyProtocol.HTTPS


class TestBuildSourcesCaps:
    """Tests for build_sources reading max / collect_per_source_default."""

    def test_source_max(self) -> None:
        config: dict[str, object] = {
            "sources": [
                {"name": "A", "url": "https://e.com/a.txt", "protocol": "http", "max": 123},
            ],
        }
        sources = build_sources(config)
        assert sources[0].max_records == 123

    def test_default_max(self) -> None:
        config: dict[str, object] = {
            "collect_per_source_default": 777,
            "sources": [
                {"name": "A", "url": "https://e.com/a.txt", "protocol": "http"},
            ],
        }
        sources = build_sources(config)
        assert sources[0].max_records == 777
