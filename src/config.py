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
    # 死代理快速跳过: 首轮单端点 + 短超时快筛, 通了才走完整验证。
    "quick_probe_timeout": 3.0,
    # 每个代理硬超时(秒); 兜底黑洞 DNS/半开连接。0 = verify_timeout * 2。
    "verify_hard_timeout": 0,
    "max_verify": 200,
    "output_dir": "output",
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    # --- New service keys ---
    "db_path": "data/proxies.db",
    "refresh_interval_minutes": 30,
    "proxy_expiry_hours": 6,
    # 单代理经代理链访问外部 echo 服务很慢, 靠高并发掩盖延迟而非堆超时。
    # 默认 100: 兼容 macOS 默认 ulimit -n=256 的文件描述符上限。
    # 服务器可调高(如 800), 但需先 ulimit -n 4096 之类放开口子。
    "max_concurrency": 100,
    "verify_endpoints": [
        "https://ipinfo.io/json",
        "https://api.ipify.org?format=json",
        "http://httpbin.org/ip",
        "https://ip.my-ip.io/json",
        "https://myip.ipip.net/json",  # 国内可达兜底, 返回 {"ip":...}
    ],
    "anon_check_url": "https://ipinfo.io/json",
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
