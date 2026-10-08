"""Official X API recent-search connector.

Uses X API v2 recent search when X_BEARER_TOKEN is configured. The endpoint
covers recent posts; current X search access and pricing are controlled by X.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from src.connectors.config import env

URL = "https://api.x.com/2/tweets/search/recent"

HYPE_TERMS = {
    "multibagger",
    "guaranteed",
    "target",
    "upper circuit",
    "breakout",
    "rocket",
    "buy now",
    "operator",
    "telegram",
    "whatsapp",
}


def search_x(ticker: str, *, max_results: int = 50, days: int = 7, timeout: float = 10.0) -> dict[str, Any]:
    token = env("X_BEARER_TOKEN")
    ticker = ticker.upper().strip()
    fetched_at = datetime.now(timezone.utc).isoformat()

    if not token:
        return {
            "status": "missing_credentials",
            "query": ticker,
            "results": [],
            "result_count": 0,
            "hype_result_count": 0,
            "observations": [],
            "error": "X_BEARER_TOKEN is not configured",
        }

    safe_days = max(1, min(days, 7))
    query = f'"{ticker}" -is:retweet lang:en'
    params = {
        "query": query,
        "max_results": max(10, min(max_results, 100)),
        "tweet.fields": "created_at,public_metrics,lang,author_id",
    }

    try:
        response = requests.get(
            URL,
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        posts = payload.get("data") or []

        cutoff = datetime.now(timezone.utc).timestamp() - safe_days * 86400
        cleaned: list[dict[str, Any]] = []
        hype_count = 0

        for post in posts:
            created_at = post.get("created_at")
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    if dt.timestamp() < cutoff:
                        continue
                except ValueError:
                    pass

            text = str(post.get("text") or "")
            if any(term in text.lower() for term in HYPE_TERMS):
                hype_count += 1

            metrics = post.get("public_metrics") or {}
            cleaned.append({
                "id": str(post.get("id") or ""),
                "text": text,
                "created_at": created_at,
                "author_id": str(post.get("author_id") or ""),
                "public_metrics": {
                    "like_count": metrics.get("like_count", 0),
                    "reply_count": metrics.get("reply_count", 0),
                    "retweet_count": metrics.get("retweet_count", 0),
                    "quote_count": metrics.get("quote_count", 0),
                },
            })

        observations: list[dict[str, Any]] = []
        if len(cleaned) >= 30:
            observations.append({
                "signal": "x_volume",
                "severity": "medium",
                "text": f"X recent search returned {len(cleaned)} matching post(s).",
            })
        elif cleaned:
            observations.append({
                "signal": "x_presence",
                "severity": "low",
                "text": f"X recent search found {len(cleaned)} matching post(s).",
            })

        if hype_count >= 5:
            observations.append({
                "signal": "x_hype_language",
                "severity": "medium",
                "text": f"{hype_count} X post(s) contain hype or urgency-style keywords.",
            })

        return {
            "status": "connected",
            "query": query,
            "fetched_at": fetched_at,
            "results": cleaned,
            "result_count": len(cleaned),
            "hype_result_count": hype_count,
            "observations": observations,
            "error": None,
        }
    except Exception as exc:
        return {
            "status": "error",
            "query": query,
            "fetched_at": fetched_at,
            "results": [],
            "result_count": 0,
            "hype_result_count": 0,
            "observations": [],
            "error": str(exc),
        }
