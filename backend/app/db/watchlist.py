"""SQLite-backed watchlist repository.

Single-table watchlist storage with lazy initialization. The DB file and table
are created on first use; the table is seeded with a small default set of
tickers only if it is empty.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# Seed tickers used only when the watchlist table is empty on first init.
SEED_TICKERS: tuple[str, ...] = ("AAPL", "GOOGL", "MSFT", "TSLA", "NVDA")

# Default DB path: <project_root>/db/finally.db
# This file lives at backend/app/db/watchlist.py, so parents[3] is the project root.
_DEFAULT_DB_PATH = Path(__file__).resolve().parents[3] / "db" / "finally.db"


def _resolve_db_path() -> Path:
    """Return the configured DB path, honoring the DB_PATH env var."""
    env = os.environ.get("DB_PATH")
    if env:
        return Path(env)
    return _DEFAULT_DB_PATH


class WatchlistRepo:
    """Synchronous SQLite-backed watchlist repository.

    Connection-per-call: each operation opens, executes, and closes its own
    connection. This is fine for the demo's low write volume.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            self._db_path = _resolve_db_path()
        else:
            self._db_path = Path(db_path)
        self._initialized = False

    # ---- internal helpers ---------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        self._ensure_initialized()
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_initialized(self) -> None:
        """Lazily create the DB file, table, and seed data if needed."""
        if self._initialized:
            return

        # Ensure parent directory exists.
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS watchlist (
                    id INTEGER PRIMARY KEY,
                    ticker TEXT UNIQUE NOT NULL,
                    added_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

            # Seed only when the table is empty.
            cur = conn.execute("SELECT COUNT(*) FROM watchlist")
            (count,) = cur.fetchone()
            if count == 0:
                now = datetime.now(timezone.utc).isoformat()
                conn.executemany(
                    "INSERT INTO watchlist (ticker, added_at) VALUES (?, ?)",
                    [(t, now) for t in SEED_TICKERS],
                )
                conn.commit()
        finally:
            conn.close()

        self._initialized = True

    # ---- public API ---------------------------------------------------------

    def list_tickers(self) -> list[str]:
        """Return all tickers in alphabetical order."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT ticker FROM watchlist ORDER BY ticker ASC"
            ).fetchall()
            return [row["ticker"] for row in rows]
        finally:
            conn.close()

    def add(self, ticker: str) -> bool:
        """Add a ticker (uppercased). Returns True if added, False if already present."""
        normalized = ticker.strip().upper()
        if not normalized:
            return False
        conn = self._connect()
        try:
            now = datetime.now(timezone.utc).isoformat()
            try:
                conn.execute(
                    "INSERT INTO watchlist (ticker, added_at) VALUES (?, ?)",
                    (normalized, now),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                # UNIQUE constraint failed — already present.
                return False
        finally:
            conn.close()

    def remove(self, ticker: str) -> bool:
        """Remove a ticker (case-insensitive). Returns True if removed, False if not present."""
        normalized = ticker.strip().upper()
        if not normalized:
            return False
        conn = self._connect()
        try:
            cur = conn.execute(
                "DELETE FROM watchlist WHERE ticker = ?", (normalized,)
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()
