"""Market data ingestion: OHLCV, delivery %, circuit hits.

Strategy (hackathon):
    1. ALWAYS write fetched data to data/cache/*.parquet — the demo reads cache only.
    2. Live fetch is best-effort. If it fails, fall back to cache, then to synthetic
       sample data so nothing ever blocks the demo.

Real sources to plug in (week 1):
    - NSE bhavcopy (daily OHLCV):  https://www.nseindia.com/api/reports  (archives)
    - NSE delivery data:           daily "security-wise delivery position" files
    - Circuit hits:                NSE/BSE "securities hitting price bands" lists
    - Quick fallback:              yfinance with "<ticker>.NS" (OHLCV only, no delivery)
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def load_universe(path: str | Path | None = None) -> pd.DataFrame:
    """Load the demo universe (cases + controls)."""
    p = Path(path) if path else Path(__file__).resolve().parents[2] / "config" / "universe.csv"
    return pd.read_csv(p, parse_dates=["listing_date", "lockin_expiry", "pump_end"])


def default_as_of(ticker: str) -> pd.Timestamp:
    """Demo replay date: for synthetic case tickers, the day the pump ends
    (so the demo shows the moment of maximum danger); otherwise now.

    REMOVE once live data is wired — a production system always scores at now.
    """
    try:
        uni = load_universe()
        row = uni[uni.ticker == ticker]
        if not row.empty and pd.notna(row.iloc[0].get("pump_end")):
            return row.iloc[0].pump_end
    except Exception:
        pass
    return pd.Timestamp.now()


def _cache_path(ticker: str) -> Path:
    return CACHE_DIR / f"ohlcv_{ticker}.parquet"


def fetch_ohlcv(ticker: str, start: date, end: date) -> pd.DataFrame:
    """Best-effort live fetch. TODO(live-data): NSE bhavcopy / yfinance.

    Expected output columns: date, open, high, low, close, volume,
    delivery_pct (0-100, may be NaN until NSE delivery files are wired in).
    """
    raise NotImplementedError(
        "Wire NSE bhavcopy or yfinance here in week 1; "
        "until then use load_ohlcv() which falls back to cache/synthetic."
    )


def load_ohlcv(ticker: str, start: date | str = "2023-01-01",
               end: date | str | None = None, allow_synthetic: bool = True) -> pd.DataFrame:
    """Load OHLCV for a ticker: cache -> live -> synthetic (labelled)."""
    cache = _cache_path(ticker)
    if cache.exists():
        df = pd.read_parquet(cache)
    else:
        try:
            df = fetch_ohlcv(ticker, pd.Timestamp(start).date(),
                             pd.Timestamp(end).date() if end else date.today())
            df.to_parquet(cache)
        except NotImplementedError:
            if not allow_synthetic:
                raise
            df = make_synthetic_ohlcv(ticker, start, end)

    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def make_synthetic_ohlcv(ticker: str, start: date | str = "2023-01-01",
                         end: date | str | None = None,
                         pump: bool | None = None,
                         pump_end: pd.Timestamp | None = None) -> pd.DataFrame:
    """Deterministic synthetic series so the engine/tests run offline.

    For case tickers the pump window (ramp -> spike -> dump) is anchored so
    it ENDS at the universe's `pump_end` date (a few days before the SEBI
    event). Controls get a quiet random walk. Defaults are read from the
    universe when not passed explicitly.
    """
    if pump is None or pump_end is None:
        try:
            uni = load_universe()
            row = uni[uni.ticker == ticker]
            if not row.empty:
                if pump is None:
                    pump = bool(row.iloc[0].role == "case")
                if pump_end is None and pd.notna(row.iloc[0].get("pump_end")):
                    pump_end = row.iloc[0].pump_end
        except Exception:
            pump = pump or False

    start, end = pd.Timestamp(start), pd.Timestamp(end or date.today())
    days = pd.bdate_range(start, end)
    n = len(days)
    rng = np.random.default_rng(abs(hash(ticker)) % (2**32))

    base_price = 40 + rng.uniform(0, 60)
    drift = rng.normal(0.0005, 0.015, n).cumsum()
    volume = rng.lognormal(mean=10, sigma=0.4, size=n)
    delivery = np.clip(rng.normal(45, 10, n), 5, 95)

    if pump:
        # anchor: pump window = 40 sessions ending at pump_end (or series end)
        if pump_end is not None and pump_end > start:
            end_pos = int(np.searchsorted(days, pump_end, side="right")) - 1
        else:
            end_pos = n - 1
        k = end_pos - 39
        if k > 0:
            # ramp to ~5x peak, then collapse ~65%. Volume stays elevated
            # THROUGH the dump (distribution) and delivery stays weak.
            ramp = min(25, end_pos - k)
            drift[k:k + ramp] += np.linspace(0, 1.6, ramp)               # ramp (log)
            drift[k + ramp:end_pos + 1] += np.linspace(1.6, 0.5, end_pos - k - ramp + 1)
            drift[end_pos + 1:] += 0.5                                    # stays dumped
            volume[k:k + ramp] *= 10                                      # volume explosion
            volume[k + ramp:end_pos + 1] *= 5                             # distribution volume
            delivery[k:end_pos + 1] *= 0.4                                # weak delivery

    close = base_price * np.exp(drift)
    df = pd.DataFrame({
        "date": days,
        "open": close * (1 + rng.normal(0, 0.004, n)),
        "high": close * (1 + np.abs(rng.normal(0, 0.008, n))),
        "low": close * (1 - np.abs(rng.normal(0, 0.008, n))),
        "close": close,
        "volume": volume.round(),
        "delivery_pct": delivery.round(1),
    })
    df["synthetic"] = True  # never let synthetic rows masquerade as real data
    return df


def circuit_hits(df: pd.DataFrame, band: float = 0.05) -> pd.Series:
    """Approximate circuit hits from close-to-close moves (±5% default SME band).

    TODO(live-data): replace with actual NSE/BSE price-band lists.
    """
    ret = df["close"].pct_change()
    return (ret.abs() >= band - 1e-9).fillna(False)
