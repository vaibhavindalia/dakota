"""Free StockTwits public-search evidence adapter for Dakota.

This adapter intentionally avoids the legacy unauthenticated StockTwits API and
also avoids requiring a paid Firestream account. It uses DDGS to discover
publicly indexed StockTwits pages/snippets from the web search index.

Important:
    - This is search-engine discovery evidence, not a complete StockTwits feed.
    - It should never be presented as exhaustive coverage.
    - Results are useful for contextual evidence and sentiment analysis, not as
      standalone proof of coordination or manipulation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from ddgs import DDGS


_HYPE_TERMS = (
    "moon",
    "rocket",
    "multibagger",
    "breakout",
    "to the moon",
    "guaranteed",
    "squeeze",
    "pump",
    "100%",
    "double",
    "target",
)


def _clean_ticker(ticker: str) -> str:
    value = (ticker or "").upper().strip()
    value = value.split(".", 1)[0]
    return value


def _is_stocktwits_url(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return False
    return host == "stocktwits.com" or host.endswith(".stocktwits.com")


def _result_text(item: dict[str, Any]) -> str:
    title = str(item.get("title") or "").strip()
    body = str(item.get("body") or "").strip()
    if title and body:
        return f"{title}. {body}"
    return title or body


def _dedupe(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []

    for item in results:
        url = str(item.get("url") or "").strip()
        key = (
            url.lower()
            if url
            else str(item.get("title") or "").strip().lower()
        )

        if not key or key in seen:
            continue

        seen.add(key)
        out.append(item)

    return out


def _search(
    query: str,
    *,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    with DDGS() as client:
        raw = client.text(
            query,
            max_results=max_results,
        )

    out: list[dict[str, Any]] = []

    for item in raw or []:
        if not isinstance(item, dict):
            continue

        href = str(item.get("href") or "").strip()

        if not _is_stocktwits_url(href):
            continue

        out.append(
            {
                "title": str(
                    item.get("title") or ""
                ).strip(),
                "url": href,
                "body": str(
                    item.get("body") or ""
                ).strip(),
            }
        )

    return out


def search_stocktwits(
    ticker: str,
    *,
    max_results: int = 10,
) -> dict[str, Any]:
    """Discover publicly indexed StockTwits evidence without paid credentials."""
    ticker = _clean_ticker(ticker)

    fetched_at = datetime.now(timezone.utc).isoformat()
    symbol = f"{ticker}.NSE" if ticker else ""

    if not ticker:
        return {
            "status": "invalid_query",
            "provider": "StockTwits public search",
            "symbol": "",
            "query": "",
            "results": [],
            "messages": [],
            "result_count": 0,
            "hype_result_count": 0,
            "observations": [],
            "error": "No ticker supplied",
            "warnings": [],
            "fetched_at": fetched_at,
        }

    queries = [
        f'site:stocktwits.com/symbol/{symbol} "{ticker}"',
        f'site:stocktwits.com "{ticker}.NSE" StockTwits',
    ]

    results: list[dict[str, Any]] = []
    errors: list[str] = []

    for query in queries:
        try:
            results.extend(
                _search(
                    query,
                    max_results=max_results,
                )
            )
        except Exception as exc:
            errors.append(str(exc))

    results = _dedupe(results)

    if not results and errors:
        return {
            "status": "error",
            "provider": "StockTwits public search",
            "symbol": symbol,
            "query": queries[0],
            "queries": queries,
            "results": [],
            "messages": [],
            "result_count": 0,
            "hype_result_count": 0,
            "observations": [],
            "error": "; ".join(errors[:2]),
            "warnings": [],
            "fetched_at": fetched_at,
        }

    texts = [
        _result_text(item)
        for item in results
    ]

    hype_count = sum(
        any(
            term in text.lower()
            for term in _HYPE_TERMS
        )
        for text in texts
    )

    observations: list[dict[str, Any]] = []

    if results:
        observations.append(
            {
                "signal": "stocktwits_search_volume",
                "severity": "medium",
                "text": (
                    f"DDGS found {len(results)} publicly indexed StockTwits "
                    f"result(s) for {symbol}."
                ),
            }
        )

        observations.append(
            {
                "signal": "stocktwits_discovery_only",
                "severity": "low",
                "text": (
                    "StockTwits evidence comes from public search-engine "
                    "discovery; it is not a complete StockTwits feed and "
                    "is not proof of coordination."
                ),
            }
        )

    if hype_count:
        observations.append(
            {
                "signal": "stocktwits_hype_language",
                "severity": "medium",
                "text": (
                    f"{hype_count} indexed StockTwits result(s) contained "
                    "promotion/hype-style language."
                ),
            }
        )

    # DDGS can return useful results for one query while another query yields a
    # soft "no results" exception. That is a warning about coverage, not a
    # provider failure, because we already have usable evidence.
    warnings = errors[:2] if errors and results else []

    return {
        "status": "connected" if results else "no_results",
        "provider": "StockTwits public search",
        "symbol": symbol,
        "query": queries[0],
        "queries": queries,
        "results": results,
        "messages": results,
        "result_count": len(results),
        "hype_result_count": hype_count,
        "observations": observations,
        "error": None,
        "warnings": warnings,
        "fetched_at": fetched_at,
    }


if __name__ == "__main__":
    import json
    import sys

    ticker = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "CDSL"
    )

    print(
        json.dumps(
            search_stocktwits(ticker),
            indent=2,
            ensure_ascii=False,
        )
    )
