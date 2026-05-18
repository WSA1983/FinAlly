"""Tests for the WatchlistRepo SQLite module."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.db import WatchlistRepo
from app.db.watchlist import SEED_TICKERS


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Per-test isolated SQLite file path."""
    return tmp_path / "test_finally.db"


def test_lazy_init_creates_table_and_file(db_path: Path) -> None:
    assert not db_path.exists()
    repo = WatchlistRepo(db_path)
    # First operation triggers lazy init.
    tickers = repo.list_tickers()
    assert db_path.exists()

    # Table exists in the new DB file.
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='watchlist'"
        ).fetchone()
        assert row is not None
    finally:
        conn.close()

    # Seed data is present on a fresh DB.
    assert sorted(SEED_TICKERS) == tickers


def test_seed_only_runs_on_empty_db(db_path: Path) -> None:
    # First instance seeds the DB.
    repo1 = WatchlistRepo(db_path)
    repo1.list_tickers()
    repo1.remove("AAPL")
    after_first = repo1.list_tickers()
    assert "AAPL" not in after_first

    # Fresh instance must NOT reseed — it should respect the existing state.
    repo2 = WatchlistRepo(db_path)
    assert repo2.list_tickers() == after_first


def test_list_tickers_is_alphabetical(db_path: Path) -> None:
    repo = WatchlistRepo(db_path)
    # Clear seed and insert in non-alpha order.
    for t in list(SEED_TICKERS):
        repo.remove(t)
    repo.add("ZZZ")
    repo.add("AAA")
    repo.add("MMM")
    assert repo.list_tickers() == ["AAA", "MMM", "ZZZ"]


def test_add_returns_true_then_false_for_duplicate(db_path: Path) -> None:
    repo = WatchlistRepo(db_path)
    assert repo.add("PYPL") is True
    assert repo.add("PYPL") is False
    # Lowercase input still treated as duplicate (uppercased).
    assert repo.add("pypl") is False


def test_add_uppercases_ticker(db_path: Path) -> None:
    repo = WatchlistRepo(db_path)
    assert repo.add("ibm") is True
    assert "IBM" in repo.list_tickers()


def test_remove_returns_true_when_present_false_otherwise(db_path: Path) -> None:
    repo = WatchlistRepo(db_path)
    # AAPL is in the seed set.
    assert repo.remove("AAPL") is True
    assert "AAPL" not in repo.list_tickers()
    # Removing again returns False.
    assert repo.remove("AAPL") is False
    # Unknown ticker returns False.
    assert repo.remove("NOPE") is False


def test_remove_is_case_insensitive(db_path: Path) -> None:
    repo = WatchlistRepo(db_path)
    assert repo.remove("googl") is True
    assert "GOOGL" not in repo.list_tickers()


def test_db_path_env_var_overrides_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    custom = tmp_path / "custom.db"
    monkeypatch.setenv("DB_PATH", str(custom))
    repo = WatchlistRepo()  # No explicit path -> reads env.
    repo.list_tickers()
    assert custom.exists()


def test_parent_directory_created_if_missing(tmp_path: Path) -> None:
    nested = tmp_path / "nested" / "dir" / "finally.db"
    repo = WatchlistRepo(nested)
    repo.list_tickers()
    assert nested.exists()
