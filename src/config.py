"""Configuration management with backward compatibility."""

from __future__ import annotations

import json
from pathlib import Path

from src.models import ProxyProtocol

# ---------------------------------------------------------------------------
# Default proxy sources — all 8 original GitHub sources preserved exactly
# ---------------------------------------------------------------------------
DEFAULT_PROXY_SOURCES: list[dict[str, object]] = [
    {
        "name": "TheSpeedX HTTP",
        "url": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
        "protocol": "http",
        "format": "ip:port",
        "enabled": True,
    },
    {
        "name": "Monosans HTTP",
        "url": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
        "protocol": "http",
        "format": "ip:port",
        "enabled": True,
    },
    {
        "name": "clarketm HTTP",
        "url": "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
        "protocol": "http",
        "format": "ip:port",
        "enabled": True,
    },
    {
        "name": "ShiftyTR HTTP",
        "url": "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
        "protocol": "http",
        "format": "ip:port",
        "enabled": True,
    },
    {
        "name": "roosterkid HTTPS",
        "url": "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
        "protocol": "https",
        "format": "ip:port",
        "enabled": True,
    },
    {
        "name": "TheSpeedX SOCKS5",
        "url": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
        "protocol": "socks5",
        "format": "ip:port",
        "enabled": True,
    },
    {
        "name": "Monosans SOCKS5",
        "url": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
        "protocol": "socks5",
        "format": "ip:port",
        "enabled": True,
    },
    {
        "name": "Hookzof SOCKS5",
        "url": "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
        "protocol": "socks5",
        "format": "ip:port",
        "enabled": True,
    },
]

# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------
DEFAULT_CONFIG: dict[str, object] = {
    "timeout": 30,
    "max_workers": 20,
    "verify_timeout": 5.0,
    "max_verify": 200,
    "output_dir": "output",
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    # --- New service keys ---
    "db_path": "data/proxies.db",
    "refresh_interval_minutes": 30,
    "proxy_expiry_hours": 6,
    "max_concurrency": 50,
    "verify_endpoints": ["http://httpbin.org/ip"],
    "anon_check_url": "http://httpbin.org/ip",
    "country_url": "http://ip-api.com/json",
}


def load_config(config_file: str | None = None) -> dict[str, object]:
    """Load config, merging user overrides onto DEFAULT_CONFIG."""
    config: dict[str, object] = DEFAULT_CONFIG.copy()

    if config_file and Path(config_file).exists():
        try:
            with Path(config_file).open(encoding="utf-8") as fh:
                user_config = json.load(fh)
                config.update(user_config)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"Failed to load config file: {exc}")

    return config


def load_proxy_sources(config_file: str | None = None) -> list[dict[str, object]]:
    """Load proxy source list from config file or fall back to defaults."""
    if config_file and Path(config_file).exists():
        try:
            with Path(config_file).open(encoding="utf-8") as fh:
                user_config = json.load(fh)
                if "sources" in user_config:
                    return user_config["sources"]
        except (json.JSONDecodeError, OSError) as exc:
            print(f"Failed to load config file: {exc}")

    return DEFAULT_PROXY_SOURCES


def parse_protocol(value: str) -> ProxyProtocol:
    """Map a protocol string to ProxyProtocol enum."""
    match value.lower().strip():
        case "http":
            return ProxyProtocol.HTTP
        case "https":
            return ProxyProtocol.HTTPS
        case "socks4":
            return ProxyProtocol.SOCKS4
        case "socks5":
            return ProxyProtocol.SOCKS5
        case other:
            msg = f"Unknown protocol: {other}"
            raise ValueError(msg)


# Backward compat alias
PROXY_SOURCES: list[dict[str, object]] = DEFAULT_PROXY_SOURCES
