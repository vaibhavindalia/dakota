"""Load cached NSE/BSE daily history collected by Dakota.

This module intentionally reads local exchange reports already downloaded into
``data/raw``. It does not scrape websites at request time.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd


PRICE_REQUIRED = {"open", "high", "low", "close", "volume"}


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def _find_col(df: pd.DataFrame, *names: str) -> str | None:
    targets = {_norm(n) for n in names}
    for col in df.columns:
        if _norm(col) in targets:
            return col
    return None


def _parse_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", dayfirst=True).dt.normalize()


def _parse_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(",", "", regex=False).str.replace("₹", "", regex=False).str.strip(),
        errors="coerce",
    )


def _read_csv(path: Path) -> pd.DataFrame:
    for encoding in ("utf-8", "latin1"):
        try:
            return pd.read_csv(path, low_memory=False, encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("csv", b"", 0, 1, f"Unable to decode {path}")


def _candidate_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.csv")) if root.exists() else []


def _load_nse(ticker: str, root: Path) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    deliveries: list[pd.DataFrame] = []

    for path in _candidate_files(root):
        try:
            raw = _read_csv(path)
        except Exception:
            continue
        date_col = _find_col(raw, "TradDt", "Trade Date")
        symbol_col = _find_col(raw, "TckrSymb", "SYMBOL")
        open_col = _find_col(raw, "OpnPric", "OPEN")
        high_col = _find_col(raw, "HghPric", "HIGH")
        low_col = _find_col(raw, "LwPric", "LOW")
        close_col = _find_col(raw, "ClsPric", "CLOSE")
        vol_col = _find_col(raw, "TtlTradgVol", "TOTAL TRADED QUANTITY", "VOLUME")
        prev_col = _find_col(raw, "PrvsClsgPric", "PREV_CLOSE", "PREVIOUS CLOSE")

        if symbol_col and open_col and high_col and low_col and close_col and vol_col:
            match = raw[raw[symbol_col].astype(str).str.upper().str.strip() == ticker.upper().strip()].copy()
            if not match.empty:
                item = pd.DataFrame({
                    "date": _parse_date(match[date_col]) if date_col else pd.Series(pd.NaT, index=match.index),
                    "open": _parse_number(match[open_col]),
                    "high": _parse_number(match[high_col]),
                    "low": _parse_number(match[low_col]),
                    "close": _parse_number(match[close_col]),
                    "volume": _parse_number(match[vol_col]),
                    "previous_close": _parse_number(match[prev_col]) if prev_col else pd.NA,
                    "source_file": path.name,
                })
                rows.append(item)
                continue

        deliv_symbol = _find_col(raw, "SYMBOL")
        deliv_date = _find_col(raw, "DATE", "TradDt")
        qty_col = _find_col(raw, "DELIV_QTY", "DELIVERY QTY")
        pct_col = _find_col(raw, "DELIV_PER", "DELV. PER.", "DELIVERY PERCENTAGE")
        if deliv_symbol and (qty_col or pct_col):
            match = raw[raw[deliv_symbol].astype(str).str.upper().str.strip() == ticker.upper().strip()].copy()
            if not match.empty:
                deliveries.append(pd.DataFrame({
                    "date": _parse_date(match[deliv_date]) if deliv_date else pd.Series(pd.NaT, index=match.index),
                    "delivery_quantity": _parse_number(match[qty_col]) if qty_col else pd.NA,
                    "delivery_pct": _parse_number(match[pct_col]) if pct_col else pd.NA,
                }))

    if not rows:
        return pd.DataFrame()

    out = pd.concat(rows, ignore_index=True)
    out = out.dropna(subset=["date", "close"]).drop_duplicates(subset=["date"], keep="last")
    if deliveries:
        d = pd.concat(deliveries, ignore_index=True).dropna(subset=["date"]).drop_duplicates(subset=["date"], keep="last")
        out = out.merge(d, on="date", how="left")
    return out.sort_values("date").reset_index(drop=True)


def _load_bse(ticker: str, root: Path) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    deliveries: list[pd.DataFrame] = []
    ticker_upper = ticker.upper().strip()

    for path in _candidate_files(root):
        try:
            raw = _read_csv(path)
        except Exception:
            continue

        date_col = _find_col(raw, "TradDt", "DATE", "Trade Date")
        symbol_col = _find_col(raw, "TckrSymb", "SYMBOL")
        code_col = _find_col(raw, "FinInstrmId", "SCRIP CODE", "SC_CODE")
        open_col = _find_col(raw, "OpnPric", "OPEN")
        high_col = _find_col(raw, "HghPric", "HIGH")
        low_col = _find_col(raw, "LwPric", "LOW")
        close_col = _find_col(raw, "ClsPric", "CLOSE")
        vol_col = _find_col(raw, "TtlTradgVol", "DAY'S VOLUME", "VOLUME")
        prev_col = _find_col(raw, "PrvsClsgPric", "PREV_CLOSE", "PREVIOUS CLOSE")

        if open_col and high_col and low_col and close_col and vol_col and (symbol_col or code_col):
            mask = pd.Series(False, index=raw.index)
            if symbol_col:
                mask = mask | raw[symbol_col].astype(str).str.upper().str.strip().eq(ticker_upper)
            if code_col and ticker.isdigit():
                mask = mask | raw[code_col].astype(str).str.replace(".0", "", regex=False).str.strip().eq(ticker)
            match = raw[mask].copy()
            if not match.empty:
                rows.append(pd.DataFrame({
                    "date": _parse_date(match[date_col]) if date_col else pd.Series(pd.NaT, index=match.index),
                    "open": _parse_number(match[open_col]),
                    "high": _parse_number(match[high_col]),
                    "low": _parse_number(match[low_col]),
                    "close": _parse_number(match[close_col]),
                    "volume": _parse_number(match[vol_col]),
                    "previous_close": _parse_number(match[prev_col]) if prev_col else pd.NA,
                    "source_file": path.name,
                }))
                continue

        code = _find_col(raw, "SCRIP CODE")
        date = _find_col(raw, "DATE")
        qty = _find_col(raw, "DELIVERY QTY")
        pct = _find_col(raw, "DELV. PER.")
        if code and (qty or pct):
            # BSE delivery files are code based. The investigator can pass a
            # numeric code as ticker when needed; symbol-based matching is
            # intentionally not guessed here.
            if ticker.isdigit():
                match = raw[raw[code].astype(str).str.replace(".0", "", regex=False).str.strip().eq(ticker)].copy()
                if not match.empty:
                    deliveries.append(pd.DataFrame({
                        "date": _parse_date(match[date]) if date else pd.Series(pd.NaT, index=match.index),
                        "delivery_quantity": _parse_number(match[qty]) if qty else pd.NA,
                        "delivery_pct": _parse_number(match[pct]) if pct else pd.NA,
                    }))

    if not rows:
        return pd.DataFrame()

    out = pd.concat(rows, ignore_index=True)
    out = out.dropna(subset=["date", "close"]).drop_duplicates(subset=["date"], keep="last")
    if deliveries:
        d = pd.concat(deliveries, ignore_index=True).dropna(subset=["date"]).drop_duplicates(subset=["date"], keep="last")
        out = out.merge(d, on="date", how="left")
    return out.sort_values("date").reset_index(drop=True)


def load_history(ticker: str, exchange: str, data_root: str | Path = "data/raw") -> pd.DataFrame:
    """Load all locally cached history for a ticker/exchange."""
    exchange = exchange.upper().strip()
    root = Path(data_root) / exchange.lower()
    if exchange == "NSE":
        return _load_nse(ticker, root)
    if exchange == "BSE":
        return _load_bse(ticker, root)
    raise ValueError("exchange must be NSE or BSE")
