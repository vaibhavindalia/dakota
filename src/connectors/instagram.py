"""Instagram Graph API hashtag connector.

Requires a legitimate Instagram/Meta access token and operated IG user ID.
Only public hashtag media exposed by the API is used.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from src.connectors.config import env

BASE = "https://graph.facebook.com"

HYPE_TERMS = {
    "multibagger",
    "guaranteed",
    "target",
    "upper circuit",
    "buy now",
    "rocket",
    "breakout",
    "operator",
}


def search_instagram(ticker: str, *, limit: int = 25, timeout: float = 10.0) -> dict[str, Any]:
    token = env("INSTAGRAM_ACCESS_TOKEN")
    user_id = env("INSTAGRAM_USER_ID")
    version = env("META_GRAPH_VERSION")
    ticker = ticker.upper().strip()

    if not token or not user_id or not version:
        return {
            "status": "missing_credentials",
            "query": f"#{ticker}",
            "results": [],
            "result_count": 0,
            "hype_result_count": 0,
            "observations": [],
            "error": "Set INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_USER_ID and META_GRAPH_VERSION",
        }

    try:
        search = requests.get(
            f"{BASE}/{version}/ig_hashtag_search",
            params={
                "user_id": user_id,
                "q": ticker.lower().lstrip("#"),
                "access_token": token,
            },
            timeout=timeout,
        )
        search.raise_for_status()
        hashtag_items = search.json().get("data") or []

        if not hashtag_items:
            return {
                "status": "connected",
                "query": f"#{ticker}",
                "results": [],
                "result_count": 0,
                "hype_result_count": 0,
                "observations": [],
                "error": None,
            }

        hashtag_id = str(hashtag_items[0].get("id") or "")
        media = requests.get(
            f"{BASE}/{version}/{hashtag_id}/recent_media",
            params={
                "user_id": user_id,
                "fields": "id,caption,media_type,permalink,timestamp,like_count,comments_count",
                "access_token": token,
                "limit": max(1, min(limit, 50)),
            },
            timeout=timeout,
        )
        media.raise_for_status()
        items = media.json().get("data") or []

        results: list[dict[str, Any]] = []
        hype_count = 0
        for item in items:
            caption = str(item.get("caption") or "")
            if any(term in caption.lower() for term in HYPE_TERMS):
                hype_count += 1
            results.append({
                "id": str(item.get("id") or ""),
                "caption": caption[:1000],
                "media_type": item.get("media_type"),
                "permalink": item.get("permalink"),
                "timestamp": item.get("timestamp"),
                "like_count": item.get("like_count", 0),
                "comments_count": item.get("comments_count", 0),
            })

        observations: list[dict[str, Any]] = []
        if len(results) >= 10:
            observations.append({
                "signal": "instagram_volume",
                "severity": "medium",
                "text": f"Instagram hashtag search returned {len(results)} public media item(s).",
            })
        elif results:
            observations.append({
                "signal": "instagram_presence",
                "severity": "low",
                "text": f"Instagram hashtag search found {len(results)} public media item(s).",
            })

        if hype_count >= 3:
            observations.append({
                "signal": "instagram_hype_language",
                "severity": "medium",
                "text": f"{hype_count} public Instagram caption(s) contain hype-style keywords.",
            })

        return {
            "status": "connected",
            "query": f"#{ticker}",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "results": results,
            "result_count": len(results),
            "hype_result_count": hype_count,
            "observations": observations,
            "error": None,
        }
    except Exception as exc:
        return {
            "status": "error",
            "query": f"#{ticker}",
            "results": [],
            "result_count": 0,
            "hype_result_count": 0,
            "observations": [],
            "error": str(exc),
        }
