"""Smoke tests for the Clash generator script."""

from __future__ import annotations

from typing import TYPE_CHECKING

import yaml

from scripts.gen_clash import _emit_nodes, _parse

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
    out = tmp_path / "clash_proxies.yaml"
    http_nodes = _parse(tmp_path / "valid_http.txt", "http")
    socks5_nodes = _parse(tmp_path / "valid_socks5.txt", "socks5")
    lines = ["proxies:", *_emit_nodes(http_nodes + socks5_nodes)]
    out.write_text("\n".join(lines), encoding="utf-8")
    data = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert len(data["proxies"]) == 2
