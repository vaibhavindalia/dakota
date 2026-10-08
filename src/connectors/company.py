"""Company/corporate-evidence connector using exchange-backed Python clients.

NSE and BSE publish corporate announcements and shareholding information. This
adapter deliberately uses optional packages so Dakota can still run from cached
exchange files when a connector package is unavailable.
"""
from __future__ import annotations

import inspect
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "to_dict"):
        try:
            return value.to_dict()
        except Exception:
            pass
    if hasattr(value, "to_dicts"):
        try:
            return value.to_dicts()
        except Exception:
            pass
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "__dict__"):
        return str(value)
    return str(value)


def _call_flexible(obj: Any, name_candidates: list[str], ticker: str, **kwargs: Any) -> Any:
    for name in name_candidates:
        fn = getattr(obj, name, None)
        if not callable(fn):
            continue
        try:
            sig = inspect.signature(fn)
            accepted = {
                k: v
                for k, v in kwargs.items()
                if k in sig.parameters
            }
            if ticker:
                for key in ("symbol", "ticker", "scrip", "scripcode"):
                    if key in sig.parameters and key not in accepted:
                        accepted[key] = ticker
                        break
            return fn(**accepted)
        except Exception:
            continue
    return None


def _nse(ticker: str) -> dict[str, Any]:
    try:
        from nse import NSE  # type: ignore
    except Exception as exc:
        return {"status": "package_missing", "error": str(exc), "announcements": [], "shareholding": []}

    try:
        root = Path("data")
        with NSE(download_folder=root, server=False) as client:
            announcements = _call_flexible(client, ["announcements"], ticker, symbol=ticker)
            shareholding = _call_flexible(client, ["shareholding"], ticker, symbol=ticker)

        return {
            "status": "connected",
            "source": "nse",
            "announcements": _jsonable(announcements) if announcements is not None else [],
            "shareholding": _jsonable(shareholding) if shareholding is not None else [],
            "error": None,
        }
    except Exception as exc:
        return {"status": "error", "source": "nse", "announcements": [], "shareholding": [], "error": str(exc)}


def _bse(ticker: str, bse_code: str | None = None) -> dict[str, Any]:
    try:
        from bse import BSE  # type: ignore
    except Exception as exc:
        return {"status": "package_missing", "error": str(exc), "announcements": []}

    try:
        with BSE(download_folder=Path("data")) as client:
            code = bse_code or _call_flexible(client, ["getScripCode"], ticker, symbol=ticker)
            announcements = _call_flexible(
                client,
                ["announcements"],
                str(code or ticker),
                scripcode=str(code) if code else None,
            )
        return {
            "status": "connected",
            "source": "bse",
            "scrip_code": str(code) if code else None,
            "announcements": _jsonable(announcements) if announcements is not None else [],
            "error": None,
        }
    except Exception as exc:
        return {"status": "error", "source": "bse", "announcements": [], "error": str(exc)}


def collect_company_evidence(ticker: str, bse_code: str | None = None) -> dict[str, Any]:
    ticker = ticker.upper().strip()
    fetched_at = datetime.now(timezone.utc).isoformat()
    nse = _nse(ticker)
    bse = _bse(ticker, bse_code=bse_code)

    observations: list[dict[str, Any]] = []

    for source_name, source in (("NSE", nse), ("BSE", bse)):
        if source.get("status") == "connected":
            announcements = source.get("announcements")
            if isinstance(announcements, list) and len(announcements) >= 10:
                observations.append({
                    "signal": f"{source_name.lower()}_announcement_volume",
                    "severity": "low",
                    "text": f"{source_name} connector returned a dense set of recent corporate announcements; individual filings require source review.",
                })

    return {
        "status": "connected" if any(x.get("status") == "connected" for x in (nse, bse)) else "unavailable",
        "fetched_at": fetched_at,
        "nse": nse,
        "bse": bse,
        "observations": observations,
        "error": None,
    }
