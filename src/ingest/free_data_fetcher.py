"""Free data fetcher for Dakota - yfinance + Screener.in (no API key needed).

Strategy (100% Free):
    1. yfinance  -> Large-cap and main-board stocks (good coverage)
    2. Screener.in free public JSON -> SME fundamentals (fallback)

Saved to  data/cache/fundamentals_live.csv  and  data/cache/shareholding_live.csv
so the risk engine reads them instantly without any live API wait time.

Usage:
    python -m src.ingest.free_data_fetcher           # fetch all stocks in universe
    python -m src.ingest.free_data_fetcher TRAFIKSOL  # fetch one stock only
"""
from __future__ import annotations

import csv
import json
import logging
import sys
import time
import urllib.request
from datetime import datetime, date
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
CACHE_DIR = BASE_DIR / "data" / "cache"
UNIVERSE_CSV = BASE_DIR / "config" / "universe.csv"

FUND_LIVE_CSV = CACHE_DIR / "fundamentals_live.csv"
SH_LIVE_CSV = CACHE_DIR / "shareholding_live.csv"

FUND_COLUMNS = [
    "ticker", "fetched_at", "source",
    "revenue_cr", "profit_cr", "total_debt_cr",
    "market_cap_cr", "pe_ratio", "price_52w_change_pct",
    "insider_pct", "insider_pct_source",
    "zero_revenue_flag", "high_debt_flag", "price_pump_flag", "notes",
]

SH_COLUMNS = [
    "ticker", "fetched_at", "source", "quarter_label",
    "promoter_pct", "promoter_delta_pp", "promoter_dumping_flag",
    "public_pct", "notes",
]


def _load_tickers() -> list[dict]:
    rows = []
    with open(UNIVERSE_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("ticker"):
                rows.append(row)
    return rows


def _yf_suffix(exchange: str) -> str:
    return ".NS" if str(exchange).upper() == "NSE" else ".BO"


def _fetch_yfinance(ticker: str, exchange: str) -> dict[str, Any] | None:
    """Fetch fundamentals from Yahoo Finance. Returns None on failure."""
    try:
        import yfinance as yf  # type: ignore
    except ImportError:
        logger.warning("yfinance not installed. Run: pip install yfinance")
        return None

    symbol = ticker + _yf_suffix(exchange)
    try:
        info = yf.Ticker(symbol).info
        if not info:
            return None
        mc = info.get("marketCap")
        price = info.get("regularMarketPrice")
        if mc is None and price is None:
            return None

        to_cr = lambda v: round(float(v) / 1e7, 2) if v else 0.0
        revenue_cr = to_cr(info.get("totalRevenue") or 0)
        debt_cr    = to_cr(info.get("totalDebt") or 0)
        mc_cr      = to_cr(info.get("marketCap") or 0)
        profit_cr  = to_cr(info.get("netIncomeToCommon") or 0)

        w52 = info.get("52WeekChange")
        price_pump_pct = round(float(w52) * 100, 1) if w52 is not None else None

        insider_raw = info.get("heldPercentInsiders")
        insider_pct = round(float(insider_raw) * 100, 2) if insider_raw is not None else None

        pe = info.get("trailingPE")

        zero_revenue = revenue_cr < 1.0
        high_debt    = (debt_cr / revenue_cr > 3.0) if revenue_cr > 0.5 else False
        price_pump   = price_pump_pct is not None and price_pump_pct > 500

        return {
            "ticker": ticker,
            "fetched_at": datetime.utcnow().isoformat(),
            "source": "yfinance",
            "revenue_cr": revenue_cr,
            "profit_cr": profit_cr,
            "total_debt_cr": debt_cr,
            "market_cap_cr": mc_cr,
            "pe_ratio": round(float(pe), 1) if pe else None,
            "price_52w_change_pct": price_pump_pct,
            "insider_pct": insider_pct,
            "insider_pct_source": "yfinance",
            "zero_revenue_flag": zero_revenue,
            "high_debt_flag": high_debt,
            "price_pump_flag": price_pump,
            "notes": "Yahoo Finance " + symbol,
        }
    except Exception as exc:
        logger.debug("yfinance failed for %s: %s", symbol, exc)
        return None


def _fetch_screener(ticker: str) -> dict[str, Any] | None:
    """Fetch basic fundamentals from Screener.in public JSON endpoint (free, no login)."""
    url = "https://www.screener.in/api/company/" + ticker + "/?format=json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        # Build ratios dict
        ratios: dict = {}
        src = data.get("consolidated") or data.get("standalone") or {}
        for section in src.get("ratios", []):
            ratios[section.get("name", "")] = section.get("values", [])

        def _last(key: str) -> float | None:
            vals = ratios.get(key, [])
            if vals:
                try:
                    return float(str(vals[-1]).replace(",", "").replace("%", ""))
                except (ValueError, TypeError):
                    pass
            return None

        revenue_cr = _last("Sales")
        profit_cr  = _last("Net Profit")
        debt_cr    = _last("Borrowings")
        mc_cr      = _last("Market Cap")
        pe         = _last("Price to Earning")

        # Promoter shareholding
        promoter_pct: float | None = None
        for row in data.get("shareholding_pattern", {}).get("rows", []):
            if "Promoter" in str(row.get("name", "")):
                vals = row.get("values", [])
                if vals:
                    try:
                        promoter_pct = float(str(vals[-1]).replace(",", "").replace("%", ""))
                    except (ValueError, TypeError):
                        pass
                break

        zero_revenue = bool(revenue_cr is not None and revenue_cr < 1.0)
        high_debt    = bool(revenue_cr and revenue_cr > 0.5 and debt_cr and debt_cr / revenue_cr > 3.0)

        return {
            "ticker": ticker,
            "fetched_at": datetime.utcnow().isoformat(),
            "source": "screener.in",
            "revenue_cr": revenue_cr or 0.0,
            "profit_cr": profit_cr or 0.0,
            "total_debt_cr": debt_cr or 0.0,
            "market_cap_cr": mc_cr or 0.0,
            "pe_ratio": pe,
            "price_52w_change_pct": None,
            "insider_pct": promoter_pct,
            "insider_pct_source": "screener.in",
            "zero_revenue_flag": zero_revenue,
            "high_debt_flag": high_debt,
            "price_pump_flag": False,
            "notes": "Screener.in " + ticker,
            "_promoter_pct": promoter_pct,
        }
    except Exception as exc:
        logger.debug("Screener.in failed for %s: %s", ticker, exc)
        return None


def fetch_stock_data(ticker: str, exchange: str) -> dict[str, Any] | None:
    """Try yfinance first, then screener.in. Returns None if both fail."""
    result = _fetch_yfinance(ticker, exchange)
    if result is None:
        logger.info("%s: yfinance failed -> trying Screener.in", ticker)
        result = _fetch_screener(ticker)
    if result is None:
        logger.warning("%s: all free sources failed", ticker)
    return result


def _upsert_csv(path: Path, new_df: pd.DataFrame, key: str) -> None:
    """Update rows for given tickers; preserve rows for other tickers."""
    if path.exists():
        old_df = pd.read_csv(path)
        old_df = old_df[~old_df[key].isin(new_df[key])]
        combined = pd.concat([old_df, new_df], ignore_index=True)
    else:
        combined = new_df
    combined.to_csv(path, index=False, encoding="utf-8")
    logger.info("Saved %d rows -> %s", len(new_df), path)


def fetch_all_and_save(tickers: list[dict] | None = None) -> dict[str, int]:
    """Fetch all tickers in universe and update CSV caches. Returns stats."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    rows_in  = tickers or _load_tickers()
    fund_rows: list[dict] = []
    sh_rows:  list[dict] = []
    stats = {"ok": 0, "failed": 0, "total": len(rows_in)}

    for row in rows_in:
        ticker   = str(row.get("ticker", "")).upper().strip()
        exchange = str(row.get("exchange", "NSE")).upper().strip()
        if not ticker:
            continue

        logger.info("Fetching %s (%s)...", ticker, exchange)
        data = fetch_stock_data(ticker, exchange)

        if data:
            fund_row = {col: data.get(col) for col in FUND_COLUMNS}
            fund_row["ticker"] = ticker
            fund_rows.append(fund_row)

            promoter_pct = data.get("insider_pct") or data.get("_promoter_pct")
            if promoter_pct is not None:
                sh_rows.append({
                    "ticker": ticker,
                    "fetched_at": data["fetched_at"],
                    "source": data.get("insider_pct_source", "yfinance"),
                    "quarter_label": date.today().strftime("Q%m-%Y"),
                    "promoter_pct": promoter_pct,
                    "promoter_delta_pp": None,
                    "promoter_dumping_flag": False,
                    "public_pct": round(100.0 - promoter_pct, 2),
                    "notes": "Auto-fetched " + str(date.today()),
                })
            stats["ok"] += 1
        else:
            stats["failed"] += 1

        time.sleep(0.5)  # polite delay between requests

    # Compute promoter delta vs previous run
    if SH_LIVE_CSV.exists() and sh_rows:
        prev = pd.read_csv(SH_LIVE_CSV)
        for sh_row in sh_rows:
            prev_row = prev[prev.ticker == sh_row["ticker"]]
            if not prev_row.empty:
                prev_pct = float(prev_row.iloc[-1]["promoter_pct"])
                delta = round(sh_row["promoter_pct"] - prev_pct, 2)
                sh_row["promoter_delta_pp"]     = delta
                sh_row["promoter_dumping_flag"] = delta <= -5.0  # sold >5pp = Red Flag

    _upsert_csv(FUND_LIVE_CSV, pd.DataFrame(fund_rows, columns=FUND_COLUMNS), key="ticker")
    if sh_rows:
        _upsert_csv(SH_LIVE_CSV, pd.DataFrame(sh_rows, columns=SH_COLUMNS), key="ticker")

    logger.info("Done. OK=%d Failed=%d Total=%d", stats["ok"], stats["failed"], stats["total"])
    return stats


def load_live_fundamentals(ticker: str | None = None) -> pd.DataFrame:
    """Load live fundamentals cache. Returns empty DataFrame if not populated yet."""
    if not FUND_LIVE_CSV.exists():
        return pd.DataFrame(columns=FUND_COLUMNS)
    df = pd.read_csv(FUND_LIVE_CSV)
    return df[df.ticker == ticker].reset_index(drop=True) if ticker else df


def load_live_shareholding(ticker: str | None = None) -> pd.DataFrame:
    """Load live shareholding cache."""
    if not SH_LIVE_CSV.exists():
        return pd.DataFrame(columns=SH_COLUMNS)
    df = pd.read_csv(SH_LIVE_CSV)
    return df[df.ticker == ticker].reset_index(drop=True) if ticker else df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    specific = sys.argv[1].upper() if len(sys.argv) > 1 else None
    rows = _load_tickers()
    if specific:
        rows = [r for r in rows if r["ticker"].upper() == specific]
        if not rows:
            print("Ticker " + specific + " not found in universe.csv")
            sys.exit(1)
    result = fetch_all_and_save(rows)
    print("\nFetch complete: " + str(result["ok"]) + " OK | " + str(result["failed"]) + " failed | " + str(result["total"]) + " total")
