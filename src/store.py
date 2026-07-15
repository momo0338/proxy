"""SQLite-backed proxy storage."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from src.models import Anonymity, ProxyProtocol, ProxyRecord

if TYPE_CHECKING:
    from collections.abc import Iterator

_SCHEMA = """
CREATE TABLE IF NOT EXISTS proxies(
    key         TEXT PRIMARY KEY,
    ip          TEXT    NOT NULL,
    port        INTEGER NOT NULL,
    protocol    TEXT    NOT NULL,
    source      TEXT    NOT NULL DEFAULT '',
    country     TEXT    NOT NULL DEFAULT '',
    anonymity   TEXT    NOT NULL DEFAULT 'transparent',
    response_time REAL  NOT NULL DEFAULT 0.0,
    last_verified TEXT NOT NULL DEFAULT '',
    is_valid    INTEGER NOT NULL DEFAULT 0
);
"""


class ProxyStore:
    """Thin wrapper around SQLite for proxy persistence."""

    def __init__(self, db_path: str) -> None:
        """Initialise store with the given database path."""
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Provide a transactional connection scope."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self) -> None:
        """Create the proxies table if it doesn't exist."""
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def upsert(self, record: ProxyRecord) -> None:
        """Insert or replace a single proxy record."""
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO proxies
                   (key, ip, port, protocol, source, country, anonymity,
                    response_time, last_verified, is_valid)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.key,
                    record.ip,
                    record.port,
                    record.protocol.value,
                    record.source,
                    record.country,
                    record.anonymity.value,
                    record.response_time,
                    record.last_verified,
                    int(record.is_valid),
                ),
            )

    def save_many(self, records: list[ProxyRecord]) -> None:
        """Batch upsert many records."""
        with self._connect() as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO proxies
                   (key, ip, port, protocol, source, country, anonymity,
                    response_time, last_verified, is_valid)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        r.key,
                        r.ip,
                        r.port,
                        r.protocol.value,
                        r.source,
                        r.country,
                        r.anonymity.value,
                        r.response_time,
                        r.last_verified,
                        int(r.is_valid),
                    )
                    for r in records
                ],
            )

    def record_validation(  # noqa: PLR0913
        self,
        key: str,
        *,
        is_valid: bool,
        response_time: float,
        anonymity: Anonymity,
        country: str,
        last_verified: str,
    ) -> None:
        """Update validation result for an existing record by key."""
        with self._connect() as conn:
            conn.execute(
                """UPDATE proxies
                   SET is_valid = ?, response_time = ?, anonymity = ?,
                       country = ?, last_verified = ?
                   WHERE key = ?""",
                (
                    int(is_valid),
                    response_time,
                    anonymity.value,
                    country,
                    last_verified,
                    key,
                ),
            )

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> ProxyRecord:
        """Convert a database row to a ProxyRecord."""
        return ProxyRecord(
            ip=row["ip"],
            port=row["port"],
            protocol=ProxyProtocol(row["protocol"]),
            source=row["source"],
            country=row["country"],
            anonymity=Anonymity(row["anonymity"]),
            response_time=row["response_time"],
            last_verified=row["last_verified"],
            is_valid=bool(row["is_valid"]),
        )

    def get_valid(  # noqa: PLR0913
        self,
        *,
        protocol: ProxyProtocol | None = None,
        anonymity: Anonymity | None = None,
        country: str | None = None,
        limit: int | None = None,
        only_fresh: bool = True,
        expiry_hours: int = 6,
    ) -> list[ProxyRecord]:
        """Return valid proxies, optionally filtered."""
        clauses: list[str] = ["is_valid = 1"]
        params: list[object] = []

        if only_fresh:
            cutoff = (datetime.now(UTC) - timedelta(hours=expiry_hours)).isoformat()
            clauses.append("last_verified >= ?")
            params.append(cutoff)

        if protocol is not None:
            clauses.append("protocol = ?")
            params.append(protocol.value)

        if anonymity is not None:
            clauses.append("anonymity = ?")
            params.append(anonymity.value)

        if country is not None:
            clauses.append("country = ?")
            params.append(country)

        where = " AND ".join(clauses)
        sql = f"SELECT * FROM proxies WHERE {where} ORDER BY response_time ASC"  # noqa: S608
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_record(row) for row in rows]

    def random_valid(
        self,
        *,
        protocol: ProxyProtocol | None = None,
        anonymity: Anonymity | None = None,
        country: str | None = None,
    ) -> ProxyRecord | None:
        """Return a single random valid proxy."""
        clauses: list[str] = ["is_valid = 1"]
        params: list[object] = []

        if protocol is not None:
            clauses.append("protocol = ?")
            params.append(protocol.value)
        if anonymity is not None:
            clauses.append("anonymity = ?")
            params.append(anonymity.value)
        if country is not None:
            clauses.append("country = ?")
            params.append(country)

        where = " AND ".join(clauses)
        sql = f"SELECT * FROM proxies WHERE {where} ORDER BY RANDOM() LIMIT 1"  # noqa: S608

        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return self._row_to_record(row) if row else None

    def get_unvalidated(self, *, include_failed: bool = False) -> list[ProxyRecord]:
        """Return unvalidated proxies.

        By default only returns proxies that have never been tested
        (is_valid = 0 AND last_verified = ''). Pass include_failed=True to also
        return proxies that were previously tested and found dead, so they can
        be retried (e.g. after a source re-collects them).
        """
        if include_failed:
            sql = "SELECT * FROM proxies WHERE is_valid = 0"
        else:
            sql = "SELECT * FROM proxies WHERE is_valid = 0 AND last_verified = ''"
        with self._connect() as conn:
            rows = conn.execute(sql).fetchall()
        return [self._row_to_record(row) for row in rows]

    def count_unvalidated(self, *, include_failed: bool = False) -> int:
        """Count unvalidated proxies without materialising rows."""
        if include_failed:
            sql = "SELECT COUNT(*) FROM proxies WHERE is_valid = 0"
        else:
            sql = "SELECT COUNT(*) FROM proxies WHERE is_valid = 0 AND last_verified = ''"
        with self._connect() as conn:
            row = conn.execute(sql).fetchone()
        return row[0] if row else 0

    def count(self) -> dict[str, int]:
        """Aggregate counts: total, valid, and per protocol."""
        with self._connect() as conn:
            total_row = conn.execute("SELECT COUNT(*) FROM proxies").fetchone()
            total: int = total_row[0] if total_row else 0
            valid_row = conn.execute(
                "SELECT COUNT(*) FROM proxies WHERE is_valid = 1"
            ).fetchone()
            valid: int = valid_row[0] if valid_row else 0
            rows = conn.execute(
                "SELECT protocol, COUNT(*) as cnt FROM proxies GROUP BY protocol"
            ).fetchall()

        by_protocol: dict[str, int] = {row["protocol"]: row["cnt"] for row in rows}  # type: ignore[index]
        return {"total": total, "valid": valid, "by_protocol": by_protocol}

    def delete_expired(self, expiry_hours: int) -> int:
        """Delete valid proxies older than expiry_hours. Returns count deleted."""
        cutoff = (datetime.now(UTC) - timedelta(hours=expiry_hours)).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM proxies WHERE is_valid = 1 AND last_verified < ?",
                (cutoff,),
            )
            return cursor.rowcount
