"""Configuration management with backward compatibility."""

from __future__ import annotations

import json
from pathlib import Path

from src.models import ProxyProtocol

# ---------------------------------------------------------------------------
# Default proxy sources — curated multi-protocol public lists.
# Fields per entry:
#   name / url / protocol / enabled
#   weight: relative sampling weight (higher = preferred). Reserved for the
#           sampling/optimisation pass; not yet enforced by the collector.
#   max:    per-source cap on kept proxies per collect cycle.
# The parser auto-detects `scheme://ip:port` and `ip:port:PROTOCOL` lines, so
# `protocol` here is only the fallback for plain `ip:port` rows.
# ---------------------------------------------------------------------------
DEFAULT_PROXY_SOURCES: list[dict[str, object]] = [
    {
        "name": "Hookzof SOCKS5",
        "url": "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
        "protocol": "socks5",
        "enabled": True,
        "weight": 3,
    },
    {
        "name": "ALIILAPRO SOCKS5",
        "url": "https://raw.githubusercontent.com/ALIILAPRO/Proxy/main/socks5.txt",
        "protocol": "socks5",
        "enabled": True,
        "weight": 3,
    },
    {
        "name": "Monosans HTTP",
        "url": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
        "protocol": "http",
        "enabled": True,
        "weight": 2,
    },
    {
        "name": "Monosans SOCKS5",
        "url": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
        "protocol": "socks5",
        "enabled": True,
        "weight": 2,
    },
    {
        "name": "mmpx12 SOCKS5",
        "url": "https://raw.githubusercontent.com/mmpx12/proxy-list/master/socks5.txt",
        "protocol": "socks5",
        "enabled": True,
        "weight": 2,
    },
    {
        "name": "Zaeem20 SOCKS5",
        "url": "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/socks5.txt",
        "protocol": "socks5",
        "enabled": True,
        "weight": 2,
    },
    {
        "name": "Zaeem20 HTTP",
        "url": "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/http.txt",
        "protocol": "http",
        "enabled": True,
        "weight": 2,
    },
    {
        "name": "ALIILAPRO HTTP",
        "url": "https://raw.githubusercontent.com/ALIILAPRO/Proxy/main/http.txt",
        "protocol": "http",
        "enabled": True,
        "weight": 1,
    },
    {
        "name": "mmpx12 HTTP",
        "url": "https://raw.githubusercontent.com/mmpx12/proxy-list/master/http.txt",
        "protocol": "http",
        "enabled": True,
        "weight": 1,
    },
    {
        "name": "TheSpeedX HTTP",
        "url": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
        "protocol": "http",
        "enabled": True,
        "weight": 1,
    },
    {
        "name": "TheSpeedX SOCKS5",
        "url": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
        "protocol": "socks5",
        "enabled": True,
        "weight": 1,
    },
    {
        "name": "roosterkid HTTPS",
        "url": "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
        "protocol": "https",
        "enabled": True,
        "weight": 1,
    },
    {
        "name": "roosterkid SOCKS5",
        "url": "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5_RAW.txt",
        "protocol": "socks5",
        "enabled": True,
        "weight": 1,
    },
    {
        "name": "sunny9577 HTTP",
        "url": "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/generated/http_proxies.txt",
        "protocol": "http",
        "enabled": True,
        "weight": 1,
    },
    {
        "name": "sunny9577 SOCKS5",
        "url": "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/generated/socks5_proxies.txt",
        "protocol": "socks5",
        "enabled": True,
        "weight": 1,
    },
    {
        "name": "vakhov HTTP",
        "url": "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/http.txt",
        "protocol": "http",
        "enabled": True,
        "weight": 1,
    },
    {
        "name": "vakhov SOCKS5",
        "url": "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks5.txt",
        "protocol": "socks5",
        "enabled": True,
        "weight": 1,
    },
    {
        "name": "Tsprnay HTTP",
        "url": "https://raw.githubusercontent.com/Tsprnay/Proxy-lists/master/proxies/http.txt",
        "protocol": "http",
        "enabled": True,
        "weight": 1,
        "max": 2000,
    },
    {
        "name": "Tsprnay SOCKS5",
        "url": "https://raw.githubusercontent.com/Tsprnay/Proxy-lists/master/proxies/socks5.txt",
        "protocol": "socks5",
        "enabled": True,
        "weight": 1,
        "max": 2000,
    },
    {
        "name": "proxifly ALL",
        "url": "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/all/data.txt",
        "protocol": "http",
        "enabled": True,
        "weight": 1,
        "max": 2000,
    },
    {
        "name": "clarketm HTTP",
        "url": "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
        "protocol": "http",
        "enabled": True,
        "weight": 1,
    },
    {
        "name": "ShiftyTR HTTP",
        "url": "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
        "protocol": "http",
        "enabled": True,
        "weight": 1,
    },
]

# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------
DEFAULT_CONFIG: dict[str, object] = {
    "timeout": 30,
    "verify_timeout": 5.0,
    # 死代理快速跳过: 首轮单端点 + 短超时快筛, 通了才走完整验证。
    "quick_probe_timeout": 3.0,
    # 每个代理硬超时(秒); 兜底黑洞 DNS/半开连接。0 = verify_timeout * 2。
    "verify_hard_timeout": 0,
    "output_dir": "output",
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    # --- Source collection caps ---
    # 单次采集总量上限(去重后), 0 = 不限制。当前不设上限, 先拉全量做基线。
    "collect_limit": 0,
    # 未显式配置 max 的源, 每源默认保留条数。0 = 不限制(拉全部)。
    "collect_per_source_default": 0,
    # --- New service keys ---
    "db_path": "data/proxies.db",
    "refresh_interval_minutes": 30,
    "proxy_expiry_hours": 6,
    # 单代理经代理链访问外部 echo 服务很慢, 靠高并发掩盖延迟而非堆超时。
    # 默认 100: 兼容 macOS 默认 ulimit -n=256 的文件描述符上限。
    # 服务器可调高(如 800), 但需先 ulimit -n 4096 之类放开口子。
    "max_concurrency": 100,
    "verify_endpoints": [
        "https://api.ipify.org?format=json",
        "https://ipinfo.io/json",
        "https://ip.my-ip.io/json",
    ],
    # 国内 IP 专用验证端点: 严格 HTTPS 加密隧道 + 国内稳定 CDN/高可用端点
    "china_verify_endpoints": [
        "https://connect.rom.miui.com/generate_204",
        "https://connectivitycheck.platform.hicloud.com/generate_204",
        "https://myip.ipip.net/json",
        "https://www.baidu.com",
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
                # Allow grouping collection caps under a nested "settings" object.
                settings = user_config.pop("settings", None)
                config.update(user_config)
                if isinstance(settings, dict):
                    config.update(settings)
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
