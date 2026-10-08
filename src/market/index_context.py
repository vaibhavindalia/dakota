"""Index-relative context for Dakota.

Uses local NSE index bhavcopy/history when present and optionally falls back to
an nse client for a short historical window.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def _norm(value: Any) -> str:
    return "".join(ch.lower() for ch in str(value) if ch.isalnum())


def _find(df: pd.DataFrame, *names: str) -> str | None:
    targets = {_norm(x) for x in names}
    for col in df.columns:
        if _norm(col) in targets:
            return col
    return None


def load_local_index(index_name: str = "NIFTY 50", data_root: str | Path = "data/raw") -> pd.DataFrame:
    root = Path(data_root) / "nse"
    if not root.exists():
        return pd.DataFrame()

    rows: list[pd.DataFrame] = []
    for path in sorted(root.rglob("*.csv")):
        try:
            df = pd.read_csv(path, low_memory=False)
        except Exception:
            continue
        name_col = _find(df, "Index Name", "IndexName", "Index")
        close_col = _find(df, "Closing Index Value", "ClosingIndexValue", "Close")
        date_col = _find(df, "Index Date", "Date", "TradDt")
        if not (name_col and close_col and date_col):
            continue
        name = df[name_col].astype(str).str.upper().str.strip()
        match = df[name.eq(index_name.upper().strip())].copy()
        if match.empty:
            continue
        rows.append(pd.DataFrame({
            "date": pd.to_datetime(match[date_col], errors="coerce", dayfirst=True).dt.normalize(),
            "close": pd.to_numeric(match[close_col], errors="coerce"),
        }))

    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True).dropna().drop_duplicates("date").sort_values("date").reset_index(drop=True)


def index_relative_return(stock_history: pd.DataFrame, *, index_name: str = "NIFTY 50", data_root: str | Path = "data/raw") -> dict[str, Any]:
    idx = load_local_index(index_name, data_root=data_root)
    if idx.empty or stock_history.empty:
        return {
            "status": "missing_index_history",
            "index": index_name,
            "observations": [],
            "series": [],
        }

    stock = stock_history[["date", "close"]].copy().dropna().sort_values("date")
    merged = stock.merge(idx, on="date", how="inner", suffixes=("_stock", "_index"))
    if len(merged) < 2:
        return {
            "status": "insufficient_overlap",
            "index": index_name,
            "observations": [],
            "series": [],
        }

    merged["stock_return_20d"] = merged["close_stock"].pct_change(20) * 100
    merged["index_return_20d"] = merged["close_index"].pct_change(20) * 100
    latest = merged.iloc[-1]

    observations: list[dict[str, Any]] = []
    stock_ret = latest.get("stock_return_20d")
    index_ret = latest.get("index_return_20d")

    if pd.notna(stock_ret) and pd.notna(index_ret):
        relative = float(stock_ret - index_ret)
        if relative >= 25:
            observations.append({
                "signal": "index_relative_strength",
                "severity": "high",
                "text": f"20-session stock return is {relative:.1f} percentage points above {index_name}.",
            })
        elif relative >= 12:
            observations.append({
                "signal": "index_relative_strength",
                "severity": "medium",
                "text": f"20-session stock return is {relative:.1f} percentage points above {index_name}.",
            })

    return {
        "status": "connected",
        "index": index_name,
        "latest_stock_return_20d": float(stock_ret) if pd.notna(stock_ret) else None,
        "latest_index_return_20d": float(index_ret) if pd.notna(index_ret) else None,
        "observations": observations,
        "series": merged.tail(120).assign(
            date=merged.tail(120)["date"].dt.strftime("%Y-%m-%d")
        ).to_dict(orient="records"),
    }
