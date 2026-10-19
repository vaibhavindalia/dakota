"""Portfolio Valuation Engine for Dakota.

Provides deterministic, auditable multi-holding calculations:
1. Actual cost basis (Quantity * Average Buy Price) when historical purchase price is known.
2. Estimated cost basis (Quantity * Current Market Price) when purchase price is unrecorded.
3. Current market value (Quantity * Current Price) from live or cached market data.
4. Unrealized P/L and Return % computed strictly on positions with verified purchase information.
5. Reusable portfolio summary aggregation with graceful handling of unpriced or partial positions.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

logger = logging.getLogger(__name__)

# In-memory quote cache with TTL to avoid redundant disk/network calls across rapid UI requests
_QUOTE_CACHE: dict[str, dict[str, Any]] = {}
_QUOTE_CACHE_LOCK = threading.Lock()
QUOTE_CACHE_TTL_SECONDS = 60.0

# Optional universe lookup cache for scrip names
_UNIVERSE_NAME_MAP: dict[str, str] = {}
_UNIVERSE_LOADED = False


def _get_company_name(ticker: str) -> str:
    """Retrieve human-friendly company name from universe.csv if available."""
    global _UNIVERSE_NAME_MAP, _UNIVERSE_LOADED
    clean = str(ticker).upper().strip()

    if not _UNIVERSE_LOADED:
        universe_path = Path(__file__).resolve().parents[2] / "config" / "universe.csv"
        if universe_path.exists():
            try:
                import pandas as pd
                df = pd.read_csv(universe_path)
                for _, row in df.iterrows():
                    tk = str(row.get("ticker", "")).upper().strip()
                    nm = str(row.get("name", "")).strip()
                    if tk and nm:
                        _UNIVERSE_NAME_MAP[tk] = nm
            except Exception as exc:
                logger.debug("Failed loading universe names: %s", exc)
        _UNIVERSE_LOADED = True

    # Fallback mappings for known equities
    known_fallbacks = {
        "WIPRO": "Wipro Limited",
        "ZOMATO": "Zomato Limited",
        "ETERNAL": "Eternal Ltd (Zomato)",
        "CLOUD": "Varanium Cloud Limited",
        "HDFC": "HDFC Bank Limited",
        "HDFCBANK": "HDFC Bank Limited",
        "TCS": "Tata Consultancy Services Limited",
        "RELIANCE": "Reliance Industries Limited",
        "INFY": "Infosys Limited",
    }
    return _UNIVERSE_NAME_MAP.get(clean) or known_fallbacks.get(clean) or f"{clean} Equity"


def get_holding_quote(
    ticker: str,
    exchange: str = "NSE",
    force_refresh: bool = False,
    now_fn: Callable[[], float] | None = None,
) -> dict[str, Any]:
    """Retrieve market quote for a ticker with concurrency safety and in-memory TTL cache.

    Guarantees that a quote lookup failure never crashes the portfolio valuation.
    """
    clean_ticker = str(ticker).upper().strip()
    now_ts = now_fn() if now_fn else time.time()

    with _QUOTE_CACHE_LOCK:
        cached = _QUOTE_CACHE.get(clean_ticker)
        if cached and not force_refresh:
            age = now_ts - cached["cached_at"]
            if age < QUOTE_CACHE_TTL_SECONDS:
                return dict(cached["data"])

    try:
        from src.ingest.market_data import load_ohlcv

        # Load daily historical series (uses yfinance or cached parquet)
        df = load_ohlcv(clean_ticker, start="2023-01-01", allow_synthetic=True, force_refresh=force_refresh)
        if df is None or df.empty:
            quote_data = {
                "ticker": clean_ticker,
                "current_price": None,
                "change": 0.0,
                "change_pct": 0.0,
                "last_traded_at": None,
                "quote_status": "unavailable",
                "source": "empty_series",
                "currency": "INR",
            }
        else:
            df = df.sort_values("date").reset_index(drop=True)
            close_series = df["close"].dropna()
            if close_series.empty:
                quote_data = {
                    "ticker": clean_ticker,
                    "current_price": None,
                    "change": 0.0,
                    "change_pct": 0.0,
                    "last_traded_at": None,
                    "quote_status": "unavailable",
                    "source": "no_valid_close",
                    "currency": "INR",
                }
            else:
                last_price = round(float(close_series.iloc[-1]), 2)
                prev_price = round(float(close_series.iloc[-2]), 2) if len(close_series) >= 2 else last_price
                change = round(last_price - prev_price, 2)
                change_pct = round((change / prev_price) * 100, 2) if prev_price > 0 else 0.0

                last_dt = df["date"].iloc[-1]
                last_dt_str = str(last_dt)[:19]

                src = str(df.get("source", pd.Series(["cache"])).iloc[0]) if "source" in df.columns else "yfinance"
                from src.ingest.market_data import get_daily_cache_status
                cache_stat = get_daily_cache_status(clean_ticker)
                freshness_status = cache_stat.get("status", "cached")
                meta_info = cache_stat.get("meta", {})
                retrieved_at = meta_info.get("retrieved_at")
                last_sync = meta_info.get("last_successful_sync") or retrieved_at

                quote_data = {
                    "ticker": clean_ticker,
                    "current_price": last_price,
                    "change": change,
                    "change_pct": change_pct,
                    "last_traded_at": last_dt_str,
                    "quote_status": freshness_status,
                    "data_status": freshness_status,
                    "provider": meta_info.get("provider", "yfinance"),
                    "retrieved_at": retrieved_at,
                    "market_event_timestamp": last_dt_str,
                    "last_successful_sync": last_sync,
                    "source": src,
                    "currency": "INR",
                }
    except Exception as exc:
        logger.warning("Quote retrieval exception for %s: %s", clean_ticker, exc)
        quote_data = {
            "ticker": clean_ticker,
            "current_price": None,
            "change": 0.0,
            "change_pct": 0.0,
            "last_traded_at": None,
            "quote_status": "unavailable",
            "last_error": str(exc),
            "currency": "INR",
        }

    with _QUOTE_CACHE_LOCK:
        _QUOTE_CACHE[clean_ticker] = {
            "cached_at": now_ts,
            "data": quote_data,
        }

    return dict(quote_data)


def calculate_holding_metrics(
    ticker: str,
    quantity: float,
    average_buy_price: float | None = None,
    current_price: float | None = None,
    exchange: str = "NSE",
    company_name: str | None = None,
    quote_status: str = "fresh",
    quote_timestamp: str | None = None,
    bse_code: str | None = None,
    currency: str = "INR",
) -> dict[str, Any]:
    """Calculate valuation, cost basis (actual vs estimated), and P/L for a single holding.

    Rules:
    - If average_buy_price is known (> 0):
        actual_cost_basis = quantity * average_buy_price
        estimated_cost_basis = None
        cost_basis_type = "actual"
        has_actual_cost = True
    - If average_buy_price is unknown / None / <= 0:
        actual_cost_basis = None
        has_actual_cost = False
        if current_price is known (> 0):
            estimated_cost_basis = quantity * current_price
            cost_basis_type = "estimated"
        else:
            estimated_cost_basis = None
            cost_basis_type = "unavailable"
    - Current Market Value = quantity * current_price (if current_price > 0)
    - Unrealized P/L = current_value - actual_cost_basis (ONLY when actual_cost_basis is known)
    - Unrealized Return % = (unrealized_pnl / actual_cost_basis) * 100 (ONLY when actual_cost_basis is known)
    - Never calculate unrealized P/L or Return % on estimated cost basis!
    """
    clean_ticker = str(ticker).upper().strip()
    qty = float(quantity) if quantity is not None else 0.0
    name = company_name or _get_company_name(clean_ticker)

    # Sanitize average buy price
    valid_buy_price: float | None = None
    if average_buy_price is not None:
        try:
            val = float(average_buy_price)
            if val > 0:
                valid_buy_price = round(val, 2)
        except (ValueError, TypeError):
            valid_buy_price = None

    # Sanitize current price
    valid_current_price: float | None = None
    if current_price is not None:
        try:
            val = float(current_price)
            if val > 0:
                valid_current_price = round(val, 2)
        except (ValueError, TypeError):
            valid_current_price = None

    # 1. Market value
    current_value: float | None = None
    if valid_current_price is not None:
        current_value = round(qty * valid_current_price, 2)

    # 2. Cost basis determination
    actual_cost_basis: float | None = None
    estimated_cost_basis: float | None = None
    has_actual_cost = False

    if valid_buy_price is not None:
        has_actual_cost = True
        actual_cost_basis = round(qty * valid_buy_price, 2)
        estimated_cost_basis = None
        cost_basis_type = "actual"
    else:
        has_actual_cost = False
        actual_cost_basis = None
        if valid_current_price is not None:
            estimated_cost_basis = round(qty * valid_current_price, 2)
            cost_basis_type = "estimated"
        else:
            estimated_cost_basis = None
            cost_basis_type = "unavailable"

    # 3. Unrealized P/L and Return % (Strictly requires actual purchase cost)
    unrealized_pnl: float | None = None
    unrealized_return_pct: float | None = None

    if has_actual_cost and actual_cost_basis is not None and current_value is not None:
        unrealized_pnl = round(current_value - actual_cost_basis, 2)
        if actual_cost_basis > 0:
            unrealized_return_pct = round((unrealized_pnl / actual_cost_basis) * 100, 2)

    # Valuation status descriptor
    if cost_basis_type == "actual":
        valuation_status = "verified_cost"
    elif cost_basis_type == "estimated":
        valuation_status = "estimated_cost_basis"
    else:
        valuation_status = "unpriced"

    return {
        "ticker": clean_ticker,
        "name": name,
        "exchange": str(exchange).upper().strip(),
        "bse_code": bse_code,
        "quantity": qty,
        "average_buy_price": valid_buy_price,
        "avg_buy_price": valid_buy_price,
        "current_price": valid_current_price,
        "current_value": current_value,
        "market_value": current_value,  # alias
        "actual_cost_basis": actual_cost_basis,
        "estimated_cost_basis": estimated_cost_basis,
        "has_actual_cost": has_actual_cost,
        "cost_basis_type": cost_basis_type,
        "valuation_status": valuation_status,
        "unrealized_pnl": unrealized_pnl,
        "unrealized_return_pct": unrealized_return_pct,
        "quote_status": quote_status,
        "quote_timestamp": quote_timestamp,
        "currency": currency,
        # Legacy backward-compatibility fields:
        "invested_value": actual_cost_basis if actual_cost_basis is not None else 0.0,
    }


def calculate_portfolio_summary(holdings_metrics: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate individual holding metrics into a comprehensive portfolio summary."""
    total_positions = len(holdings_metrics)

    # Actual cost basis: sum of positions with recorded buy prices
    actual_costs = [h["actual_cost_basis"] for h in holdings_metrics if h.get("actual_cost_basis") is not None]
    total_actual_cost = round(sum(actual_costs), 2) if actual_costs else 0.0

    # Estimated cost basis: sum of estimated positions missing buy prices
    est_costs = [h["estimated_cost_basis"] for h in holdings_metrics if h.get("estimated_cost_basis") is not None]
    total_estimated_cost = round(sum(est_costs), 2) if est_costs else 0.0

    # Current market value: sum of positions with valid quotes
    market_vals = [h["current_value"] for h in holdings_metrics if h.get("current_value") is not None]
    total_market_value = round(sum(market_vals), 2) if market_vals else 0.0

    # Unrealized P/L: only positions with verified buy prices AND current quotes
    pnl_holdings = [h for h in holdings_metrics if h.get("unrealized_pnl") is not None]
    if pnl_holdings:
        total_unrealized_pnl = round(sum(h["unrealized_pnl"] for h in pnl_holdings), 2)
        base_cost = sum(h["actual_cost_basis"] for h in pnl_holdings if h.get("actual_cost_basis"))
        total_unrealized_return_pct = (
            round((total_unrealized_pnl / base_cost) * 100, 2) if base_cost > 0 else 0.0
        )
    else:
        total_unrealized_pnl = None
        total_unrealized_return_pct = None

    # Counts and health status
    unpriced_count = sum(1 for h in holdings_metrics if h.get("current_price") is None)
    missing_buy_price_count = sum(1 for h in holdings_metrics if not h.get("has_actual_cost"))
    verified_buy_price_count = sum(1 for h in holdings_metrics if h.get("has_actual_cost"))
    is_partial_valuation = unpriced_count > 0

    as_of = datetime.now(timezone.utc).isoformat()

    return {
        "total_positions": total_positions,
        "total_actual_cost": total_actual_cost,
        "total_estimated_cost": total_estimated_cost,
        "total_market_value": total_market_value,
        "total_unrealized_pnl": total_unrealized_pnl,
        "total_unrealized_return_pct": total_unrealized_return_pct,
        "unpriced_count": unpriced_count,
        "missing_buy_price_count": missing_buy_price_count,
        "verified_buy_price_count": verified_buy_price_count,
        "is_partial_valuation": is_partial_valuation,
        "as_of": as_of,
        "currency": "INR",
        # Legacy compatibility aliases:
        "total_invested": total_actual_cost,
        "count": total_positions,
    }


def enrich_and_value_portfolio(
    items: list[dict[str, Any]],
    risk_assessor: Callable[[str], dict[str, Any]] | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Full portfolio enrichment pipeline: quote lookup + calculation + risk assessment + summary."""
    enriched: list[dict[str, Any]] = []

    for raw in items:
        ticker = str(raw.get("ticker", "")).upper().strip()
        exchange = str(raw.get("exchange", "NSE")).upper().strip()
        bse_code = raw.get("bse_code")
        quantity = float(raw.get("quantity") or 0.0)

        # Handle various legacy buy price keys
        avg_buy_price = (
            raw.get("average_buy_price")
            if raw.get("average_buy_price") is not None
            else raw.get("avg_buy_price", raw.get("averagePrice"))
        )

        # Retrieve quote
        quote = get_holding_quote(ticker, exchange=exchange, force_refresh=force_refresh)
        current_price = quote.get("current_price")
        quote_status = quote.get("quote_status", "fresh")
        quote_timestamp = quote.get("last_traded_at")

        # Calculate metrics
        metrics = calculate_holding_metrics(
            ticker=ticker,
            quantity=quantity,
            average_buy_price=avg_buy_price,
            current_price=current_price,
            exchange=exchange,
            quote_status=quote_status,
            quote_timestamp=quote_timestamp,
            bse_code=bse_code,
        )

        # Incorporate price change and market freshness info from quote
        metrics["change"] = quote.get("change", 0.0)
        metrics["change_pct"] = quote.get("change_pct", 0.0)
        metrics["data_status"] = quote.get("data_status", quote_status)
        metrics["provider"] = quote.get("provider", "yfinance")
        metrics["retrieved_at"] = quote.get("retrieved_at")
        metrics["market_event_timestamp"] = quote.get("market_event_timestamp")
        metrics["last_successful_sync"] = quote.get("last_successful_sync")

        # Risk assessment
        if risk_assessor:
            try:
                metrics["risk"] = risk_assessor(ticker)
            except Exception:
                metrics["risk"] = {"score": None, "band": "Unavailable", "verdict": ""}
        else:
            metrics["risk"] = raw.get("risk", {"score": None, "band": "Unavailable", "verdict": ""})

        enriched.append(metrics)

    summary = calculate_portfolio_summary(enriched)

    return {
        "holdings": enriched,
        "summary": summary,
        **summary,  # Spread summary at top-level for backwards compatibility
    }
