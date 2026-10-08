"""Dakota's full tip investigation orchestration layer."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd

from src.campaign.analyzer import analyze_tip_coordination
from src.campaign.store import TipStore
from src.connectors.company import collect_company_evidence
from src.evidence.aggregate import aggregate_scores
from src.evidence.news import search_news
from src.evidence.social import collect_social_evidence
from src.market.history import load_history
from src.market.index_context import index_relative_return
from src.market.indicators import add_indicators, latest_indicator_snapshot, market_signal_reasons
from src.tipcheck.parser import parse_tip




_COMMON_WORDS = {
    "BUY", "SELL", "HOLD", "TARGET", "PRICE", "TODAY", "TOMORROW",
    "NOW", "URGENT", "GUARANTEED", "RETURN", "RETURNS", "TARGETS",
    "STOCK", "SHARE", "SHARES", "RS", "INR", "RUPEE", "RUPIX",
    "AT", "THE", "AND", "FOR", "WITH", "THIS", "THAT", "WILL",
    "FROM", "TO", "ON", "OF", "A", "AN", "IS", "IT", "RUN",
    "RUNNING", "BREAKOUT", "MULTIBAGGER", "IMMEDIATELY", "TOMORROW",
}


def _fallback_tickers(raw_text: str) -> list[str]:
    import re

    candidates = re.findall(r"(?<![A-Z0-9])([A-Z]{2,12})(?![A-Z0-9])", raw_text.upper())
    result: list[str] = []
    for token in candidates:
        if token in _COMMON_WORDS:
            continue
        if token not in result:
            result.append(token)
    return result[:5]


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return str(value)


def _series_for_chart(df: pd.DataFrame, limit: int = 120) -> list[dict[str, Any]]:
    cols = ["date", "close", "volume", "ema_20", "sma_50", "rsi_14"]
    available = [c for c in cols if c in df.columns]
    if not available:
        return []
    tail = df.tail(limit)[available].copy()
    result: list[dict[str, Any]] = []
    for _, row in tail.iterrows():
        item = {
            "date": row["date"].strftime("%Y-%m-%d") if pd.notna(row["date"]) else None
        }
        for col in available[1:]:
            item[col] = _json_value(row[col])
        result.append(item)
    return result


def _tip_observations(parsed) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for category, hits in parsed.markers_found.items():
        observations.append({
            "signal": f"tip_{category}",
            "severity": "medium" if category != "urgency_pressure" else "high",
            "text": f"Tip parser found {len(hits)} marker(s) in '{category}'.",
        })
    if parsed.urgency:
        observations.append({
            "signal": "tip_urgency",
            "severity": "medium",
            "text": "The tip contains urgency language.",
        })
    if parsed.price_target is not None:
        observations.append({
            "signal": "tip_price_target",
            "severity": "low",
            "text": f"The tip contains a price target of ₹{parsed.price_target:,.2f}.",
        })
    if parsed.sebi_reg_claimed:
        observations.append({
            "signal": "tip_sebi_claim",
            "severity": "low",
            "text": "The tip contains a SEBI-registration claim; registration is not verified by this investigation.",
        })
    return observations


def _flatten_social_observations(social: dict[str, Any]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for source in ("reddit", "x", "instagram", "telegram"):
        item = social.get(source) or {}
        if isinstance(item, dict):
            observations.extend(item.get("observations") or [])
    return observations


def _web_enabled() -> bool:
    return os.getenv("DAKOTA_WEB_EVIDENCE", "1").strip().lower() not in {"0", "false", "no", "off"}


def _external(ticker: str) -> dict[str, Any]:
    if not _web_enabled():
        return {
            "news": {"status": "disabled", "articles": [], "observations": [], "error": None},
            "social": {},
            "company": {"status": "disabled", "observations": [], "nse": {}, "bse": {}},
        }
    news = search_news(ticker)
    social = collect_social_evidence(ticker)
    company = collect_company_evidence(ticker)
    return {"news": news, "social": social, "company": company}


def _source_status(exchange: str, external: dict[str, Any], index_data: dict[str, Any]) -> dict[str, str]:
    news = external.get("news") or {}
    social = external.get("social") or {}
    company = external.get("company") or {}
    return {
        "nse": "connected_local_cache" if exchange == "NSE" else "not_used",
        "bse": "connected_local_cache" if exchange == "BSE" else "not_used",
        "news": str(news.get("status") or "unknown"),
        "reddit": str((social.get("reddit") or {}).get("status") or "unknown"),
        "x": str((social.get("x") or {}).get("status") or "unknown"),
        "instagram": str((social.get("instagram") or {}).get("status") or "unknown"),
        "telegram": "ingestion_connector",
        "company": str(company.get("status") or "unknown"),
        "index": str(index_data.get("status") or "unknown"),
    }


def investigate_tip(raw_tip: str, data_root: str | Path = "data/raw", source_label: str = "manual") -> dict[str, Any]:
    parsed = parse_tip(raw_tip)
    tickers = list(parsed.tickers)
    if not tickers:
        tickers = _fallback_tickers(parsed.clean_text)

    if not tickers:
        return {
            "status": "needs_ticker",
            "message": "No stock ticker was confidently extracted from the tip.",
            "tip": {
                "tickers": [],
                "price_target": parsed.price_target,
                "markers_found": parsed.markers_found,
                "n_scam_markers": parsed.n_scam_markers,
                "urgency": parsed.urgency,
                "sebi_reg_claimed": parsed.sebi_reg_claimed,
            },
        }

    store = TipStore(Path(data_root).parent / "dakota.db")
    investigations: list[dict[str, Any]] = []

    for ticker in tickers:
        clean_text = parsed.clean_text
        store.add(ticker, clean_text, source_label)
        coordination = analyze_tip_coordination(store, ticker, clean_text, source_label)
        external = _external(ticker)
        news = external.get("news") or {}
        social = external.get("social") or {}
        company = external.get("company") or {}
        company_obs = company.get("observations") or []
        social_obs = _flatten_social_observations(social)

        market_candidates: list[tuple[str, pd.DataFrame]] = []
        for exchange in ("NSE", "BSE"):
            hist = load_history(ticker, exchange, data_root=data_root)
            if not hist.empty:
                market_candidates.append((exchange, hist))

        tip_obs = _tip_observations(parsed)
        coord_obs = coordination.get("observations") or []

        if not market_candidates:
            risk = aggregate_scores(
                tip_observations=tip_obs + coord_obs,
                market_observations=[],
                news_observations=(news.get("observations") or []) + company_obs,
                social_observations=social_obs,
            )
            investigations.append({
                "ticker": ticker,
                "status": "market_data_missing",
                "market": None,
                "coordination": coordination,
                "evidence": {"news": news, "social": social, "company": company, "index": {"status": "not_available"}},
                "risk": risk,
                "source_status": _source_status("UNKNOWN", external, {"status": "not_available"}),
            })
            continue

        exchange, history = market_candidates[0]
        enriched = add_indicators(history)
        snapshot = latest_indicator_snapshot(enriched)
        market_obs = market_signal_reasons(snapshot)
        index_data = index_relative_return(history, index_name="NIFTY 50", data_root=data_root)
        market_obs = market_obs + (index_data.get("observations") or [])

        risk = aggregate_scores(
            tip_observations=tip_obs + coord_obs,
            market_observations=market_obs,
            news_observations=(news.get("observations") or []) + company_obs,
            social_observations=social_obs,
        )

        investigations.append({
            "ticker": ticker,
            "status": "ok",
            "exchange": exchange,
            "market": {
                "data_points": int(len(enriched)),
                "first_date": enriched["date"].min().strftime("%Y-%m-%d"),
                "last_date": enriched["date"].max().strftime("%Y-%m-%d"),
                "snapshot": snapshot,
                "observations": market_obs,
                "chart": _series_for_chart(enriched),
            },
            "coordination": coordination,
            "evidence": {
                "news": news,
                "social": social,
                "company": company,
                "index": index_data,
            },
            "risk": risk,
            "investigation_score_partial": risk["score"],
            "score_reasons": risk["reasons"],
            "source_status": _source_status(exchange, external, index_data),
        })

    return {
        "status": "ok",
        "tip": {
            "tickers": tickers,
            "price_target": parsed.price_target,
            "markers_found": parsed.markers_found,
            "n_scam_markers": parsed.n_scam_markers,
            "urgency": parsed.urgency,
            "sebi_reg_claimed": parsed.sebi_reg_claimed,
            "sebi_reg_number": parsed.sebi_reg_number,
            "source": source_label,
        },
        "investigations": investigations,
        "next_layers": [
            "historical campaign graph and near-duplicate clustering",
            "NSE/BSE surveillance / ASM / GSM context",
            "fundamentals and financial-integrity features",
            "authorized Telegram channel monitoring",
            "authorized WhatsApp Cloud API ingestion",
        ],
        "disclaimer": (
            "Dakota reports risk indicators present in available evidence. It does not determine fraud and does not provide buy/sell advice. Missing connectors are not treated as clean evidence."
        ),
    }
