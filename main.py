"""Proxy Pool Service — CLI and long-running daemon."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
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


def _auto_export(config: dict[str, object], store: ProxyStore) -> None:
    """Export validated proxies to disk after a validate/collect cycle.

    Defaults to the full usable list (fresh_only=False); freshness windows are
    an on-demand serving concern, not a manual-export concern.
    """
    from src.exporter import export_valid  # noqa: PLC0415

    out_dir = Path(str(config.get("db_path", "data/proxies.db"))).parent
    summary = export_valid(
        store,
        out_dir,
        expiry_hours=int(config.get("proxy_expiry_hours", 6)),  # type: ignore[arg-type]
        fresh_only=False,
    )
    if summary["total"]:  # type: ignore[attr-defined]
        print(f"\nExported {summary['total']} valid proxies to {out_dir}")  # type: ignore[attr-defined]


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
    quick_probe: bool = typer.Option(
        True, "--quick-probe/--no-quick-probe", help="Fast short-timeout probe first; only re-verify survivors fully"
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

    max_conc = int(config.get("max_concurrency", 100))  # type: ignore[arg-type]
    validator = ProxyValidator(config, store)
    valid = asyncio.run(validator.validate_all(unvalidated, max_conc, quick_probe=quick_probe))
    print(f"Valid proxies: {len(valid)}")
    _auto_export(config, store)


@app.command(name="all")
def all_cmd(
    config_path: str | None = typer.Option(None, "--config", "-c"),
    include_failed: bool = typer.Option(
        False, "--include-failed", help="Also retry proxies that were previously verified dead"
    ),
    quick_probe: bool = typer.Option(
        True, "--quick-probe/--no-quick-probe", help="Fast short-timeout probe first; only re-verify survivors fully"
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
    max_conc = int(config.get("max_concurrency", 100))  # type: ignore[arg-type]
    validator = ProxyValidator(config, store)
    valid = asyncio.run(validator.validate_all(unvalidated, max_conc, quick_probe=quick_probe))
    print(f"Valid proxies: {len(valid)}")
    _auto_export(config, store)

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


@app.command()
def diagnose(
    config_path: str | None = typer.Option(None, "--config", "-c"),
    sample: int = typer.Option(5, "--sample", "-n", help="How many sample proxies to probe"),
) -> None:
    """Check endpoint reachability and probe sample proxies verbosely."""
    from src.diagnostics import diagnose as run_diagnose  # noqa: PLC0415
    from src.validator import ProxyValidator  # noqa: PLC0415

    _print_header("Proxy Pool — Diagnostics")
    config = _load_config(config_path)
    store = _get_store(config)
    validator = ProxyValidator(config, store)
    asyncio.run(run_diagnose(store, validator, config, sample))


@app.command()
def export(
    config_path: str | None = typer.Option(None, "--config", "-c"),
    dir_path: str | None = typer.Option(None, "--dir", "-d", help="Output directory (default: alongside db)"),
    fresh_only: bool = typer.Option(
        False, "--fresh/--all", help="--fresh = only recently verified; --all (default) = every valid proxy"
    ),
) -> None:
    """Export validated proxies from the DB to data/ as JSON and text."""
    from src.exporter import export_valid  # noqa: PLC0415

    _print_header("Proxy Pool — Export")
    config = _load_config(config_path)
    store = _get_store(config)
    out_dir = dir_path or str(Path(str(config.get("db_path", "data/proxies.db"))).parent)
    summary = export_valid(
        store,
        out_dir,
        expiry_hours=int(config.get("proxy_expiry_hours", 6)),  # type: ignore[arg-type]
        fresh_only=fresh_only,
    )
    total = summary["total"]
    print(f"Exported {total} valid proxies to {out_dir}")
    for f in summary.get("files", []):  # type: ignore[attr-defined]
        print(f"  - {f}")


if __name__ == "__main__":
    app()
