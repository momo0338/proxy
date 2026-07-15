"""Tests for src.api — FastAPI routes."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api import create_app
from src.config import DEFAULT_CONFIG
from src.models import Anonymity, ProxyProtocol, ProxyRecord
from src.store import ProxyStore


@pytest.fixture()
def client() -> TestClient:
    """Create a test client with a temporary store."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")
        store = ProxyStore(db_path)
        store.init_schema()

        config = dict(DEFAULT_CONFIG)
        config["db_path"] = db_path
        config["refresh_on_startup"] = False

        app = create_app(store, config)
        yield TestClient(app)


@pytest.fixture()
def populated_client() -> TestClient:
    """Create a test client pre-populated with proxy data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")
        store = ProxyStore(db_path)
        store.init_schema()

        # Add some valid proxies
        for i in range(3):
            store.upsert(
                ProxyRecord(
                    ip=f"10.0.0.{i}",
                    port=8080,
                    protocol=ProxyProtocol.HTTP,
                    source="test",
                    country="US",
                    anonymity=Anonymity.ELITE,
                    response_time=0.5,
                    last_verified=datetime.now(UTC).isoformat(),
                    is_valid=True,
                )
            )

        config = dict(DEFAULT_CONFIG)
        config["db_path"] = db_path
        config["refresh_on_startup"] = False

        app = create_app(store, config)
        yield TestClient(app)


class TestHealthEndpoint:
    """Tests for GET /health."""

    def test_health_ok(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["total"] == 0
        assert data["valid"] == 0

    def test_health_with_data(self, populated_client: TestClient) -> None:
        resp = populated_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert data["valid"] == 3


class TestMetricsEndpoint:
    """Tests for GET /metrics."""

    def test_metrics_empty(self, client: TestClient) -> None:
        resp = client.get("/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["by_protocol"] == {}

    def test_metrics_with_data(self, populated_client: TestClient) -> None:
        resp = populated_client.get("/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert data["by_protocol"]["http"] == 3


class TestProxiesEndpoint:
    """Tests for GET /proxies."""

    def test_proxies_empty(self, client: TestClient) -> None:
        resp = client.get("/proxies")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_proxies_with_data(self, populated_client: TestClient) -> None:
        resp = populated_client.get("/proxies")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        assert data[0]["ip"] == "10.0.0.0"
        assert data[0]["protocol"] == "http"

    def test_proxies_filter_protocol(self, populated_client: TestClient) -> None:
        resp = populated_client.get("/proxies?protocol=socks5")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_proxies_limit(self, populated_client: TestClient) -> None:
        resp = populated_client.get("/proxies?limit=1")
        assert resp.status_code == 200
        assert len(resp.json()) == 1


class TestRandomProxyEndpoint:
    """Tests for GET /proxy/random."""

    def test_random_empty(self, client: TestClient) -> None:
        resp = client.get("/proxy/random")
        assert resp.status_code == 404

    def test_random_with_data(self, populated_client: TestClient) -> None:
        resp = populated_client.get("/proxy/random")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ip"].startswith("10.0.0.")


class TestRefreshEndpoint:
    """Tests for POST /refresh."""

    def test_refresh_accepted(self, client: TestClient) -> None:
        resp = client.post("/refresh")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"
