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
        for result in results:
            if isinstance(result, BaseException):
                log.warning("Source fetch failed: %s", result)
                continue
            all_records.extend(result)

        # Upsert all collected records as unvalidated
        unvalidated = [
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
            for rec in all_records
        ]

        self._store.save_many(unvalidated)
        return len(unvalidated)
