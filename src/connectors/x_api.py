"""Free X/Twitter evidence connector for Dakota.

This provider intentionally does NOT use the paid X API.
It follows the working approach from the teammate repository:
use DuckDuckGo/DDGS to discover publicly indexed X/Twitter pages and
normalize the search snippets into Dakota's social-evidence schema.

No X account, Bearer Token, or paid X API credits are required.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)


HYPE_TERMS = {
    "multibagger",
    "multibag",
    "guaranteed",
    "target",
    "upper circuit",
    "upper-circuit",
    "breakout",
    "rocket",
    "buy now",
    "operator",
    "telegram",
    "whatsapp",
    "sure shot",
    "sure-shot",
    "100%",
    "double",
    "rocket stock",
}


def _load_ddgs() -> Any:
    """Load the current DDGS package, with teammate-era compatibility."""
    try:
        from ddgs import DDGS  # type: ignore

        return DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # type: ignore

            return DDGS
        except ImportError as exc:
            raise ImportError(
                "DDGS provider is not installed. Run: "
                "python -m pip install -U ddgs"
            ) from exc


def _run_search(ddgs: Any, query: str, limit: int) -> list[dict[str, Any]]:
    """Run text search against DDGS and normalize the iterator/list output."""
    raw = ddgs.text(query, max_results=limit)

    if raw is None:
        return []

    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]

    try:
        return [item for item in raw if isinstance(item, dict)]
    except TypeError:
        return []


def _search_variants(ticker: str) -> list[str]:
    symbol = ticker.upper().strip().split(".")[0]

    # The first query mirrors the friend's working implementation.
    # The second also catches X's newer x.com domain.
    return [
        f"site:twitter.com ${symbol}",
        f"site:x.com ${symbol}",
    ]


def search_x(
    ticker: str,
    *,
    max_results: int = 15,
    timeout: float = 12.0,
) -> dict[str, Any]:
    """Discover public X/Twitter evidence through DDGS search.

    The returned shape intentionally matches the existing social.py contract:
    status, provider, query, messages, results_count, observations, and error.
    """
    symbol = ticker.upper().strip().split(".")[0]
    fetched_at = datetime.now(timezone.utc).isoformat()
    limit = max(1, min(int(max_results), 30))

    try:
        DDGS = _load_ddgs()
        ddgs = DDGS(timeout=timeout)
    except TypeError:
        # Compatibility with versions whose constructor does not accept timeout.
        try:
            DDGS = _load_ddgs()
            ddgs = DDGS()
        except Exception as exc:
            return {
                "status": "not_configured",
                "provider": "X/Twitter via DDGS",
                "query": symbol,
                "ticker_searched": f"${symbol}",
                "results": [],
                "messages": [],
                "result_count": 0,
                "results_count": 0,
                "hype_result_count": 0,
                "observations": [],
                "error": str(exc),
                "fetched_at": fetched_at,
                "method": "ddgs_public_search",
            }
    except ImportError as exc:
        return {
            "status": "not_configured",
            "provider": "X/Twitter via DDGS",
            "query": symbol,
            "ticker_searched": f"${symbol}",
            "results": [],
            "messages": [],
            "result_count": 0,
            "results_count": 0,
            "hype_result_count": 0,
            "observations": [],
            "error": str(exc),
            "fetched_at": fetched_at,
            "method": "ddgs_public_search",
        }
    except Exception as exc:
        log.exception("DDGS initialization failed")
        return {
            "status": "error",
            "provider": "X/Twitter via DDGS",
            "query": symbol,
            "ticker_searched": f"${symbol}",
            "results": [],
            "messages": [],
            "result_count": 0,
            "results_count": 0,
            "hype_result_count": 0,
            "observations": [],
            "error": str(exc),
            "fetched_at": fetched_at,
            "method": "ddgs_public_search",
        }

    merged: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    errors: list[str] = []

    for query in _search_variants(symbol):
        try:
            results = _run_search(ddgs, query, limit)
        except Exception as exc:
            errors.append(f"{query}: {exc}")
            continue

        for item in results:
            title = str(item.get("title") or "").strip()
            body = str(item.get("body") or item.get("snippet") or "").strip()
            href = str(item.get("href") or item.get("url") or "").strip()

            dedupe_key = href or f"{title}|{body}"
            if dedupe_key in seen_urls:
                continue
            seen_urls.add(dedupe_key)

            combined = f"{title} {body}".strip()
            if not combined:
                continue

            hype = any(term in combined.lower() for term in HYPE_TERMS)

            merged.append(
                {
                    "body": body,
                    "text": body,
                    "title": title,
                    "url": href,
                    "created_at": "",
                    "username": title.replace(" - Twitter", "").strip(),
                    "source": "Twitter/X",
                    "hype": hype,
                }
            )

            if len(merged) >= limit:
                break

        if len(merged) >= limit:
            break

    hype_count = sum(1 for item in merged if item.get("hype"))

    observations: list[dict[str, Any]] = []
    if merged:
        observations.append(
            {
                "signal": "x_public_search",
                "severity": "low",
                "text": (
                    f"DDGS found {len(merged)} publicly indexed X/Twitter result(s) "
                    f"for ${symbol}. This is search-engine discovery evidence, "
                    "not a complete X feed and not proof of coordination."
                ),
            }
        )

    if hype_count >= 5:
        observations.append(
            {
                "signal": "x_hype_language",
                "severity": "medium",
                "text": f"{hype_count} discovered X/Twitter result(s) contain hype or urgency-style keywords.",
            }
        )

    response: dict[str, Any] = {
        "status": "connected" if merged else ("no_results" if not errors else "error"),
        "provider": "X/Twitter via DDGS",
        "query": f"site:twitter.com OR site:x.com ${symbol}",
        "ticker_searched": f"${symbol}",
        "fetched_at": fetched_at,
        "results": merged,
        "messages": merged,
        "result_count": len(merged),
        "results_count": len(merged),
        "hype_result_count": hype_count,
        "observations": observations,
        "error": "; ".join(errors) if errors else None,
        "method": "ddgs_public_search",
        "requires_bearer_token": False,
        "coverage_note": (
            "Public search discovery only; coverage depends on search-engine indexing."
        ),
    }

    return response
