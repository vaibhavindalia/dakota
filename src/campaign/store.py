"""Privacy-preserving tip/campaign store.

Only ticker, timestamp, fingerprint and coarse source label are persisted.
Raw tip text is never stored by this module.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.tipcheck.privacy import fingerprint


class TipStore:
    def __init__(self, path: str | Path = "data/dakota.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tip_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    ts TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    source_label TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tip_ticker_ts ON tip_events(ticker, ts)"
            )
            conn.commit()

    def add(self, ticker: str, clean_text: str, source_label: str) -> dict[str, Any]:
        fp = fingerprint(clean_text)
        ts = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO tip_events (ticker, ts, fingerprint, source_label) VALUES (?, ?, ?, ?)",
                (ticker.upper().strip(), ts, fp, source_label[:64]),
            )
            conn.commit()
        return {"ticker": ticker.upper().strip(), "ts": ts, "fingerprint": fp, "source_label": source_label[:64]}

    def recent(self, ticker: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT ticker, ts, fingerprint, source_label FROM tip_events WHERE ticker = ? ORDER BY id DESC LIMIT ?",
                (ticker.upper().strip(), int(limit)),
            ).fetchall()
        return [dict(row) for row in rows]

    def fingerprint_count(self, ticker: str, fp: str, limit: int = 100) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM tip_events WHERE ticker = ? AND fingerprint = ?",
                (ticker.upper().strip(), fp),
            ).fetchone()
        return int(row["c"] if row else 0)
