"""Export validated proxies to disk for manual use.

After validation, the usable proxies live in SQLite. This module dumps them
into ``data/`` as both JSON (structured, classified) and plain text (one
address per line, classified by protocol and anonymity) so they can be copied
or fed to other tools directly.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

from src.models import ProxyProtocol

if TYPE_CHECKING:
    from src.models import Anonymity, ProxyRecord
    from src.store import ProxyStore


def export_valid(
    store: ProxyStore,
    out_dir: str | Path,
    *,
    expiry_hours: int = 6,
    fresh_only: bool = False,
) -> dict[str, object]:
    """Write all valid proxies in the store to ``out_dir``.

    Defaults to every ``is_valid=1`` record (``fresh_only=False``) so a manual
    export gives the full usable list; serve/API still apply freshness windows
    when serving on demand. Pass ``fresh_only=True`` to restrict to recently
    verified proxies.

    Produces:
      - valid_proxies.json    classified dict + summary
      - valid_proxies.txt     every usable address, grouped by protocol/anonymity
      - valid_<protocol>.txt  one per protocol, flat address list

    Returns a summary dict (counts by protocol/anonymity, file paths).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    records = store.get_valid(only_fresh=fresh_only, expiry_hours=expiry_hours)
    if not records:
        _clean_stale_files(out_dir)
        return {"total": 0, "files": []}

    # 分类: protocol -> anonymity -> [records]
    grouped: dict[ProxyProtocol, dict[Anonymity, list[ProxyRecord]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for rec in records:
        grouped[rec.protocol][rec.anonymity].append(rec)

    json_obj: dict[str, object] = {
        "total": len(records),
        "by_protocol": {},
        "proxies": [],
    }
    for protocol, by_anon in grouped.items():
        proto_entry: dict[str, object] = {"total": 0, "by_anonymity": {}, "addresses": []}
        for anon, recs in by_anon.items():
            proto_entry["by_anonymity"][anon.value] = len(recs)
            proto_entry["total"] = int(proto_entry["total"]) + len(recs)  # type: ignore[arg-type]
            for rec in recs:
                proto_entry["addresses"].append(rec.address)  # type: ignore[attr-defined]
                json_obj["proxies"].append(  # type: ignore[attr-defined]
                    {
                        "address": rec.address,
                        "protocol": rec.protocol.value,
                        "anonymity": rec.anonymity.value,
                        "country": rec.country,
                        "response_time": rec.response_time,
                    }
                )
        json_obj["by_protocol"][protocol.value] = proto_entry  # type: ignore[attr-defined]

    json_path = out_dir / "valid_proxies.json"
    json_path.write_text(json.dumps(json_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    txt_path = out_dir / "valid_proxies.txt"
    lines: list[str] = [f"# 可用代理 {len(records)} 条 (按协议/匿名度分类)", ""]
    for protocol in sorted(grouped, key=lambda p: p.value):
        by_anon = grouped[protocol]
        for anon in sorted(by_anon, key=lambda a: a.value):
            recs = by_anon[anon]
            lines.append(f"## {protocol.value.upper()} / {anon.value} ({len(recs)})")
            lines.extend(rec.address for rec in recs)
            lines.append("")
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # 单协议扁平文件, 方便只认某协议的工具直接吃
    per_protocol_files: list[str] = []
    for protocol, by_anon in grouped.items():
        flat = [rec.address for recs in by_anon.values() for rec in recs]
        ppath = out_dir / f"valid_{protocol.value}.txt"
        ppath.write_text("\n".join(flat) + "\n", encoding="utf-8")
        per_protocol_files.append(str(ppath))

    return {
        "total": len(records),
        "by_protocol": {p.value: sum(len(r) for r in a.values()) for p, a in grouped.items()},
        "files": [str(json_path), str(txt_path), *per_protocol_files],
    }


def _clean_stale_files(out_dir: Path) -> None:
    """Remove previously exported files when there is nothing to export.

    Prevents a stale valid-proxy list from lingering after a run that produced
    zero usable proxies.
    """
    for name in ("valid_proxies.json", "valid_proxies.txt"):
        (out_dir / name).unlink(missing_ok=True)
    for proto in ProxyProtocol:
        (out_dir / f"valid_{proto.value}.txt").unlink(missing_ok=True)
