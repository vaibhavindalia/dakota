"""On-demand real historical market data for Dakota.

This module deliberately fetches history for a requested ticker rather than
scraping the whole market. The investigation engine only needs detailed history
for the stock mentioned in a tip, which keeps network load and storage bounded.

NSE source adapter:
    nse-archives / nsedata -> NSE's "Full Bhavcopy and Security Deliverable
    data" (sec_bhavdata_full), which contains OHLCV and delivery fields.

NSE index adapter:
    nsedata -> historical NIFTY 50 index data.

BSE source adapter:
    bseindia -> BSE historical equity data for the requested symbol.

No synthetic fallback is used here. A source failure is reported explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
import time
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REAL_DIR = ROOT / "data" / "real"
REAL_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class FetchResult:
    exchange: str
    ticker: str
    rows: int
    first_date: str | None
    last_date: str | None
    path: str
    status: str
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "exchange": self.exchange,
            "ticker": self.ticker,
            "rows": self.rows,
            "first_date": self.first_date,
            "last_date": self.last_date,
            "path": self.path,
            "status": self.status,
            "message": self.message,
        }


def _symbol_path(exchange: str, ticker: str) -> Path:
    safe = ticker.upper().strip().replace("/", "_").replace(" ", "_")
    return REAL_DIR / f"{exchange.lower()}_{safe}_daily.csv"


def _date_str(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return pd.Timestamp(value).strftime("%Y-%m-%d")
    except Exception:
        return str(value)


def _pick(df: pd.DataFrame, *names: str) -> str | None:
    normalized = {str(c).strip().upper().replace(" ", "_"): c for c in df.columns}
    for name in names:
        key = name.strip().upper().replace(" ", "_")
        if key in normalized:
            return normalized[key]
    return None


def _numeric(df: pd.DataFrame, column: str | None) -> pd.Series:
    if column is None:
        return pd.Series(index=df.index, dtype="float64")
    return pd.to_numeric(
        df[column].astype(str).str.replace(",", "", regex=False),
        errors="coerce",
    )


def _normalise_nse_day(df: pd.DataFrame, ticker: str, trade_date: date) -> pd.DataFrame:
    symbol_col = _pick(df, "SYMBOL", "TckrSymb")
    if symbol_col is not None:
        mask = df[symbol_col].astype(str).str.upper().eq(ticker.upper())
        df = df.loc[mask].copy()

    if df.empty:
        return pd.DataFrame()

    open_col = _pick(df, "OPEN_PRICE", "OpnPric")
    high_col = _pick(df, "HIGH_PRICE", "HghPric")
    low_col = _pick(df, "LOW_PRICE", "LwPric")
    close_col = _pick(df, "CLOSE_PRICE", "ClsPric")
    prev_col = _pick(df, "PREV_CLOSE", "PrvsClsgPric")
    volume_col = _pick(df, "TTL_TRD_QNTY", "TtlTradgVol")
    delivery_qty_col = _pick(df, "DELIV_QTY")
    delivery_pct_col = _pick(df, "DELIV_PER")
    series_col = _pick(df, "SERIES", "SctySrs")
    isin_col = _pick(df, "ISIN")

    out = pd.DataFrame({
        "exchange": "NSE",
        "ticker": ticker.upper(),
        "trade_date": pd.Timestamp(trade_date).normalize(),
        "series": df[series_col].astype(str) if series_col else "",
        "isin": df[isin_col].astype(str) if isin_col else "",
        "open": _numeric(df, open_col),
        "high": _numeric(df, high_col),
        "low": _numeric(df, low_col),
        "close": _numeric(df, close_col),
        "previous_close": _numeric(df, prev_col),
        "volume": _numeric(df, volume_col),
        "delivery_quantity": _numeric(df, delivery_qty_col),
        "delivery_pct": _numeric(df, delivery_pct_col),
    })
    return out.reset_index(drop=True)


def fetch_nse_history(
    ticker: str,
    start_date: date,
    end_date: date,
    *,
    pause_seconds: float = 0.25,
    max_calendar_days: int = 400,
) -> FetchResult:
    """Fetch NSE daily history with real OHLCV + delivery data."""
    try:
        from nsedata import nse
    except ImportError as exc:
        return FetchResult(
            "NSE", ticker, 0, None, None, str(_symbol_path("NSE", ticker)),
            "missing_dependency",
            "Install nse-archives or indian-market-data first.",
        )

    if end_date < start_date:
        raise ValueError("end_date must be >= start_date")
    if (end_date - start_date).days > max_calendar_days:
        raise ValueError(
            f"Refusing more than {max_calendar_days} calendar days in one run. "
            "Run smaller windows to keep exchange load bounded."
        )

    rows: list[pd.DataFrame] = []
    current = start_date

    while current <= end_date:
        try:
            day_df = nse.get(
                "capital_market",
                "equities_sme",
                "sec_bhavdata_full",
                current.strftime("%Y-%m-%d"),
            )
            normalised = _normalise_nse_day(
                day_df,
                ticker,
                current,
            )
            if not normalised.empty:
                rows.append(normalised)
        except Exception:
            # Weekend/holiday/no-file days are expected. The caller gets only
            # the successful rows; failures are not converted into synthetic data.
            pass

        current += timedelta(days=1)
        if pause_seconds:
            time.sleep(pause_seconds)

    path = _symbol_path("NSE", ticker)

    if not rows:
        return FetchResult(
            "NSE", ticker, 0, None, None, str(path),
            "no_data",
            "No matching NSE rows were returned for the requested date range.",
        )

    out = pd.concat(rows, ignore_index=True)
    out = out.drop_duplicates(
        subset=["exchange", "ticker", "trade_date"],
        keep="last",
    ).sort_values("trade_date")
    out.to_csv(path, index=False)

    return FetchResult(
        "NSE",
        ticker,
        len(out),
        _date_str(out["trade_date"].min()),
        _date_str(out["trade_date"].max()),
        str(path),
        "ok",
    )


def _normalise_bse_history(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    date_col = _pick(df, "DATE", "TRADE_DATE", "TRADDT", "TRADDT")
    open_col = _pick(df, "OPEN", "OPEN_PRICE", "OPNPRC", "OpnPric")
    high_col = _pick(df, "HIGH", "HIGH_PRICE", "HGHPRC", "HghPric")
    low_col = _pick(df, "LOW", "LOW_PRICE", "LTP", "LwPric")
    close_col = _pick(df, "CLOSE", "CLOSE_PRICE", "CLS_PRC", "ClsPric")
    prev_col = _pick(df, "PREV_CLOSE", "PREVCLOSE", "PrvsClsgPric")
    volume_col = _pick(df, "VOLUME", "TTL_TRD_QNTY", "TtlTradgVol")

    if date_col is None or close_col is None:
        raise ValueError(
            f"Could not identify BSE historical columns: {list(df.columns)}"
        )

    out = pd.DataFrame({
        "exchange": "BSE",
        "ticker": ticker.upper(),
        "trade_date": pd.to_datetime(df[date_col], errors="coerce").dt.normalize(),
        "series": "",
        "isin": "",
        "open": _numeric(df, open_col),
        "high": _numeric(df, high_col),
        "low": _numeric(df, low_col),
        "close": _numeric(df, close_col),
        "previous_close": _numeric(df, prev_col),
        "volume": _numeric(df, volume_col),
        "delivery_quantity": float("nan"),
        "delivery_pct": float("nan"),
    })

    return (
        out.dropna(subset=["trade_date", "close"])
        .drop_duplicates(subset=["exchange", "ticker", "trade_date"])
        .sort_values("trade_date")
        .reset_index(drop=True)
    )


def fetch_bse_history(
    ticker: str,
    start_date: date,
    end_date: date,
) -> FetchResult:
    """Fetch BSE historical daily OHLCV for one symbol."""
    try:
        from bseindia import equity
    except ImportError:
        return FetchResult(
            "BSE", ticker, 0, None, None, str(_symbol_path("BSE", ticker)),
            "missing_dependency",
            "Install bseindia first.",
        )

    path = _symbol_path("BSE", ticker)

    try:
        raw = equity.historical_stock_data(
            symbol=ticker.upper(),
            from_date=start_date.strftime("%d-%m-%Y"),
            to_date=end_date.strftime("%d-%m-%Y"),
        )
        out = _normalise_bse_history(raw, ticker)
    except Exception as exc:
        return FetchResult(
            "BSE", ticker, 0, None, None, str(path),
            "error",
            str(exc),
        )

    if out.empty:
        return FetchResult(
            "BSE", ticker, 0, None, None, str(path),
            "no_data",
            "BSE returned no matching daily rows.",
        )

    out.to_csv(path, index=False)

    return FetchResult(
        "BSE",
        ticker,
        len(out),
        _date_str(out["trade_date"].min()),
        _date_str(out["trade_date"].max()),
        str(path),
        "ok",
    )


def fetch_nifty50_history(
    start_date: date,
    end_date: date,
) -> dict[str, Any]:
    """Fetch NIFTY 50 index history from the NSE index dataset."""
    try:
        from nsedata import nse
    except ImportError:
        return {
            "status": "missing_dependency",
            "message": "Install nse-archives or indian-market-data first.",
        }

    try:
        raw = nse.get_historical_index(
            "NIFTY 50",
            start_date.strftime("%d-%b-%Y"),
            end_date.strftime("%d-%b-%Y"),
        )
    except Exception as exc:
        return {
            "status": "error",
            "message": str(exc),
        }

    if raw is None or raw.empty:
        return {
            "status": "no_data",
            "message": "No NIFTY 50 rows returned.",
        }

    out = raw.copy()
    out.columns = [str(c).strip().lower().replace(" ", "_") for c in out.columns]
    out["trade_date"] = pd.to_datetime(
        out.get("date", out.columns[0]),
        errors="coerce",
    ).dt.normalize()

    path = REAL_DIR / "nifty50_daily.csv"
    out = out.dropna(subset=["trade_date"]).sort_values("trade_date")
    out.to_csv(path, index=False)

    return {
        "status": "ok",
        "rows": len(out),
        "first_date": _date_str(out["trade_date"].min()),
        "last_date": _date_str(out["trade_date"].max()),
        "path": str(path),
    }
