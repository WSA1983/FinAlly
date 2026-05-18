"""Tests for the watchlist API and core FastAPI app wiring."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.db import WatchlistRepo


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Build a TestClient with an isolated SQLite file and a stubbed market source.

    We patch the market data source factory so tests don't spin up the GBM
    simulator background task.
    """
    db_file = tmp_path / "test_finally.db"
    monkeypatch.setenv("DB_PATH", str(db_file))

    # Stub the market data source so start/stop/add/remove are no-ops.
    fake_source = MagicMock()
    fake_source.start = AsyncMock()
    fake_source.stop = AsyncMock()
    fake_source.add_ticker = AsyncMock()
    fake_source.remove_ticker = AsyncMock()

    import app.main as main_module

    monkeypatch.setattr(main_module, "create_market_data_source", lambda cache: fake_source)

    # Build a fresh app after env + monkeypatches are in place.
    app = main_module.create_app()
    # Expose the fake source so tests can assert call counts.
    app.state._fake_source = fake_source

    with TestClient(app) as c:
        yield c


def test_health_endpoint(client: TestClient) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_get_watchlist_returns_seeded_tickers(client: TestClient) -> None:
    resp = client.get("/api/watchlist")
    assert resp.status_code == 200
    body = resp.json()
    assert "tickers" in body
    # WatchlistRepo seeds with AAPL, GOOGL, MSFT, TSLA, NVDA on empty DB.
    assert set(body["tickers"]) == {"AAPL", "GOOGL", "MSFT", "TSLA", "NVDA"}
    # Alphabetical ordering
    assert body["tickers"] == sorted(body["tickers"])


def test_post_watchlist_adds_ticker(client: TestClient) -> None:
    resp = client.post("/api/watchlist", json={"ticker": "amzn"})
    assert resp.status_code == 201
    assert resp.json() == {"ticker": "AMZN"}

    # It should now appear in GET.
    listed = client.get("/api/watchlist").json()["tickers"]
    assert "AMZN" in listed

    # The market source should have been told to start streaming it.
    fake_source = client.app.state._fake_source
    fake_source.add_ticker.assert_awaited_with("AMZN")


def test_post_watchlist_duplicate_returns_400(client: TestClient) -> None:
    # AAPL is in the seeded set.
    resp = client.post("/api/watchlist", json={"ticker": "AAPL"})
    assert resp.status_code == 400
    assert "already" in resp.json()["detail"].lower()


def test_post_watchlist_empty_ticker_returns_400(client: TestClient) -> None:
    resp = client.post("/api/watchlist", json={"ticker": "   "})
    assert resp.status_code == 400


def test_delete_watchlist_removes_ticker(client: TestClient) -> None:
    resp = client.delete("/api/watchlist/AAPL")
    assert resp.status_code == 204

    listed = client.get("/api/watchlist").json()["tickers"]
    assert "AAPL" not in listed

    fake_source = client.app.state._fake_source
    fake_source.remove_ticker.assert_awaited_with("AAPL")


def test_delete_watchlist_missing_returns_404(client: TestClient) -> None:
    resp = client.delete("/api/watchlist/ZZZZ")
    assert resp.status_code == 404


def test_delete_watchlist_lowercase_normalizes(client: TestClient) -> None:
    resp = client.delete("/api/watchlist/aapl")
    assert resp.status_code == 204


def test_watchlist_repo_isolated_per_test(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sanity check: the DB_PATH env var produces an isolated DB."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "iso.db"))
    repo = WatchlistRepo()
    tickers = repo.list_tickers()
    assert "AAPL" in tickers
