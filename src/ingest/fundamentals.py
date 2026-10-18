"""Company fundamentals / financial-integrity red flags.

Hackathon approach: manual CSV, same reasoning as shareholding.py — 20 companies,
hand-key from annual reports / screener pages. Columns in
data/cache/fundamentals.csv:

    ticker, fy_end, revenue_cr, profit_cr, unbilled_rev_pct, top_customer_pct,
    related_party_pct, proceeds_used_as_stated (bool), note
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache"
FUND_CSV = CACHE_DIR / "fundamentals.csv"

_TEMPLATE = pd.DataFrame({
    "ticker": ["VARANIUM", "VARANIUM", "ADDSHOP", "ADDSHOP",
               "TRAFIKSOL", "TRAFIKSOL", "FAMILYPUMP", "FAMILYPUMP"],
    "fy_end": ["2023-03-31", "2024-03-31", "2022-03-31", "2023-03-31",
               "2023-03-31", "2024-03-31", "2022-03-31", "2023-03-31"],
    "revenue_cr": [22.0, 68.0, 15.0, 41.0, 30.0, 72.0, 18.0, 47.0],  # >2x jumps
    "profit_cr": [2.0, 9.5, 1.5, 5.0, 3.0, 8.0, 1.8, 6.0],
    "unbilled_rev_pct": [5.0, 22.0, 4.0, 17.0, 6.0, 19.0, 3.0, 16.0],
    "top_customer_pct": [18.0, 47.0, 22.0, 45.0, 25.0, 52.0, 20.0, 43.0],
    "related_party_pct": [4.0, 19.0, 3.0, 24.0, 5.0, 12.0, 2.0, 18.0],
    "proceeds_used_as_stated": [True, False, True, False, True, True, True, False],
    "note": ["REPLACE with real annual-report data"] * 8,
})


_ALIASES: dict[str, list[str]] = {
    "CLOUD": ["CLOUD", "VARANIUM"],
    "VARANIUM": ["VARANIUM", "CLOUD"],
    "ASRL": ["ASRL", "ADDSHOP"],
    "ADDSHOP": ["ADDSHOP", "ASRL"],
    "AFCOM": ["AFCOM", "FAMILYPUMP"],
    "FAMILYPUMP": ["FAMILYPUMP", "AFCOM"],
}


def load_fundamentals(ticker: str | None = None) -> pd.DataFrame:
    if not FUND_CSV.exists():
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _TEMPLATE.to_csv(FUND_CSV, index=False)
    df = pd.read_csv(FUND_CSV, parse_dates=["fy_end"])
    if ticker:
        t_up = ticker.upper()
        symbols = _ALIASES.get(t_up, [t_up])
        return df[df.ticker.isin(symbols)].sort_values("fy_end").reset_index(drop=True)
    return df


def red_flags(ticker: str, as_of: pd.Timestamp) -> dict:
    """Point-in-time financial red flags as of `as_of`."""
    df = load_fundamentals(ticker)
    df = df[df.fy_end <= as_of]
    flags = {"revenue_jump": False, "unbilled_high": False,
             "concentration_high": False, "related_party_high": False,
             "proceeds_misuse": False, "years_available": len(df)}
    if df.empty:
        return flags
    last = df.iloc[-1]
    flags["unbilled_high"] = bool(last.unbilled_rev_pct >= 15)
    flags["concentration_high"] = bool(last.top_customer_pct >= 40)
    flags["related_party_high"] = bool(last.related_party_pct >= 15)
    flags["proceeds_misuse"] = not bool(last.proceeds_used_as_stated)
    if len(df) >= 2:
        prev = df.iloc[-2]
        if prev.revenue_cr > 0:
            flags["revenue_jump"] = bool(last.revenue_cr / prev.revenue_cr >= 2.0)
    return flags
