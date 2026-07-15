"""Tests for src.store — ProxyStore CRUD operations."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.models import Anonymity, ProxyProtocol, ProxyRecord
from src.store import ProxyStore


@pytest.fixture()
def store() -> ProxyStore:
    """Create a temporary ProxyStore for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")
        s = ProxyStore(db_path)
        s.init_schema()
        yield s


@pytest.fixture()
def sample_record() -> ProxyRecord:
    """Return a sample valid proxy record."""
    return ProxyRecord(
        ip="1.2.3.4",
        port=8080,
        protocol=ProxyProtocol.HTTP,
        source="test-source",
        country="US",
        anonymity=Anonymity.ELITE,
        response_time=0.5,
        last_verified=datetime.now(UTC).isoformat(),
        is_valid=True,
    )


@pytest.fixture()
def sample_invalid_record() -> ProxyRecord:
    """Return a sample unvalidated proxy record."""
    return ProxyRecord(
        ip="5.6.7.8",
        port=3128,
        protocol=ProxyProtocol.SOCKS5,
        source="test-source",
        is_valid=False,
        last_verified="",
    )


class TestProxyStoreUpsert:
    """Tests for upsert and save_many."""

    def test_upsert_single(self, store: ProxyStore, sample_record: ProxyRecord) -> None:
        store.upsert(sample_record)
        records = store.get_valid(only_fresh=False)
        assert len(records) == 1
        assert records[0].ip == "1.2.3.4"

    def test_upsert_replaces(self, store: ProxyStore, sample_record: ProxyRecord) -> None:
        store.upsert(sample_record)
        updated = ProxyRecord(
            ip="1.2.3.4",
            port=8080,
            protocol=ProxyProtocol.HTTP,
            source="test-source",
            response_time=1.0,
            is_valid=True,
            last_verified=datetime.now(UTC).isoformat(),
        )
        store.upsert(updated)
        records = store.get_valid(only_fresh=False)
        assert len(records) == 1
        assert records[0].response_time == 1.0

    def test_save_many(self, store: ProxyStore) -> None:
        records = [
            ProxyRecord(ip=f"10.0.0.{i}", port=8080, protocol=ProxyProtocol.HTTP, source="t")
            for i in range(5)
        ]
        store.save_many(records)
        counts = store.count()
        assert counts["total"] == 5


class TestProxyStoreGetValid:
    """Tests for get_valid queries."""

    def test_get_valid_only_valid(self, store: ProxyStore, sample_record: ProxyRecord) -> None:
        store.upsert(sample_record)
        invalid = ProxyRecord(
            ip="9.9.9.9", port=80, protocol=ProxyProtocol.HTTP, source="t", is_valid=False
        )
        store.upsert(invalid)
        valid = store.get_valid(only_fresh=False)
        assert len(valid) == 1
        assert valid[0].ip == "1.2.3.4"

    def test_get_valid_filter_protocol(
        self, store: ProxyStore, sample_record: ProxyRecord
    ) -> None:
        store.upsert(sample_record)
        socks = ProxyRecord(
            ip="2.2.2.2",
            port=1080,
            protocol=ProxyProtocol.SOCKS5,
            source="t",
            is_valid=True,
            last_verified=datetime.now(UTC).isoformat(),
        )
        store.upsert(socks)
        http_only = store.get_valid(protocol=ProxyProtocol.HTTP, only_fresh=False)
        assert len(http_only) == 1
        assert http_only[0].protocol == ProxyProtocol.HTTP

    def test_get_valid_limit(self, store: ProxyStore) -> None:
        for i in range(10):
            store.upsert(
                ProxyRecord(
                    ip=f"10.0.0.{i}",
                    port=8080,
                    protocol=ProxyProtocol.HTTP,
                    source="t",
                    is_valid=True,
                    last_verified=datetime.now(UTC).isoformat(),
                )
            )
        limited = store.get_valid(limit=3, only_fresh=False)
        assert len(limited) == 3

    def test_get_valid_fresh_only(self, store: ProxyStore) -> None:
        old = ProxyRecord(
            ip="1.1.1.1",
            port=80,
            protocol=ProxyProtocol.HTTP,
            source="t",
            is_valid=True,
            last_verified=(datetime.now(UTC) - timedelta(hours=10)).isoformat(),
        )
        fresh = ProxyRecord(
            ip="2.2.2.2",
            port=80,
            protocol=ProxyProtocol.HTTP,
            source="t",
            is_valid=True,
            last_verified=datetime.now(UTC).isoformat(),
        )
        store.upsert(old)
        store.upsert(fresh)
        result = store.get_valid(only_fresh=True, expiry_hours=6)
        assert len(result) == 1
        assert result[0].ip == "2.2.2.2"


class TestProxyStoreRandomValid:
    """Tests for random_valid."""

    def test_random_valid_returns_record(
        self, store: ProxyStore, sample_record: ProxyRecord
    ) -> None:
        store.upsert(sample_record)
        rec = store.random_valid()
        assert rec is not None
        assert rec.ip == "1.2.3.4"

    def test_random_valid_none_when_empty(self, store: ProxyStore) -> None:
        assert store.random_valid() is None


class TestProxyStoreDeleteExpired:
    """Tests for delete_expired."""

    def test_delete_expired(self, store: ProxyStore) -> None:
        old = ProxyRecord(
            ip="1.1.1.1", port=80, protocol=ProxyProtocol.HTTP, source="t",
            is_valid=True, last_verified=(datetime.now(UTC) - timedelta(hours=10)).isoformat(),
        )
        fresh = ProxyRecord(
            ip="2.2.2.2", port=80, protocol=ProxyProtocol.HTTP, source="t",
            is_valid=True, last_verified=datetime.now(UTC).isoformat(),
        )
        store.upsert(old)
        store.upsert(fresh)
        deleted = store.delete_expired(6)
        assert deleted == 1
        remaining = store.get_valid(only_fresh=False)
        assert len(remaining) == 1

    def test_delete_expired_no_valid(self, store: ProxyStore) -> None:
        inv = ProxyRecord(
            ip="1.1.1.1", port=80, protocol=ProxyProtocol.HTTP, source="t", is_valid=False
        )
        store.upsert(inv)
        deleted = store.delete_expired(6)
        assert deleted == 0


class TestProxyStoreCount:
    """Tests for count."""

    def test_count_empty(self, store: ProxyStore) -> None:
        counts = store.count()
        assert counts["total"] == 0
        assert counts["valid"] == 0
        assert counts["by_protocol"] == {}

    def test_count_mixed(self, store: ProxyStore) -> None:
        store.upsert(ProxyRecord(
            ip="1.1.1.1", port=80, protocol=ProxyProtocol.HTTP, source="t",
            is_valid=True, last_verified=datetime.now(UTC).isoformat(),
        ))
        store.upsert(ProxyRecord(
            ip="2.2.2.2", port=1080, protocol=ProxyProtocol.SOCKS5, source="t", is_valid=False,
        ))
        counts = store.count()
        assert counts["total"] == 2
        assert counts["valid"] == 1
        assert counts["by_protocol"]["http"] == 1
        assert counts["by_protocol"]["socks5"] == 1


class TestProxyStoreRecordValidation:
    """Tests for record_validation."""

    def test_record_validation(self, store: ProxyStore, sample_invalid_record: ProxyRecord) -> None:
        store.upsert(sample_invalid_record)
        now = datetime.now(UTC).isoformat()
        store.record_validation(
            sample_invalid_record.key,
            is_valid=True,
            response_time=0.3,
            anonymity=Anonymity.ANONYMOUS,
            country="DE",
            last_verified=now,
        )
        valid = store.get_valid(only_fresh=False)
        assert len(valid) == 1
        assert valid[0].is_valid is True
        assert valid[0].country == "DE"
        assert valid[0].response_time == 0.3


class TestProxyStoreUnvalidated:
    def test_get_unvalidated_skips_tested_dead(
        self, store: ProxyStore
    ) -> None:
        never_tested = ProxyRecord(
            ip="1.1.1.1", port=80, protocol=ProxyProtocol.HTTP, source="t", is_valid=False
        )
        store.upsert(never_tested)
        dead = ProxyRecord(
            ip="2.2.2.2", port=80, protocol=ProxyProtocol.HTTP, source="t",
            is_valid=False, last_verified=datetime.now(UTC).isoformat(),
        )
        store.upsert(dead)

        assert len(store.get_unvalidated()) == 1
        assert store.get_unvalidated()[0].ip == "1.1.1.1"
        assert len(store.get_unvalidated(include_failed=True)) == 2

    def test_count_unvalidated(self, store: ProxyStore) -> None:
        store.upsert(ProxyRecord(
            ip="1.1.1.1", port=80, protocol=ProxyProtocol.HTTP, source="t", is_valid=False
        ))
        store.upsert(ProxyRecord(
            ip="2.2.2.2", port=80, protocol=ProxyProtocol.HTTP, source="t",
            is_valid=False, last_verified=datetime.now(UTC).isoformat(),
        ))
        assert store.count_unvalidated() == 1
        assert store.count_unvalidated(include_failed=True) == 2
