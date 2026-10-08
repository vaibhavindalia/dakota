"""Instagram Graph API hashtag connector for Dakota.

Credentials:
    INSTAGRAM_ACCESS_TOKEN
    INSTAGRAM_USER_ID
    META_GRAPH_VERSION

The API path used here is the public hashtag discovery flow exposed through
Meta's Graph API. Availability depends on the Instagram/Meta account, app
permissions, and provider-side review/limits.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from src.connectors.config import env

BASE = "https://graph.facebook.com"

HYPE_TERMS = {
    "multibagger",
    "multibag",
    "guaranteed",
    "target",
    "upper circuit",
    "buy now",
    "rocket",
    "breakout",
    "operator",
    "sure shot",
    "sure-shot",
}


def _status_from_http(status_code: int) -> str:
    if status_code in {401, 403}:
        return "unauthorized"
    if status_code == 429:
        return "rate_limited"
    return "error"


def search_instagram(
    ticker: str,
    *,
    limit: int = 25,
    timeout: float = 12.0,
) -> dict[str, Any]:
    ticker = ticker.upper().strip().split(".")[0]
    fetched_at = datetime.now(timezone.utc).isoformat()

    token = env("INSTAGRAM_ACCESS_TOKEN")
    user_id = env("INSTAGRAM_USER_ID")
    version = env("META_GRAPH_VERSION")

    if not token or not user_id or not version:
        return {
            "status": "missing_credentials",
            "provider": "Instagram",
            "query": f"#{ticker}",
            "results": [],
            "result_count": 0,
            "hype_result_count": 0,
            "observations": [],
            "error": "Set INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_USER_ID and META_GRAPH_VERSION",
            "fetched_at": fetched_at,
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
        if search.status_code != 200:
            return {
                "status": _status_from_http(search.status_code),
                "provider": "Instagram",
                "query": f"#{ticker}",
                "results": [],
                "result_count": 0,
                "hype_result_count": 0,
                "observations": [],
                "error": f"HTTP {search.status_code}: {search.text[:500]}",
                "fetched_at": fetched_at,
            }

        hashtag_items = search.json().get("data") or []
        if not hashtag_items:
            return {
                "status": "connected",
                "provider": "Instagram",
                "query": f"#{ticker}",
                "results": [],
                "result_count": 0,
                "hype_result_count": 0,
                "observations": [],
                "error": None,
                "fetched_at": fetched_at,
                "hashtag_found": False,
            }

        hashtag_id = str(hashtag_items[0].get("id") or "")
        media = requests.get(
            f"{BASE}/{version}/{hashtag_id}/recent_media",
            params={
                "user_id": user_id,
                "fields": "id,caption,media_type,permalink,timestamp,like_count,comments_count",
                "access_token": token,
                "limit": max(1, min(int(limit), 50)),
            },
            timeout=timeout,
        )
        if media.status_code != 200:
            return {
                "status": _status_from_http(media.status_code),
                "provider": "Instagram",
                "query": f"#{ticker}",
                "results": [],
                "result_count": 0,
                "hype_result_count": 0,
                "observations": [],
                "error": f"HTTP {media.status_code}: {media.text[:500]}",
                "fetched_at": fetched_at,
                "hashtag_found": True,
            }

        items = media.json().get("data") or []
        results: list[dict[str, Any]] = []
        hype_count = 0

        for item in items:
            if not isinstance(item, dict):
                continue
            caption = str(item.get("caption") or "").strip()
            if any(term in caption.lower() for term in HYPE_TERMS):
                hype_count += 1
            results.append(
                {
                    "id": str(item.get("id") or ""),
                    "caption": caption[:1200],
                    "media_type": item.get("media_type"),
                    "permalink": item.get("permalink"),
                    "timestamp": item.get("timestamp"),
                    "like_count": item.get("like_count", 0),
                    "comments_count": item.get("comments_count", 0),
                }
            )

        observations: list[dict[str, Any]] = []
        if len(results) >= 10:
            observations.append(
                {
                    "signal": "instagram_volume",
                    "severity": "medium",
                    "text": f"Instagram hashtag search returned {len(results)} public media item(s).",
                }
            )
        elif results:
            observations.append(
                {
                    "signal": "instagram_presence",
                    "severity": "low",
                    "text": f"Instagram hashtag search found {len(results)} public media item(s).",
                }
            )

        if hype_count >= 3:
            observations.append(
                {
                    "signal": "instagram_hype_language",
                    "severity": "medium",
                    "text": f"{hype_count} Instagram caption(s) contain hype-style keywords.",
                }
            )

        return {
            "status": "connected",
            "provider": "Instagram",
            "query": f"#{ticker}",
            "fetched_at": fetched_at,
            "results": results,
            "result_count": len(results),
            "hype_result_count": hype_count,
            "observations": observations,
            "error": None,
            "hashtag_found": True,
        }
    except requests.Timeout:
        return {
            "status": "timeout",
            "provider": "Instagram",
            "query": f"#{ticker}",
            "results": [],
            "result_count": 0,
            "hype_result_count": 0,
            "observations": [],
            "error": f"Instagram request timed out after {timeout}s",
            "fetched_at": fetched_at,
        }
    except Exception as exc:
        return {
            "status": "error",
            "provider": "Instagram",
            "query": f"#{ticker}",
            "results": [],
            "result_count": 0,
            "hype_result_count": 0,
            "observations": [],
            "error": str(exc),
            "fetched_at": fetched_at,
        }
