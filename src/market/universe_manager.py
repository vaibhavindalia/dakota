"""Universe Manager: High-performance access and sync for 2,615+ Indian stocks.

Maintains SQLite persistence in `data/dakota.db` for instant querying (<5ms),
supports debounced live search, segment filtering, pagination, and on-demand risk scoring.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = BASE_DIR / "data" / "dakota.db"

logger = logging.getLogger(__name__)


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def query_stocks(
    search: str = "",
    segment: str = "",
    band: str = "",
    page: int = 1,
    limit: int = 50,
    sort_by: str = "score_desc",
) -> dict[str, Any]:
    """Query stocks with instant search, segment filtering, and pagination."""
    page = max(1, page)
    limit = max(1, min(limit, 200))
    offset = (page - 1) * limit

    conn = _get_connection()
    cur = conn.cursor()

    conditions: list[str] = []
    params: list[Any] = []

    if search:
        search_term = f"%{search.strip().upper()}%"
        conditions.append("(ticker LIKE ? OR UPPER(name) LIKE ?)")
        params.extend([search_term, search_term])

    if segment:
        seg_clean = segment.strip().lower()
        if seg_clean == "surveillance":
            conditions.append("is_surveillance = 1")
        elif seg_clean == "sme":
            conditions.append("segment LIKE '%sme%'")
        elif seg_clean == "main":
            conditions.append("segment = 'main' AND is_surveillance = 0")

    if band:
        band_clean = band.strip()
        if band_clean.lower() in ("high", "elevated", "low"):
            conditions.append("band = ?")
            params.append(band_clean.capitalize())

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # Sort clause
    sort_clause = "ORDER BY score DESC NULLS LAST, ticker ASC"
    if sort_by == "score_asc":
        sort_clause = "ORDER BY score ASC NULLS LAST, ticker ASC"
    elif sort_by == "ticker_asc":
        sort_clause = "ORDER BY ticker ASC"
    elif sort_by == "ticker_desc":
        sort_clause = "ORDER BY ticker DESC"

    # Count total matching
    count_sql = f"SELECT COUNT(*) FROM stock_assessments {where_clause}"
    cur.execute(count_sql, params)
    total_matching = cur.fetchone()[0]

    # Query page rows
    query_sql = f"""
    SELECT ticker, name, exchange, segment, role, score, band, verdict,
           latest_price, change_pct, high_52w, low_52w, volume, is_surveillance,
           status, updated_at
    FROM stock_assessments
    {where_clause}
    {sort_clause}
    LIMIT ? OFFSET ?
    """
    cur.execute(query_sql, params + [limit, offset])
    rows = [dict(r) for r in cur.fetchall()]

    # Global stats
    cur.execute("SELECT COUNT(*), COUNT(score) FROM stock_assessments")
    global_total, global_assessed = cur.fetchone()

    conn.close()

    total_pages = (total_matching + limit - 1) // limit if total_matching > 0 else 1

    return {
        "stocks": rows,
        "items": rows,
        "total": total_matching,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "global_total": global_total,
        "global_assessed": global_assessed,
    }


def get_or_assess_stock(
    ticker: str,
    force_refresh: bool = False,
    max_age_seconds: int | None = None,
) -> dict[str, Any]:
    """Retrieve stock record from DB. If score is missing, stale, or force_refresh requested, assess it on-demand and cache it."""
    ticker = ticker.upper().strip()
    conn = _get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM stock_assessments WHERE ticker = ?", (ticker,))
    row = cur.fetchone()

    if not row:
        # Stock not yet in database: attempt on-demand assessment
        try:
            from src.engine.risk_engine import assess
            risk = assess(ticker)
            score = risk.get("score")
            band = risk.get("band", "Unavailable")
            verdict = risk.get("verdict", "")
            now_iso = datetime.now(timezone.utc).isoformat()
            cur.execute("""
            INSERT OR REPLACE INTO stock_assessments (
                ticker, name, exchange, segment, role, score, band, verdict, status, updated_at
            ) VALUES (?, ?, 'NSE', 'main', 'control', ?, ?, ?, 'completed', ?)
            """, (ticker, ticker, score, band, verdict, now_iso))
            conn.commit()
            cur.execute("SELECT * FROM stock_assessments WHERE ticker = ?", (ticker,))
            row = cur.fetchone()
        except Exception as exc:
            logger.warning("Dynamic assessment creation failed for %s: %s", ticker, exc)
            conn.close()
            return {"ticker": ticker, "status": "not_found", "score": None, "band": "Unavailable"}

    data = dict(row)

    # Check staleness
    needs_refresh = force_refresh
    if not needs_refresh and max_age_seconds is not None and data.get("updated_at"):
        try:
            raw_ts = str(data["updated_at"]).replace("Z", "+00:00")
            updated_dt = datetime.fromisoformat(raw_ts)
            if updated_dt.tzinfo is None:
                updated_dt = updated_dt.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            if (now - updated_dt).total_seconds() > max_age_seconds:
                needs_refresh = True
        except Exception:
            pass

    # If already assessed and no refresh requested, return directly
    if not needs_refresh and data.get("score") is not None and data.get("status") == "completed":
        conn.close()
        return data

    # Perform on-demand assessment
    try:
        from src.engine.risk_engine import assess
        risk = assess(ticker)
        score = risk.get("score")
        band = risk.get("band", "Unavailable")
        verdict = risk.get("verdict", "")

        now_iso = datetime.now(timezone.utc).isoformat()
        cur.execute("""
        UPDATE stock_assessments SET
            score = ?,
            band = ?,
            verdict = ?,
            status = 'completed',
            updated_at = ?
        WHERE ticker = ?
        """, (score, band, verdict, now_iso, ticker))
        conn.commit()

        data.update({
            "score": score,
            "band": band,
            "verdict": verdict,
            "status": "completed",
            "updated_at": now_iso,
        })
    except Exception as exc:
        logger.warning("On-demand assessment failed for %s: %s", ticker, exc)
    finally:
        conn.close()

    return data


def sync_pending_batch(batch_size: int = 10) -> int:
    """Assess a batch of pending stocks in the background."""
    conn = _get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT ticker FROM stock_assessments
    WHERE score IS NULL AND status = 'pending'
    ORDER BY ticker ASC
    LIMIT ?
    """, (batch_size,))
    pending = [r[0] for r in cur.fetchall()]

    if not pending:
        conn.close()
        return 0

    from src.engine.risk_engine import assess

    updated = 0
    now_iso = datetime.now(timezone.utc).isoformat()
    for ticker in pending:
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
            """, (score, band, verdict, now_iso, ticker))
            conn.commit()
            updated += 1
        except Exception as exc:
            # Mark error so we don't spin on invalid tickers
            cur.execute("""
            UPDATE stock_assessments SET
                status = 'error',
                verdict = ?,
                updated_at = ?
            WHERE ticker = ?
            """, (str(exc)[:200], now_iso, ticker))
            conn.commit()

    conn.close()
    return updated
