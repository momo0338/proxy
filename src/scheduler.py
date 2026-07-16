"""Scheduler for periodic proxy refresh."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.collector import ProxyCollector
from src.validator import ProxyValidator

if TYPE_CHECKING:
    from src.store import ProxyStore

log = logging.getLogger(__name__)


async def run_refresh(
    store: ProxyStore,
    config: dict[str, object],
) -> dict[str, int]:
    """Orchestrate a full collect → validate → cleanup cycle."""
    log.info("Starting refresh cycle")

    # 1. Collect
    collector = ProxyCollector(store, config)
    collected = await collector.collect()
    log.info("Collected %d proxies", collected)

    # 2. Validate unvalidated (quick-probe on by default)
    max_conc = int(config.get("max_concurrency", 800))  # type: ignore[arg-type]
    validator = ProxyValidator(config, store)
    unvalidated = store.get_unvalidated()
    valid = await validator.validate_all(unvalidated, max_conc, quick_probe=True)
    log.info("Validated %d proxies (valid: %d)", len(unvalidated), len(valid))

    # 3. Expire old
    expiry_hours = int(config.get("proxy_expiry_hours", 6))  # type: ignore[arg-type]
    expired = store.delete_expired(expiry_hours)
    log.info("Expired %d old proxies", expired)

    counts = store.count()
    stats = {
        "collected": collected,
        "validated": len(unvalidated),
        "valid": counts["valid"],
        "expired": expired,
    }
    log.info("Refresh complete: %s", stats)
    return stats


class RefreshService:
    """Manages scheduled proxy refresh via APScheduler."""

    def __init__(self, store: ProxyStore, config: dict[str, object]) -> None:
        """Initialise refresh service."""
        self._store = store
        self._config = config
        self._scheduler = AsyncIOScheduler()

    async def refresh(self) -> dict[str, int]:
        """Run one refresh cycle."""
        return await run_refresh(self._store, self._config)

    async def _job(self) -> None:
        """Scheduled job wrapper with error handling."""
        try:
            await self.refresh()
        except (OSError, ValueError):
            log.exception("Refresh failed")

    def start(self) -> None:
        """Start the scheduler with an interval trigger."""
        interval = int(self._config.get("refresh_interval_minutes", 30))  # type: ignore[arg-type]
        self._scheduler.add_job(
            self._job,
            trigger=IntervalTrigger(minutes=interval),
            id="proxy_refresh",
            replace_existing=True,
        )
        self._scheduler.start()
        log.info("Scheduler started (interval: %d minutes)", interval)

    def shutdown(self) -> None:
        """Gracefully shut down the scheduler."""
        self._scheduler.shutdown()
        log.info("Scheduler stopped")
