"""Proxy collector — fetches from all configured sources."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from src.models import ProxyRecord
from src.sources import TextSource, build_sources

if TYPE_CHECKING:
    from src.store import ProxyStore

log = logging.getLogger(__name__)


class ProxyCollector:
    """Collect proxies from remote sources and store them."""

    def __init__(self, store: ProxyStore, config: dict[str, object]) -> None:
        """Initialise collector with store and config."""
        self._store = store
        self._config = config
        self._sources: list[TextSource] = build_sources(config)

    async def collect(self) -> int:
        """Fetch from all sources concurrently, upsert records. Return count collected."""
        if not self._sources:
            log.warning("No sources configured")
            return 0

        async def _fetch_one(source: TextSource) -> list[ProxyRecord]:
            """Run sync fetch in a thread."""
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, source.fetch)

        results = await asyncio.gather(
            *[_fetch_one(s) for s in self._sources],
            return_exceptions=True,
        )

        all_records: list[ProxyRecord] = []
        fetched: dict[str, int] = {}
        for source, result in zip(self._sources, results, strict=False):
            if isinstance(result, BaseException):
                log.warning("Source fetch failed: %s", result)
                fetched[source.name] = 0
                continue
            all_records.extend(result)
            fetched[source.name] = len(result)

        # Deduplicate by (ip, port, protocol) and apply the global collect cap.
        limit_val = self._config.get("collect_limit", 0)
        collect_limit = int(limit_val) if isinstance(limit_val, (int, float)) else 0

        seen: set[str] = set()
        unvalidated: list[ProxyRecord] = []
        contrib: dict[str, int] = {}
        for rec in all_records:
            key = f"{rec.ip}:{rec.port}:{rec.protocol}"
            if key in seen:
                continue
            seen.add(key)
            contrib[rec.source] = contrib.get(rec.source, 0) + 1
            unvalidated.append(
                ProxyRecord(
                    ip=rec.ip,
                    port=rec.port,
                    protocol=rec.protocol,
                    source=rec.source,
                    country=rec.country,
                    anonymity=rec.anonymity,
                    response_time=0.0,
                    last_verified="",
                    is_valid=False,
                )
            )
            if collect_limit > 0 and len(unvalidated) >= collect_limit:
                break

        print(
            f"  [collect] 抓取 {len(all_records)} 条, 去重后 {len(unvalidated)} 条;"
            " 每源 抓取/去重贡献:",
            flush=True,
        )
        for name, n in fetched.items():
            print(f"    - {name:28s} {n:7d} / {contrib.get(name, 0):7d}", flush=True)

        self._store.save_many(unvalidated)
        return len(unvalidated)
