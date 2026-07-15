"""Proxy source fetching from remote text lists."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

from src.config import parse_protocol
from src.models import ProxyProtocol, ProxyRecord, SourceFetchError


class ProxySource(Protocol):
    """Protocol for anything that can fetch proxy records."""

    name: str

    def fetch(self) -> list[ProxyRecord]:  # pragma: no cover
        """Fetch and parse proxies from this source."""
        ...


@dataclass(frozen=True, slots=True)
class TextSource:
    """Fetches a plain-text ip:port list from a URL."""

    name: str
    url: str
    protocol: ProxyProtocol
    format: str = "ip:port"
    timeout: float = 30.0

    def fetch(self) -> list[ProxyRecord]:
        """HTTP GET the URL, parse each line as ip:port."""
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                resp = client.get(self.url)
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise SourceFetchError(source=self.name, reason=str(exc)) from exc

        records: list[ProxyRecord] = []
        for line in resp.text.splitlines():
            record = ProxyRecord.from_line(line, self.protocol, self.name)
            if record is not None:
                records.append(record)
        return records


def build_sources(config: dict[str, object]) -> list[TextSource]:
    """Build TextSource list from a config dict's ``sources`` key."""
    raw = config.get("sources", [])
    if not isinstance(raw, list):
        return []

    timeout_val = config.get("timeout", 30)
    timeout = float(timeout_val) if isinstance(timeout_val, (int, float)) else 30.0

    sources: list[TextSource] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        if not entry.get("enabled", True):
            continue
        name = str(entry.get("name", ""))
        url = str(entry.get("url", ""))
        proto_str = str(entry.get("protocol", "http"))
        fmt = str(entry.get("format", "ip:port"))

        if not name or not url:
            continue

        protocol = parse_protocol(proto_str)
        sources.append(
            TextSource(name=name, url=url, protocol=protocol, format=fmt, timeout=timeout)
        )
    return sources
