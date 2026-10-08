"""Official Reddit OAuth search connector with RSS fallback."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from src.connectors.config import env
from src.evidence.reddit import search_reddit as rss_search_reddit

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
SEARCH_URL = "https://oauth.reddit.com/search"

HYPE_TERMS = {
    "multibagger",
    "guaranteed",
    "target",
    "upper circuit",
    "buy now",
    "rocket",
    "moon",
    "operator",
    "telegram",
    "whatsapp",
}


def _oauth_token(timeout: float) -> str:
    response = requests.post(
        TOKEN_URL,
        auth=(env("REDDIT_CLIENT_ID"), env("REDDIT_CLIENT_SECRET")),
        data={"grant_type": "client_credentials"},
        headers={
            "User-Agent": env("REDDIT_USER_AGENT", "Dakota/0.3 research prototype")
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return str(response.json().get("access_token") or "")


def search_reddit_real(ticker: str, *, limit: int = 50, timeout: float = 10.0) -> dict[str, Any]:
    ticker = ticker.upper().strip()
    token = ""
    if env("REDDIT_CLIENT_ID") and env("REDDIT_CLIENT_SECRET"):
        try:
            token = _oauth_token(timeout)
        except Exception as exc:
            return {
                "status": "oauth_error",
                "query": ticker,
                "results": [],
                "result_count": 0,
                "subreddit_count": 0,
                "hype_result_count": 0,
                "observations": [],
                "error": str(exc),
            }

    if not token:
        fallback = rss_search_reddit(ticker, limit=limit, timeout=timeout)
        fallback["status"] = "rss_fallback"
        return fallback

    try:
        response = requests.get(
            SEARCH_URL,
            headers={
                "Authorization": f"bearer {token}",
                "User-Agent": env("REDDIT_USER_AGENT", "Dakota/0.3 research prototype"),
            },
            params={
                "q": ticker,
                "sort": "new",
                "t": "week",
                "limit": max(1, min(limit, 100)),
                "raw_json": 1,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        children = (payload.get("data") or {}).get("children") or []

        results: list[dict[str, Any]] = []
        subreddits: set[str] = set()
        hype_count = 0

        for child in children:
            data = child.get("data") or {}
            title = str(data.get("title") or "")
            selftext = str(data.get("selftext") or "")
            text = f"{title} {selftext}".strip()
            subreddit = str(data.get("subreddit") or "")
            if subreddit:
                subreddits.add(subreddit)
            if any(term in text.lower() for term in HYPE_TERMS):
                hype_count += 1

            results.append({
                "id": str(data.get("id") or ""),
                "title": title,
                "url": str(data.get("url") or ""),
                "permalink": str(data.get("permalink") or ""),
                "subreddit": subreddit,
                "published": data.get("created_utc"),
                "score": data.get("score", 0),
                "num_comments": data.get("num_comments", 0),
            })

        observations: list[dict[str, Any]] = []
        if len(results) >= 15:
            observations.append({
                "signal": "reddit_volume",
                "severity": "medium",
                "text": f"Reddit search returned {len(results)} public result(s).",
            })
        elif results:
            observations.append({
                "signal": "reddit_presence",
                "severity": "low",
                "text": f"Reddit search found {len(results)} public result(s).",
            })

        if len(subreddits) >= 3:
            observations.append({
                "signal": "reddit_cross_subreddit",
                "severity": "medium",
                "text": f"Mentions were observed across {len(subreddits)} public subreddits; this is not proof of coordination.",
            })

        if hype_count >= 3:
            observations.append({
                "signal": "reddit_hype_language",
                "severity": "medium",
                "text": f"{hype_count} Reddit result(s) contain hype/urgency-style keywords.",
            })

        return {
            "status": "connected",
            "query": ticker,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "results": results,
            "result_count": len(results),
            "subreddit_count": len(subreddits),
            "hype_result_count": hype_count,
            "observations": observations,
            "error": None,
        }
    except Exception as exc:
        return {
            "status": "error",
            "query": ticker,
            "results": [],
            "result_count": 0,
            "subreddit_count": 0,
            "hype_result_count": 0,
            "observations": [],
            "error": str(exc),
        }
