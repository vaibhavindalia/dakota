"""Shareholding-pattern ingestion: promoter %, public %, lock-in calendar.

Hackathon approach: **manual CSV first.** For a 20-stock universe, hand-keying
quarterly shareholding from BSE filings (2-4 quarters per stock) is faster and
more reliable than scraping. Scrape later only if time permits.

Expected manual file: data/cache/shareholding.csv with columns:
    ticker, quarter_end, promoter_pct, public_pct, note

Real sources (week 1, optional):
    - BSE shareholding pattern pages (per scrip code)
    - NSE corporate filings
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache"
SH_CSV = CACHE_DIR / "shareholding.csv"

_TEMPLATE = pd.DataFrame({
    "ticker": ["VARANIUM", "VARANIUM", "VARANIUM",
               "ADDSHOP", "ADDSHOP", "ADDSHOP",
               "TRAFIKSOL", "TRAFIKSOL", "TRAFIKSOL",
               "FAMILYPUMP", "FAMILYPUMP", "FAMILYPUMP"],
    "quarter_end": ["2023-09-30", "2023-12-31", "2024-03-31",
                    "2023-03-31", "2023-06-30", "2023-09-30",
                    "2023-06-30", "2023-09-30", "2023-12-31",
                    "2023-06-30", "2023-09-30", "2023-12-31"],
    # Illustrative pump pattern: promoter selling down, public holding climbing
    "promoter_pct": [62.0, 55.0, 48.0,
                     58.0, 52.0, 45.0,
                     60.0, 53.0, 50.0,
                     57.0, 50.0, 44.0],
    "public_pct": [38.0, 45.0, 52.0,
                   42.0, 48.0, 55.0,
                   40.0, 47.0, 50.0,
                   43.0, 50.0, 56.0],
    "note": ["REPLACE with real BSE filing data"] * 12,
})


def load_shareholding(ticker: str | None = None) -> pd.DataFrame:
    """Load shareholding rows; seeds a template file on first run."""
    if not SH_CSV.exists():
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _TEMPLATE.to_csv(SH_CSV, index=False)
    df = pd.read_csv(SH_CSV, parse_dates=["quarter_end"])
    if ticker:
        return df[df.ticker == ticker].sort_values("quarter_end").reset_index(drop=True)
    return df


def promoter_trend(ticker: str, as_of: pd.Timestamp) -> dict:
    """Point-in-time promoter/public trend as of `as_of` (no lookahead!)."""
    df = load_shareholding(ticker)
    df = df[df.quarter_end <= as_of]
    if len(df) < 2:
        return {"quarters": len(df), "promoter_delta_pp": 0.0, "public_delta_pp": 0.0,
                "promoter_falling": False}
    first, last = df.iloc[0], df.iloc[-1]
    p_delta = float(last.promoter_pct - first.promoter_pct)
    return {
        "quarters": len(df),
        "promoter_delta_pp": round(p_delta, 2),
        "public_delta_pp": round(float(last.public_pct - first.public_pct), 2),
        "promoter_falling": p_delta <= -3.0,  # >=3pp decline over observed quarters
    }


def days_to_lockin_expiry(ticker: str, as_of: pd.Timestamp,
                          universe: pd.DataFrame | None = None) -> int | None:
    """Days until lock-in expiry (None if unknown/already passed far in past)."""
    from src.ingest.market_data import load_universe
    uni = universe if universe is not None else load_universe()
    row = uni[uni.ticker == ticker]
    if row.empty or pd.isna(row.iloc[0].lockin_expiry):
        return None
    return int((row.iloc[0].lockin_expiry - as_of).days)
