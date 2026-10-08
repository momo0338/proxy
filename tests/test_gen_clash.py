"""Smoke tests for the Clash generator script."""

from __future__ import annotations

from typing import TYPE_CHECKING

import yaml

from scripts.gen_clash import (
    _emit_nodes,
    _parse,
    generate_full_clash_yaml,
    identify_node,
    make_unique_name,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_parse_http_and_socks5(tmp_path: Path) -> None:
    f = tmp_path / "valid_http.txt"
    f.write_text("http://1.2.3.4:8080\nhttp://5.6.7.8:3128\n# comment\n", encoding="utf-8")
    nodes = _parse(f, "http")
    assert len(nodes) == 2
    assert nodes[0] == {
        "name": "http-1.2.3.4:8080",
        "type": "http",
        "server": "1.2.3.4",
        "port": 8080,
        "udp": True,
    }


def test_parse_skips_invalid_and_dedups(tmp_path: Path) -> None:
    f = tmp_path / "valid_socks5.txt"
    f.write_text("socks5://9.9.9.9:1080\nsocks5://9.9.9.9:1080\nnot-a-url\n", encoding="utf-8")
    nodes = _parse(f, "socks5")
    assert len(nodes) == 1
    assert nodes[0]["server"] == "9.9.9.9"


def test_generated_yaml_is_valid(tmp_path: Path) -> None:
    (tmp_path / "valid_http.txt").write_text("http://1.1.1.1:80\n", encoding="utf-8")
    (tmp_path / "valid_socks5.txt").write_text("socks5://2.2.2.2:1080\n", encoding="utf-8")
    out = tmp_path / "clash_config.yaml"
    http_nodes = _parse(tmp_path / "valid_http.txt", "http")
    socks5_nodes = _parse(tmp_path / "valid_socks5.txt", "socks5")
    lines = ["proxies:", *_emit_nodes(http_nodes + socks5_nodes)]
    out.write_text("\n".join(lines), encoding="utf-8")
    data = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert len(data["proxies"]) == 2


def test_identify_node_and_unique_naming() -> None:
    name_js, group_js, code_js = identify_node("58.210.1.1", 1080, "socks5", "CN")
    assert "江苏" in name_js
    assert group_js == "🏛️ 江苏节点"
    assert code_js == "CN"

    # 新增省份节点测试
    name_sh, group_sh, code_sh = identify_node("123.60.155.1", 3128, "http", "CN")
    assert "上海" in name_sh
    assert group_sh == "🏙️ 上海节点"
    assert code_sh == "CN"

    name_bj, group_bj, code_bj = identify_node("221.217.54.146", 9000, "http", "CN")
    assert "北京" in name_bj
    assert group_bj == "🗼 北京节点"
    assert code_bj == "CN"

    name_gd, group_gd, code_gd = identify_node("221.176.85.225", 1080, "socks5", "CN")
    assert "广东" in name_gd
    assert group_gd == "🌴 广东节点"
    assert code_gd == "CN"

    # APNIC/海外子网被纠正为海外节点
    name_vn, group_vn, code_vn = identify_node("42.112.52.3", 20001, "socks5", "CN")
    assert "越南" in name_vn
    assert group_vn == "🌍 海外节点"
    assert code_vn == "VN"

    name_pk, group_pk, code_pk = identify_node("111.119.162.248", 10900, "socks5", "CN")
    assert "巴基斯坦" in name_pk
    assert group_pk == "🌍 海外节点"
    assert code_pk == "PK"

    name_us, group_us, code_us = identify_node("1.2.3.4", 8080, "http", "US")
    assert "美国" in name_us
    assert group_us == "🌍 海外节点"
    assert code_us == "US"

    # 英文国家全称解析
    name_nl, group_nl, code_nl = identify_node("1.2.3.4", 8080, "http", "The Netherlands")
    assert "荷兰" in name_nl
    assert code_nl == "NL"

    # 特征子网解析（荷兰 45.74.x.x）
    name_subnet_nl, _, code_subnet_nl = identify_node("45.74.31.30", 1234, "socks5", "")
    assert "荷兰" in name_subnet_nl
    assert code_subnet_nl == "NL"

    used: set[str] = set()
    n1 = make_unique_name("TestNode", "http", used)
    n2 = make_unique_name("TestNode", "http", used)
    assert n1 == "TestNode [HTTP]"
    assert n2 == "TestNode [HTTP] (2)"


def test_generate_full_clash_yaml_structure() -> None:
    nodes = [
        {
            "name": "🇨🇳 江苏电信 58.210.1.1:1080 [SOCKS5]",
            "type": "socks5",
            "server": "58.210.1.1",
            "port": 1080,
            "udp": True,
            "group": "🏛️ 江苏节点",
            "country_code": "CN",
        },
        {
            "name": "🇺🇸 美国 1.2.3.4:8080 [HTTP]",
            "type": "http",
            "server": "1.2.3.4",
            "port": 8080,
            "udp": True,
            "group": "🌍 海外节点",
            "country_code": "US",
        },
    ]
    yaml_str = generate_full_clash_yaml(nodes)
    cfg = yaml.safe_load(yaml_str)

    assert cfg["mixed-port"] == 7890
    assert cfg["mode"] == "rule"
    assert "dns" in cfg
    assert len(cfg["proxies"]) == 2
    assert "rules" in cfg

    group_names = [g["name"] for g in cfg["proxy-groups"]]
    assert "🚀 节点选择" in group_names
    assert "⚡ 自动优选(国内)" in group_names
    assert "🇨🇳 全部国内" in group_names
    assert "🏛️ 江苏节点" in group_names
    assert "🌍 海外节点" in group_names
