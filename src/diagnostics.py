"""Connectivity diagnostics for the validation pipeline.

Helps answer "why are 0 proxies valid?" by checking whether the
configured echo endpoints are even reachable from this machine, and by
probing a few sample proxies with the exact error each endpoint raises.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from src.store import ProxyStore
    from src.validator import ProxyValidator


async def _check_url(url: str, timeout_sec: float) -> tuple[bool, str]:
    """Return (reachable, detail) for a direct (no-proxy) GET."""
    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return True, f"HTTP {resp.status_code}"
    except httpx.HTTPError as exc:
        return False, f"{type(exc).__name__}: {exc}"
    except OSError as exc:
        return False, f"{type(exc).__name__}: {exc}"


async def diagnose(
    store: ProxyStore,
    validator: ProxyValidator,
    config: dict[str, object],
    sample: int = 5,
) -> None:
    """Print endpoint reachability and verbose sample-proxy probing."""
    timeout_val = config.get("verify_timeout", 8.0)
    timeout = float(timeout_val) if isinstance(timeout_val, (int, float)) else 8.0
    endpoints = validator._echo_endpoints()  # noqa: SLF001

    print("== Endpoint reachability (direct, no proxy) ==")
    for ep in endpoints:
        ok, detail = await _check_url(ep, timeout)
        print(f"  [{'OK ' if ok else 'FAIL'}] {ep} -> {detail}")

    print("\n== Sample proxy probing ==")
    records = store.get_unvalidated(include_failed=True)[:sample]
    if not records:
        print("  (no proxies to probe)")
        return
    for rec in records:
        proxy_url = validator._proxy_url(rec)  # noqa: SLF001
        print(f"\n  {rec.address}")
        async with httpx.AsyncClient(proxy=proxy_url, timeout=timeout) as client:
            for ep in endpoints:
                try:
                    resp = await client.get(ep)
                    resp.raise_for_status()
                    data = resp.json()
                    seen = str(data.get("ip") or data.get("origin") or "")
                    print(f"    [OK]   {ep} -> seen_ip={seen}")
                except httpx.HTTPError as exc:
                    print(f"    [FAIL] {ep} -> {type(exc).__name__}: {exc}")
                except (OSError, ValueError) as exc:
                    print(f"    [FAIL] {ep} -> {type(exc).__name__}: {exc}")
