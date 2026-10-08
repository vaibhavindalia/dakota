"""Real exchange-data sync helpers.

The project already uses the unofficial but current `nse` and `bse` Python
clients to download public exchange reports into data/raw. Keep calls throttled,
cache files, and reuse them instead of repeatedly downloading the same date.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


def _call_method(obj: Any, candidates: list[str], trade_date: datetime) -> Any:
    for name in candidates:
        method = getattr(obj, name, None)
        if not callable(method):
            continue
        for kwargs in (
            {"date": trade_date},
            {"trade_date": trade_date.strftime("%d-%m-%Y")},
            {"trade_date": trade_date.strftime("%Y-%m-%d")},
        ):
            try:
                return method(**kwargs)
            except TypeError:
                continue
    return None


def sync_nse(trade_date: date, root: str | Path = "data/raw/nse") -> dict[str, Any]:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    try:
        from nse import NSE  # type: ignore
    except Exception as exc:
        return {"status": "package_missing", "exchange": "NSE", "error": str(exc)}

    try:
        dt = datetime.combine(trade_date, datetime.min.time())
        with NSE(download_folder=root, server=False) as client:
            results = {}
            results["bhavcopy"] = _call_method(client, ["equityBhavcopy", "equity_bhavcopy"], dt)
            results["delivery"] = _call_method(client, ["deliveryBhavcopy", "delivery_bhavcopy"], dt)
            results["indices"] = _call_method(client, ["indicesBhavcopy", "indices_bhavcopy"], dt)
            results["priceband"] = _call_method(client, ["pricebandBhavcopy", "priceBandBhavcopy", "priceband_bhavcopy"], dt)
        return {
            "status": "connected",
            "exchange": "NSE",
            "trade_date": trade_date.isoformat(),
            "results": {k: str(v) if v is not None else None for k, v in results.items()},
        }
    except Exception as exc:
        return {"status": "error", "exchange": "NSE", "trade_date": trade_date.isoformat(), "error": str(exc)}


def sync_bse(trade_date: date, root: str | Path = "data/raw/bse") -> dict[str, Any]:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    try:
        from bse import BSE  # type: ignore
    except Exception as exc:
        return {"status": "package_missing", "exchange": "BSE", "error": str(exc)}

    try:
        dt = datetime.combine(trade_date, datetime.min.time())
        with BSE(download_folder=root) as client:
            result = _call_method(client, ["equityBhavcopy", "equity_bhavcopy", "bhavcopy"], dt)
        return {
            "status": "connected" if result is not None else "no_data_returned",
            "exchange": "BSE",
            "trade_date": trade_date.isoformat(),
            "result": str(result) if result is not None else None,
        }
    except Exception as exc:
        return {"status": "error", "exchange": "BSE", "trade_date": trade_date.isoformat(), "error": str(exc)}


def sync_date(trade_date: date) -> dict[str, Any]:
    return {
        "nse": sync_nse(trade_date),
        "bse": sync_bse(trade_date),
    }


def latest_weekday() -> date:
    current = date.today()
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current
