"""Proxy Pool Service — CLI and long-running daemon."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from src.store import ProxyStore

app = typer.Typer(help="Proxy Pool Service — collect, validate, and serve proxies")

SEPARATOR = "=" * 60


def _print_header(title: str) -> None:
    """Print a formatted header."""
    print(SEPARATOR)
    print(title)
    print(SEPARATOR)


def _load_config(config_path: str | None) -> dict[str, object]:
    """Load configuration from file or defaults."""
    from src.config import load_config, load_proxy_sources  # noqa: PLC0415

    config = load_config(config_path)
    # Ensure sources are in config for build_sources()
    if "sources" not in config:
        config["sources"] = load_proxy_sources(config_path)
    return config


def _get_store(config: dict[str, object]) -> ProxyStore:
    """Get or create the proxy store."""
    from src.store import ProxyStore  # noqa: PLC0415

    db_path = str(config.get("db_path", "data/proxies.db"))
    store = ProxyStore(db_path)
    store.init_schema()
    return store


@app.command()
def collect(config_path: str | None = typer.Option(None, "--config", "-c")) -> None:
    """Collect proxies from all configured sources."""
    from src.collector import ProxyCollector  # noqa: PLC0415

    _print_header("Proxy Collector")
    config = _load_config(config_path)
    store = _get_store(config)

    collector = ProxyCollector(store, config)
    count = asyncio.run(collector.collect())
    print(f"\nCollected {count} proxies")


@app.command()
def validate(
    config_path: str | None = typer.Option(None, "--config", "-c"),
    include_failed: bool = typer.Option(
        False, "--include-failed", help="Also retry proxies that were previously verified dead"
    ),
) -> None:
    """Validate unvalidated proxies in the store."""
    from src.validator import ProxyValidator  # noqa: PLC0415

    _print_header("Proxy Validator")
    config = _load_config(config_path)
    store = _get_store(config)

    unvalidated = store.get_unvalidated(include_failed=include_failed)
    print(f"Unvalidated proxies: {len(unvalidated)}")

    if not unvalidated:
        print("Nothing to validate")
        return

    max_conc = int(config.get("max_concurrency", 50))  # type: ignore[arg-type]
    validator = ProxyValidator(config, store)
    valid = asyncio.run(validator.validate_all(unvalidated, max_conc))
    print(f"Valid proxies: {len(valid)}")


@app.command(name="all")
def all_cmd(
    config_path: str | None = typer.Option(None, "--config", "-c"),
    include_failed: bool = typer.Option(
        False, "--include-failed", help="Also retry proxies that were previously verified dead"
    ),
) -> None:
    """Collect and then validate all proxies."""
    from src.collector import ProxyCollector  # noqa: PLC0415
    from src.validator import ProxyValidator  # noqa: PLC0415

    _print_header("Proxy Pool — Full Cycle")
    config = _load_config(config_path)
    store = _get_store(config)

    print("Step 1: Collecting proxies...")
    collector = ProxyCollector(store, config)
    collected = asyncio.run(collector.collect())
    print(f"Collected {collected} proxies")

    print("\nStep 2: Validating proxies...")
    unvalidated = store.get_unvalidated(include_failed=include_failed)
    max_conc = int(config.get("max_concurrency", 50))  # type: ignore[arg-type]
    validator = ProxyValidator(config, store)
    valid = asyncio.run(validator.validate_all(unvalidated, max_conc))
    print(f"Valid proxies: {len(valid)}")

    counts = store.count()
    print(f"\nTotal in DB: {counts['total']}, Valid: {counts['valid']}")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", "-h"),
    port: int = typer.Option(8000, "--port", "-p"),
    config_path: str | None = typer.Option(None, "--config", "-c"),
) -> None:
    """Start the HTTP API service with auto-refresh."""
    import uvicorn  # noqa: PLC0415

    logging.basicConfig(level=logging.INFO)

    from src.api import create_app  # noqa: PLC0415

    _print_header("Proxy Pool Service")
    config = _load_config(config_path)
    store = _get_store(config)

    print(f"\nListening on {host}:{port}")
    print(f"DB: {config.get('db_path')}")
    print(f"Refresh interval: {config.get('refresh_interval_minutes')} minutes")

    uvicorn.run(create_app(store, config), host=host, port=port, log_level="info")


if __name__ == "__main__":
    app()
