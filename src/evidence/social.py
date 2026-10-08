"""Unified social intelligence layer for Dakota.

Providers:
    Reddit
    X
    Instagram
    StockTwits
    Telegram ingestion metadata

Sentiment from the local FinBERT layer is attached as evidence. It does not
become a direct manipulation-risk score modifier.
"""
from __future__ import annotations

from typing import Any

from src.connectors.instagram import search_instagram
from src.connectors.reddit_api import search_reddit_real
from src.connectors.x_api import search_x

try:
    from src.evidence.stocktwits import search_stocktwits
except Exception:
    search_stocktwits = None

try:
    from src.evidence.sentiment_local import analyze_bulk_sentiment
except Exception:
    analyze_bulk_sentiment = None


def _collect_texts(provider: dict[str, Any], *fields: str) -> list[str]:
    texts: list[str] = []
    for item in provider.get("results") or provider.get("messages") or []:
        if not isinstance(item, dict):
            continue
        for field in fields:
            value = str(item.get(field) or "").strip()
            if value:
                texts.append(value)
    return texts


def collect_social_evidence(ticker: str) -> dict[str, Any]:
    reddit = search_reddit_real(ticker)
    x = search_x(ticker)
    instagram = search_instagram(ticker)
    stocktwits = (
        search_stocktwits(ticker)
        if search_stocktwits is not None
        else {
            "status": "not_configured",
            "provider": "StockTwits",
            "messages": [],
            "results": [],
            "observations": [],
            "error": "StockTwits adapter unavailable",
        }
    )

    texts: list[str] = []
    texts.extend(_collect_texts(reddit, "title", "selftext"))
    texts.extend(_collect_texts(x, "text", "body"))
    texts.extend(_collect_texts(instagram, "caption", "text"))
    texts.extend(_collect_texts(stocktwits, "body", "text"))

    sentiment: dict[str, Any] = {
        "positive": 0,
        "negative": 0,
        "neutral": 0,
        "total": 0,
        "status": "not_configured",
    }

    if analyze_bulk_sentiment is not None:
        try:
            sentiment = analyze_bulk_sentiment([t for t in texts if t.strip()])
            sentiment["status"] = "connected"
        except Exception as exc:
            sentiment = {
                "positive": 0,
                "negative": 0,
                "neutral": 0,
                "total": len(texts),
                "status": "error",
                "error": str(exc),
            }

    return {
        "reddit": reddit,
        "x": x,
        "instagram": instagram,
        "stocktwits": stocktwits,
        "bulk_sentiment_analysis": sentiment,
        "telegram": {
            "status": "ingestion_connector",
            "results": [],
            "observations": [],
            "error": None,
        },
    }
