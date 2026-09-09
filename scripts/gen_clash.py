#!/usr/bin/env python3
"""Generate Clash / Mihomo proxy configuration with province-based groups.

Reads validated proxies (from ``data/valid_proxies.json``, SQLite DB, or flat
text files) and generates:
``data/clash_config.yaml``: Full ready-to-use profile for Clash Verge with
   province-level proxy groups (Jiangsu, Beijing, Shanghai, Zhejiang, Guangdong, etc.).

Usage:
    python scripts/gen_clash.py [--data-dir data] [--out data/clash_config.yaml]
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

ADDR_RE = re.compile(r"^(?P<proto>https?|socks5)://(?P<host>[^:/]+):(?P<port>\d+)/?$")


def identify_node(ip: str, port: int, proto: str, country: str = "") -> tuple[str, str, str]:
    """Identify location, province group, and country code from IP and country."""
    parts = (
        [int(p) for p in ip.split(".")]
        if ip.count(".") == 3 and all(p.isdigit() for p in ip.split("."))
        else [0, 0, 0, 0]
    )

    # 1. 江苏省 (Jiangsu)
    if parts[0] == 58 and 210 <= parts[1] <= 223:
        city = (
            "苏州"
            if parts[1] == 210
            else ("无锡" if parts[1] == 211 else ("南京" if parts[1] == 213 else ""))
        )
        return f"🇨🇳 江苏{city}电信 {ip}:{port}", "🏛️ 江苏节点", "CN"
    if parts[0] == 120 and parts[1] in (193, 194, 195):
        return f"🇨🇳 江苏移动 {ip}:{port}", "🏛️ 江苏节点", "CN"
    if parts[0] == 183 and 207 <= parts[1] <= 215:
        return f"🇨🇳 江苏移动 {ip}:{port}", "🏛️ 江苏节点", "CN"
    if (
        (parts[0] == 114 and 220 <= parts[1] <= 239)
        or (parts[0] == 121 and 224 <= parts[1] <= 239)
        or (parts[0] == 117 and 80 <= parts[1] <= 95)
        or (parts[0] == 218 and 90 <= parts[1] <= 94)
        or (parts[0] == 221 and 224 <= parts[1] <= 231)
        or (parts[0] == 222 and 184 <= parts[1] <= 191)
        or (parts[0] == 122 and 192 <= parts[1] <= 195)
        or (parts[0] == 61 and parts[1] in (160, 177))
        or (parts[0] == 180 and 96 <= parts[1] <= 127)
        or (parts[0] == 49 and 64 <= parts[1] <= 95)
    ):
        return f"🇨🇳 江苏电信 {ip}:{port}", "🏛️ 江苏节点", "CN"
    if parts[0] == 112 and 80 <= parts[1] <= 87:
        return f"🇨🇳 江苏联通 {ip}:{port}", "🏛️ 江苏节点", "CN"

    # 2. 北京市 (Beijing)
    if (
        (parts[0] == 111 and 192 <= parts[1] <= 207)
        or (parts[0] == 114 and 240 <= parts[1] <= 255)
        or (parts[0] == 123 and 112 <= parts[1] <= 127)
        or (parts[0] == 124 and 64 <= parts[1] <= 65)
        or (parts[0] == 221 and parts[1] == 221)
        or (parts[0] == 222 and parts[1] == 128)
        or (parts[0] == 61 and parts[1] == 149)
    ):
        return f"🇨🇳 北京联通 {ip}:{port}", "🗼 北京节点", "CN"
    if parts[0] == 219 and parts[1] == 142:
        return f"🇨🇳 北京电信 {ip}:{port}", "🗼 北京节点", "CN"
    if ip in ("39.106.165.196", "39.106.170.168", "47.95.206.224", "123.57.213.24"):
        return f"🇨🇳 北京阿里云 {ip}:{port}", "🗼 北京节点", "CN"
    if ip == "111.229.76.29":
        return f"🇨🇳 北京腾讯云 {ip}:{port}", "🗼 北京节点", "CN"

    # 3. 上海市 (Shanghai)
    if (
        (parts[0] == 61 and parts[1] == 152)
        or (parts[0] == 218 and parts[1] == 78)
        or (parts[0] == 180 and parts[1] == 165)
    ):
        return f"🇨🇳 上海电信 {ip}:{port}", "🏙️ 上海节点", "CN"
    if parts[0] == 112 and parts[1] == 64:
        return f"🇨🇳 上海联通 {ip}:{port}", "🏙️ 上海节点", "CN"
    if ip == "101.132.170.8":
        return f"🇨🇳 上海阿里云 {ip}:{port}", "🏙️ 上海节点", "CN"

    # 4. 浙江省 (Zhejiang)
    if parts[0] == 115 and parts[1] == 231:
        return f"🇨🇳 浙江电信 {ip}:{port}", "🌊 浙江节点", "CN"
    if parts[0] == 122 and parts[1] == 246:
        return f"🇨🇳 浙江金华电信 {ip}:{port}", "🌊 浙江节点", "CN"
    if parts[0] == 183 and parts[1] == 248:
        return f"🇨🇳 浙江金华移动 {ip}:{port}", "🌊 浙江节点", "CN"
    if ip in ("120.26.171.55", "47.121.139.13"):
        return f"🇨🇳 浙江杭州阿里云 {ip}:{port}", "🌊 浙江节点", "CN"

    # 5. 广东省 (Guangdong)
    if parts[0] == 120 and parts[1] == 232:
        return f"🇨🇳 广东移动 {ip}:{port}", "🌴 广东节点", "CN"
    if parts[0] == 58 and parts[1] == 254:
        return f"🇨🇳 广东广州电信 {ip}:{port}", "🌴 广东节点", "CN"
    if ip in ("47.107.107.24", "47.107.82.96", "8.138.217.152"):
        return f"🇨🇳 广东阿里云 {ip}:{port}", "🌴 广东节点", "CN"
    if ip == "49.234.4.115":
        return f"🇨🇳 广东腾讯云 {ip}:{port}", "🌴 广东节点", "CN"

    # 6. 其他省份
    if parts[0] == 123 and parts[1] == 129:
        return f"🇨🇳 山东济南电信 {ip}:{port}", "🌾 山东节点", "CN"
    if parts[0] == 119 and parts[1] == 188:
        return f"🇨🇳 山东联通 {ip}:{port}", "🌾 山东节点", "CN"
    if parts[0] == 111 and parts[1] == 79:
        return f"🇨🇳 江西吉安电信 {ip}:{port}", "🍃 江西节点", "CN"
    if parts[0] == 116 and parts[1] == 211:
        return f"🇨🇳 湖北武汉电信 {ip}:{port}", "🍂 湖北节点", "CN"
    if (parts[0] == 123 and parts[1] == 138) or (parts[0] == 113 and 140 <= parts[1] <= 143):
        return f"🇨🇳 陕西西安电信 {ip}:{port}", "🏔️ 陕西节点", "CN"
    if parts[0] == 183 and parts[1] == 201:
        return f"🇨🇳 陕西西安移动 {ip}:{port}", "🏔️ 陕西节点", "CN"
    if parts[0] == 171 and parts[1] == 220:
        return f"🇨🇳 四川成都电信 {ip}:{port}", "🏞️ 四川节点", "CN"
    if parts[0] == 27 and parts[1] == 185:
        return f"🇨🇳 河北电信 {ip}:{port}", "🏮 河北节点", "CN"
    if parts[0] == 113 and parts[1] == 249:
        return f"🇨🇳 重庆电信 {ip}:{port}", "🌶️ 重庆节点", "CN"
    if parts[0] == 113 and parts[1] == 45:
        return f"🇨🇳 腾讯云 {ip}:{port}", "🌐 其他国内", "CN"
    if parts[0] == 47 and parts[1] == 84:
        return f"🇨🇳 阿里云 {ip}:{port}", "🌐 其他国内", "CN"
    if str(country).upper() == "CN":
        return f"🇨🇳 中国节点 {ip}:{port}", "🌐 其他国内", "CN"

    # 7. 海外节点
    c = str(country).upper()
    flag_map = {
        "US": ("🇺🇸 美国", "US"),
        "HK": ("🇭🇰 香港", "HK"),
        "TW": ("🇹🇼 台湾", "TW"),
        "JP": ("🇯🇵 日本", "JP"),
        "SG": ("🇸🇬 新加坡", "SG"),
        "KR": ("🇰🇷 韩国", "KR"),
        "DE": ("🇩🇪 德国", "DE"),
        "GB": ("🇬🇧 英国", "GB"),
        "FR": ("🇫🇷 法国", "FR"),
        "NL": ("🇳🇱 荷兰", "NL"),
        "RU": ("🇷🇺 俄罗斯", "RU"),
        "CA": ("🇨🇦 加拿大", "CA"),
        "AU": ("🇦🇺 澳大利亚", "AU"),
        "IN": ("🇮🇳 印度", "IN"),
        "VN": ("🇻🇳 越南", "VN"),
        "TH": ("🇹🇭 泰国", "TH"),
        "ID": ("🇮🇩 印尼", "ID"),
        "BR": ("🇧🇷 巴西", "BR"),
        "MX": ("🇲🇽 墨西哥", "MX"),
        "PL": ("🇵🇱 波兰", "PL"),
        "IT": ("🇮🇹 意大利", "IT"),
        "ES": ("🇪🇸 西班牙", "ES"),
        "ZA": ("🇿🇦 南非", "ZA"),
        "SE": ("🇸🇪 瑞典", "SE"),
        "CH": ("🇨🇭 瑞士", "CH"),
        "AT": ("🇦🇹 奥地利", "AT"),
        "UA": ("🇺🇦 乌克兰", "UA"),
    }
    for k, (prefix, code) in flag_map.items():
        if k == c or k in c:
            return f"{prefix} {ip}:{port}", "🌍 海外节点", code

    return f"🌐 海外 {ip}:{port}", "🌍 海外节点", "OTHER"


def make_unique_name(base_name: str, proto: str, used_names: set[str]) -> str:
    """Ensure every node name in Clash is strictly unique."""
    proto_label = proto.upper()
    candidate = f"{base_name} [{proto_label}]"
    if candidate not in used_names:
        used_names.add(candidate)
        return candidate

    idx = 2
    while True:
        candidate_indexed = f"{base_name} [{proto_label}] ({idx})"
        if candidate_indexed not in used_names:
            used_names.add(candidate_indexed)
            return candidate_indexed
        idx += 1


def _parse(path: Path, clash_type: str) -> list[dict]:
    """Parse a flat address file into Clash proxy node dicts."""
    nodes: list[dict] = []
    if not path.exists():
        return nodes
    seen: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = ADDR_RE.match(line)
        if not m:
            continue
        host, port = m.group("host"), int(m.group("port"))
        name = f"{clash_type}-{host}:{port}"
        if name in seen:
            continue
        seen.add(name)
        nodes.append(
            {
                "name": name,
                "type": clash_type,
                "server": host,
                "port": port,
                "udp": True,
            }
        )
    return nodes


def _yaml_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _emit_nodes(nodes: list[dict]) -> list[str]:
    lines: list[str] = []
    for n in nodes:
        lines.append(f"  - name: \"{n['name']}\"")
        lines.append(f"    type: {n['type']}")
        lines.append(f"    server: {n['server']}")
        lines.append(f"    port: {n['port']}")
        lines.append(f"    udp: {_yaml_scalar(n['udp'])}")
    return lines


def load_all_valid_proxies(data_dir: Path) -> list[dict]:
    """Load all valid proxies from valid_proxies.json, SQLite DB, or flat files."""
    nodes: list[dict] = []
    seen: set[tuple[str, int, str]] = set()
    used_names: set[str] = set()

    # 1. Try valid_proxies.json
    json_path = data_dir / "valid_proxies.json"
    if json_path.exists():
        try:
            with open(json_path, encoding="utf-8") as f:
                data = json.load(f)
            for p in data.get("proxies", []):
                addr = p.get("address", "")
                m = ADDR_RE.match(addr)
                if m:
                    proto, host, port = m.group("proto"), m.group("host"), int(m.group("port"))
                    key = (host, port, proto)
                    if key not in seen:
                        seen.add(key)
                        base_name, group, ccode = identify_node(host, port, proto, p.get("country", ""))
                        unique_name = make_unique_name(base_name, proto, used_names)
                        nodes.append(
                            {
                                "name": unique_name,
                                "type": "socks5" if proto == "socks5" else "http",
                                "server": host,
                                "port": port,
                                "udp": True,
                                "group": group,
                                "country_code": ccode,
                            }
                        )
        except Exception:
            pass

    # 2. Try DB if exists
    db_path = data_dir / "proxies.db"
    if db_path.exists():
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
            cursor.execute(
                "SELECT ip, port, protocol, country FROM proxies WHERE is_valid=1 AND (last_verified >= ? OR last_verified = '');",
                (cutoff,),
            )
            for ip, port, proto, country in cursor.fetchall():
                key = (ip, port, proto)
                if key not in seen:
                    seen.add(key)
                    base_name, group, ccode = identify_node(ip, port, proto, country)
                    unique_name = make_unique_name(base_name, proto, used_names)
                    nodes.append(
                        {
                            "name": unique_name,
                            "type": "socks5" if proto == "socks5" else "http",
                            "server": ip,
                            "port": port,
                            "udp": True,
                            "group": group,
                            "country_code": ccode,
                        }
                    )
            conn.close()
        except Exception:
            pass

    # 3. Fallback to flat files if no nodes found yet
    if not nodes:
        http_nodes = _parse(data_dir / "valid_http.txt", "http")
        socks5_nodes = _parse(data_dir / "valid_socks5.txt", "socks5")
        for n in http_nodes + socks5_nodes:
            host, port, proto = n["server"], n["port"], n["type"]
            base_name, group, ccode = identify_node(host, port, proto, "")
            unique_name = make_unique_name(base_name, proto, used_names)
            n["name"] = unique_name
            n["group"] = group
            n["country_code"] = ccode
            nodes.append(n)

    return nodes


def generate_full_clash_yaml(nodes: list[dict]) -> str:
    """Generate a complete standalone Clash Verge configuration YAML."""
    # Group nodes by region
    groups: dict[str, list[str]] = {}
    china_nodes: list[str] = []
    overseas_nodes: list[str] = []

    for n in nodes:
        g = n.get("group", "🌍 海外节点")
        groups.setdefault(g, []).append(n["name"])
        if n.get("country_code") == "CN":
            china_nodes.append(n["name"])
        else:
            overseas_nodes.append(n["name"])

    lines: list[str] = [
        "# Clash Verge / Mihomo 配置文件 (按省份分组)",
        "# 可直接导入 Clash Verge 的「订阅 / 配置」中使用",
        "mixed-port: 7890",
        "allow-lan: false",
        "mode: rule",
        "log-level: info",
        "ipv6: false",
        "external-controller: 127.0.0.1:9090",
        "",
        "dns:",
        "  enable: true",
        "  listen: 0.0.0.0:1053",
        "  enhanced-mode: fake-ip",
        "  fake-ip-range: 198.18.0.1/16",
        "  nameserver:",
        "    - 223.5.5.5",
        "    - 119.29.29.29",
        "    - 114.114.114.114",
        "",
        "proxies:",
    ]

    lines.extend(_emit_nodes(nodes))
    lines.append("")
    lines.append("proxy-groups:")

    # Top-level Selector
    province_group_names = [g for g in groups if g != "🌍 海外节点"]
    lines.append("  - name: 🚀 节点选择")
    lines.append("    type: select")
    lines.append("    proxies:")
    lines.append("      - ⚡ 自动优选(国内)")
    lines.append("      - 🇨🇳 全部国内")
    lines.extend(f"      - {gname}" for gname in province_group_names)
    if overseas_nodes:
        lines.append("      - 🌍 海外节点")
    lines.append("      - DIRECT")
    lines.append("")

    # Auto URL-Test for China (Use domestic 204 endpoint to prevent timeout on CN proxies)
    if china_nodes:
        lines.append("  - name: ⚡ 自动优选(国内)")
        lines.append("    type: url-test")
        lines.append("    url: http://connect.rom.miui.com/generate_204")
        lines.append("    interval: 300")
        lines.append("    tolerance: 50")
        lines.append("    proxies:")
        lines.extend(f"      - {name}" for name in china_nodes)
        lines.append("")

    # All China Group
    if china_nodes:
        lines.append("  - name: 🇨🇳 全部国内")
        lines.append("    type: select")
        lines.append("    proxies:")
        lines.extend(f"      - {name}" for name in china_nodes)
        lines.append("")

    # Specific Province Groups (e.g. 江苏, 北京, 上海, 浙江, 广东, etc.)
    for gname, member_names in groups.items():
        if gname == "🌍 海外节点":
            continue
        lines.append(f"  - name: {gname}")
        lines.append("    type: select")
        lines.append("    proxies:")
        lines.extend(f"      - {m}" for m in member_names)
        lines.append("")

    # Overseas Group
    if overseas_nodes:
        lines.append("  - name: 🌍 海外节点")
        lines.append("    type: select")
        lines.append("    proxies:")
        lines.extend(f"      - {name}" for name in overseas_nodes)
        lines.append("")

    # Rules
    lines.append("rules:")
    lines.append("  - MATCH,🚀 节点选择")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    """Generate Clash/mihomo proxy configuration profile."""
    parser = argparse.ArgumentParser(description="Generate Clash proxy config with province groups")
    parser.add_argument("--data-dir", default="data", help="Directory with proxy data")
    parser.add_argument(
        "--out",
        default=None,
        help="Output full Clash Verge config path (default: <data-dir>/clash_config.yaml)",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        repo_data = Path(__file__).resolve().parent.parent / args.data_dir
        if repo_data.exists():
            data_dir = repo_data

    out_path = Path(args.out) if args.out else data_dir / "clash_config.yaml"

    nodes = load_all_valid_proxies(data_dir)
    if not nodes:
        print(f"No validated proxies found in {data_dir} (run `python main.py validate` first)")
        return

    full_yaml = generate_full_clash_yaml(nodes)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(full_yaml, encoding="utf-8")

    cn_count = sum(1 for n in nodes if n.get("country_code") == "CN")
    js_count = sum(1 for n in nodes if "江苏" in n.get("group", ""))
    print(f"Wrote {len(nodes)} proxies ({cn_count} China, {js_count} Jiangsu) to {out_path}")


if __name__ == "__main__":
    main()
