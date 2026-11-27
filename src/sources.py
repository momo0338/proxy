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


def split_line(line: str, default_protocol: ProxyProtocol) -> tuple[str, ProxyProtocol] | None:
    """Normalise one raw source line to (ip:port, protocol).

    Accepts three common public-list shapes:
      * "ip:port"            -> uses default_protocol
      * "scheme://ip:port"   -> protocol taken from the scheme (e.g. proxifly)
      * "ip:port:SCHEME"     -> protocol taken from the trailing token

    Returns None for blank / comment / unrecognised lines.
    """
    s = line.strip()
    if not s or s.startswith("#"):
        return None

    if "://" in s:
        scheme, _, rest = s.partition("://")
        try:
            proto = parse_protocol(scheme)
        except ValueError:
            return None
        return rest.strip(), proto

    # Trailing ":SCHEME" suffix, e.g. "1.2.3.4:80:HTTP".
    head, sep, tail = s.rpartition(":")
    if sep and tail and not tail.isdigit():
        try:
            proto = parse_protocol(tail)
        except ValueError:
            return None
        return head, proto

    return s, default_protocol


@dataclass(frozen=True, slots=True)
class TextSource:
    """Fetches a plain-text proxy list from a URL."""

    name: str
    url: str
    protocol: ProxyProtocol
    format: str = "ip:port"
    timeout: float = 30.0
    max_records: int = 0  # 0 = unlimited

    def fetch(self) -> list[ProxyRecord]:
        """HTTP GET the URL, parse each line into proxies (capped by max_records)."""
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                resp = client.get(self.url)
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise SourceFetchError(source=self.name, reason=str(exc)) from exc

        records: list[ProxyRecord] = []
        for line in resp.text.splitlines():
            parsed = split_line(line, self.protocol)
            if parsed is None:
                continue
            hostport, proto = parsed
            record = ProxyRecord.from_line(hostport, proto, self.name)
            if record is not None:
                records.append(record)
                if self.max_records > 0 and len(records) >= self.max_records:
                    break
        return records


def build_sources(config: dict[str, object]) -> list[TextSource]:
    """Build TextSource list from a config dict's sources key."""
    raw = config.get("sources", [])
    if not isinstance(raw, list):
        return []

    timeout_val = config.get("timeout", 30)
    timeout = float(timeout_val) if isinstance(timeout_val, (int, float)) else 30.0
    default_max_val = config.get("collect_per_source_default", 0)
    default_max = int(default_max_val) if isinstance(default_max_val, (int, float)) else 0

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
        max_val = entry.get("max", default_max)
        max_records = int(max_val) if isinstance(max_val, (int, float)) else default_max

        if not name or not url:
            continue

        protocol = parse_protocol(proto_str)
        sources.append(
            TextSource(
                name=name,
                url=url,
                protocol=protocol,
                format=fmt,
                timeout=timeout,
                max_records=max_records,
            )
        )
    return sources
