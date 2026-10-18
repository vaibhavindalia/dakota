"""Seed and populate the SQLite stock database with 2,615 Indian stocks and precompute cached scores."""
from __future__ import annotations

import csv
import logging
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DB_PATH = BASE_DIR / "data" / "dakota.db"
NSE_CSV = BASE_DIR / "config" / "nse_universe.csv"
CACHE_DIR = BASE_DIR / "data" / "cache"


def init_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS stock_assessments (
        ticker TEXT PRIMARY KEY,
        name TEXT,
        exchange TEXT,
        segment TEXT,
        role TEXT,
        score REAL,
        band TEXT,
        verdict TEXT,
        latest_price REAL,
        change_pct REAL,
        high_52w REAL,
        low_52w REAL,
        volume INTEGER,
        is_surveillance INTEGER DEFAULT 0,
        status TEXT DEFAULT 'pending',
        updated_at TEXT
    );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_stock_segment ON stock_assessments(segment);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_stock_band ON stock_assessments(band);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_stock_status ON stock_assessments(status);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_stock_score ON stock_assessments(score DESC);")
    conn.commit()
    return conn


def seed_universe(conn: sqlite3.Connection) -> int:
    cur = conn.cursor()
    if not NSE_CSV.exists():
        logger.error("nse_universe.csv not found at %s", NSE_CSV)
        return 0

    with open(NSE_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    count = 0
    for r in rows:
        t = r["ticker"].upper().strip()
        is_surv = 1 if r.get("surveillance_flag") == "True" else 0
        cur.execute("""
        INSERT INTO stock_assessments (ticker, name, exchange, segment, role, is_surveillance, status)
        VALUES (?, ?, ?, ?, ?, ?, 'pending')
        ON CONFLICT(ticker) DO UPDATE SET
            name = excluded.name,
            exchange = excluded.exchange,
            segment = excluded.segment,
            role = excluded.role,
            is_surveillance = excluded.is_surveillance
        """, (
            t,
            r.get("name", ""),
            r.get("exchange", "NSE"),
            r.get("segment", "main"),
            r.get("role", "control"),
            is_surv,
        ))
        count += 1

    conn.commit()
    logger.info("Seeded %d stocks into stock_assessments table.", count)
    return count


def precompute_cached(conn: sqlite3.Connection) -> int:
    from src.engine.risk_engine import assess

    cur = conn.cursor()
    cached_tickers = [p.stem.replace("ohlcv_", "").upper() for p in CACHE_DIR.glob("ohlcv_*.parquet")]
    uni_tickers = []
    try:
        from src.ingest.market_data import load_universe
        uni_tickers = [t.upper() for t in load_universe().ticker]
    except Exception:
        pass

    target_tickers = list(dict.fromkeys(cached_tickers + uni_tickers + [
        "CLOUD", "VARANIUM", "ASRL", "ADDSHOP", "TRAFIKSOL", "AFCOM", "TATAPOWER", "RELIANCE", "CDSL", "IRCTC", "SUZLON"
    ]))
    logger.info("Found %d priority stock targets to assess and precompute...", len(target_tickers))

    start = time.time()
    updated = 0
    for ticker in target_tickers:
        try:
            risk = assess(ticker)
            score = risk.get("score")
            band = risk.get("band", "Unavailable")
            verdict = risk.get("verdict", "")
            cur.execute("""
            UPDATE stock_assessments SET
                score = ?,
                band = ?,
                verdict = ?,
                status = 'completed',
                updated_at = ?
            WHERE ticker = ?
            """, (score, band, verdict, datetime.utcnow().isoformat(), ticker))
            updated += 1
        except Exception as exc:
            logger.warning("Could not assess %s: %s", ticker, exc)

    conn.commit()
    logger.info("Precomputed and cached %d stock assessments in %.2fs", updated, time.time() - start)
    return updated


if __name__ == "__main__":
    conn = init_db()
    total = seed_universe(conn)
    cached = precompute_cached(conn)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM stock_assessments WHERE status = 'completed'")
    completed_count = cur.fetchone()[0]
    print(f"DONE: {total} total stocks, {completed_count} pre-computed with instant scores.")
    conn.close()
