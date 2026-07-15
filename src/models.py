"""Proxy data models and value objects."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class ProxyProtocol(StrEnum):
    """Supported proxy protocols."""

    HTTP = "http"
    HTTPS = "https"
    SOCKS4 = "socks4"
    SOCKS5 = "socks5"


class Anonymity(StrEnum):
    """Proxy anonymity levels."""

    TRANSPARENT = "transparent"
    ANONYMOUS = "anonymous"
    ELITE = "elite"


@dataclass(frozen=True, slots=True)
class ProxyRecord:
    """Immutable proxy record value object."""

    ip: str
    port: int
    protocol: ProxyProtocol
    source: str
    country: str = ""
    anonymity: Anonymity = Anonymity.TRANSPARENT
    response_time: float = 0.0
    last_verified: str = ""
    is_valid: bool = False

    @property
    def address(self) -> str:
        """Full proxy URL like http://1.2.3.4:8080."""
        return f"{self.protocol}://{self.ip}:{self.port}"

    @property
    def key(self) -> str:
        """Dedup key: ip:port:protocol."""
        return f"{self.ip}:{self.port}:{self.protocol}"

    def to_dict(self) -> dict[str, object]:
        """Serialize to a plain dict for JSON responses."""
        return {
            "ip": self.ip,
            "port": self.port,
            "protocol": self.protocol.value,
            "source": self.source,
            "country": self.country,
            "anonymity": self.anonymity.value,
            "response_time": self.response_time,
            "last_verified": self.last_verified,
            "is_valid": self.is_valid,
            "address": self.address,
        }

    @classmethod
    def from_line(
        cls,
        line: str,
        protocol: ProxyProtocol,
        source: str,
    ) -> ProxyRecord | None:
        """Parse an ``ip:port`` line into a ProxyRecord.

        Returns None for blank / comment / malformed lines (never raises).
        """
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            return None

        match = re.match(r"^(\d+\.\d+\.\d+\.\d+):(\d+)$", stripped)
        if match is None:
            return None

        ip = match.group(1)
        port = int(match.group(2))

        # Validate octets
        for octet in ip.split("."):
            if not 0 <= int(octet) <= 255:
                return None

        if not 1 <= port <= 65535:
            return None

        return cls(ip=ip, port=port, protocol=protocol, source=source)


@dataclass(frozen=True, slots=True)
class SourceFetchError(Exception):
    """Raised when a proxy source cannot be fetched."""

    source: str
    reason: str

    def __str__(self) -> str:
        """Return human-readable error message."""
        return f"Failed to fetch source '{self.source}': {self.reason}"
