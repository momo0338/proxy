"""Tests for src.config — configuration loading and defaults."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from src.config import (
    DEFAULT_CONFIG,
    DEFAULT_PROXY_SOURCES,
    load_config,
    load_proxy_sources,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestLoadConfig:
    """Tests for load_config."""

    def test_default_config(self) -> None:
        config = load_config()
        assert config["db_path"] == "data/proxies.db"
        assert config["refresh_interval_minutes"] == 30
        assert config["proxy_expiry_hours"] == 6
        assert config["max_concurrency"] == 100
        assert config["quick_probe_timeout"] == 3.0
        assert config["verify_hard_timeout"] == 0
        assert config["verify_endpoints"] == [
            "https://ipinfo.io/json",
            "https://api.ipify.org?format=json",
            "http://httpbin.org/ip",
            "https://ip.my-ip.io/json",
        ]

    def test_load_from_file(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"db_path": "/custom/path.db", "refresh_interval_minutes": 10})
        )
        config = load_config(str(config_file))
        assert config["db_path"] == "/custom/path.db"
        assert config["refresh_interval_minutes"] == 10
        # Default values preserved
        assert config["max_concurrency"] == 100

    def test_nonexistent_file(self) -> None:
        config = load_config("/nonexistent/config.json")
        assert config == DEFAULT_CONFIG

    def test_invalid_json(self, tmp_path: Path) -> None:
        config_file = tmp_path / "bad.json"
        config_file.write_text("not json {{{")
        config = load_config(str(config_file))
        assert config == DEFAULT_CONFIG


class TestLoadProxySources:
    """Tests for load_proxy_sources."""

    def test_default_sources(self) -> None:
        sources = load_proxy_sources()
        assert len(sources) == 8
        names = [s["name"] for s in sources]
        assert "TheSpeedX HTTP" in names
        assert "Hookzof SOCKS5" in names

    def test_load_from_file(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        custom_sources = [
            {
                "name": "Custom",
                "url": "https://example.com/p.txt",
                "protocol": "http",
                "enabled": True,
            }
        ]
        config_file.write_text(json.dumps({"sources": custom_sources}))
        sources = load_proxy_sources(str(config_file))
        assert len(sources) == 1
        assert sources[0]["name"] == "Custom"

    def test_nonexistent_file(self) -> None:
        sources = load_proxy_sources("/nonexistent.json")
        assert sources == DEFAULT_PROXY_SOURCES


class TestDefaultProxySources:
    """Verify all 8 original sources are preserved."""

    def test_source_count(self) -> None:
        assert len(DEFAULT_PROXY_SOURCES) == 8

    def test_all_enabled(self) -> None:
        for source in DEFAULT_PROXY_SOURCES:
            assert source["enabled"] is True

    def test_protocols(self) -> None:
        protocols = {s["protocol"] for s in DEFAULT_PROXY_SOURCES}
        assert "http" in protocols
        assert "https" in protocols
        assert "socks5" in protocols
