"""Public Reddit search evidence collector for Dakota.

This is intentionally a prototype adapter using Reddit's public search RSS
feed. It does not authenticate, join private communities, or scrape private
content. A production connector should use Reddit's supported developer/API
access and respect current terms and rate limits.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus
from xml.etree import ElementTree as ET

import requests

REDDIT_SEARCH_URL = "https://www.reddit.com/search.rss"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Dakota/0.3"

HYPE_TERMS = {
    "multibagger",
    "guaranteed",
    "target",
    "rocket",
    "upper circuit",
    "buy now",
    "moon",
    "breakout",
    "operator",
    "telegram",
    "whatsapp",
    "tip",
}


def _child_text(entry: ET.Element, local_name: str) -> str:
    for node in list(entry):
        tag = node.tag.rsplit("}", 1)[-1]
        if tag == local_name:
            return (node.text or "").strip()
    return ""


def _fetch_rss(params: dict, timeout: float, max_retries: int = 2) -> requests.Response:
    """Fetch Reddit RSS with retry + backoff for 429 rate limits."""
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            response = requests.get(
                REDDIT_SEARCH_URL,
                params=params,
                headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml"},
                timeout=timeout,
            )
            if response.status_code == 429:
                if attempt < max_retries:
                    wait = float(response.headers.get("Retry-After", 2 * (attempt + 1)))
                    time.sleep(min(wait, 5))
                    continue
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as exc:
            last_exc = exc
            if "429" in str(exc) and attempt < max_retries:
                time.sleep(2 * (attempt + 1))
                continue
            raise
        except Exception:
            raise
    raise last_exc  # type: ignore[misc]


def search_reddit(ticker: str, *, days: int = 7, limit: int = 25, timeout: float = 8.0) -> dict[str, Any]:
    ticker = ticker.upper().strip()
    fetched_at = datetime.now(timezone.utc).isoformat()
    params = {
        "q": ticker,
        "sort": "new",
        "t": "week" if days <= 7 else "month",
        "restrict_sr": "false",
        "limit": max(1, min(int(limit), 50)),
    }

    try:
        response = _fetch_rss(params, timeout)
        root = ET.fromstring(response.content)
        entries: list[dict[str, Any]] = []
        subreddits: set[str] = set()
        hype_count = 0

        for entry in root.iter():
            tag = entry.tag.rsplit("}", 1)[-1]
            if tag != "entry":
                continue
            title = _child_text(entry, "title")
            link = ""
            author = ""
            published = _child_text(entry, "published")
            for node in list(entry):
                node_tag = node.tag.rsplit("}", 1)[-1]
                if node_tag == "link":
                    link = str(node.attrib.get("href") or "")
                elif node_tag == "author":
                    author = _child_text(node, "name")

            # Public subreddit information is encoded in the Reddit title/link;
            # do not store usernames as a Dakota evidence field.
            text = title.lower()
            subreddit = ""
            marker = "/r/"
            if marker in link.lower():
                remainder = link.lower().split(marker, 1)[1]
                subreddit = remainder.split("/", 1)[0]
                if subreddit:
                    subreddits.add(subreddit)
            if any(term in text for term in HYPE_TERMS):
                hype_count += 1

            entries.append({
                "title": title,
                "url": link,
                "subreddit": subreddit,
                "published": published,
            })

        observations: list[dict[str, Any]] = []
        count = len(entries)
        if count >= 15:
            observations.append({
                "signal": "reddit_volume",
                "severity": "medium",
                "text": f"Reddit search returned {count} public result(s) for {ticker} in the selected recent window.",
            })
        elif count:
            observations.append({
                "signal": "reddit_presence",
                "severity": "low",
                "text": f"Reddit search found {count} public result(s) mentioning {ticker}.",
            })

        if len(subreddits) >= 3:
            observations.append({
                "signal": "reddit_cross_subreddit",
                "severity": "medium",
                "text": f"Mentions were observed across {len(subreddits)} public subreddits; this is a discovery signal, not proof of coordination.",
            })

        if hype_count >= 3:
            observations.append({
                "signal": "reddit_hype_language",
                "severity": "medium",
                "text": f"{hype_count} public Reddit result(s) contain hype/urgency-style keywords.",
            })

        return {
            "status": "connected",
            "query": ticker,
            "fetched_at": fetched_at,
            "result_count": count,
            "subreddit_count": len(subreddits),
            "hype_result_count": hype_count,
            "results": entries[:limit],
            "observations": observations,
            "error": None,
        }
    except Exception as exc:
        # Distinguish rate-limiting from real errors
        is_rate_limited = "429" in str(exc) or "too many" in str(exc).lower()
        return {
            "status": "rate_limited" if is_rate_limited else "error",
            "query": ticker,
            "fetched_at": fetched_at,
            "result_count": 0,
            "subreddit_count": 0,
            "hype_result_count": 0,
            "results": [],
            "observations": [],
            "error": "Reddit rate limit reached — try again in a few minutes" if is_rate_limited else str(exc),
        }

