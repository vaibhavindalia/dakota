"""News evidence collector for Dakota.

Uses the public GDELT DOC 2.0 search endpoint for a lightweight prototype.
The collector returns metadata and short risk observations; it does not copy
full article text into Dakota storage.

Source: GDELT DOC 2.0 API. The API supports article-list searches over recent
coverage and JSON output.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus

import requests

try:
    from src.evidence.news_analyzer import verify_news_for_ticker
except Exception:
    verify_news_for_ticker = None

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
USER_AGENT = "Dakota/0.2 research prototype"

HYPE_TERMS = {
    "guaranteed",
    "multibagger",
    "multibag",
    "upper circuit",
    "upper-circuit",
    "target",
    "rocket",
    "breakout",
    "operator",
    "telegram",
    "whatsapp",
    "tip",
    "buy now",
    "sure shot",
    "sure-shot",
}

RED_FLAG_TERMS = {
    "sebi",
    "investigation",
    "fraud",
    "manipulation",
    "pump",
    "dump",
    "insider",
    "regulatory",
    "surveillance",
    "warning",
}


@dataclass
class NewsResult:
    status: str
    query: str
    fetched_at: str
    article_count: int
    hype_article_count: int
    red_flag_article_count: int
    articles: list[dict[str, Any]]
    observations: list[dict[str, Any]]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "query": self.query,
            "fetched_at": self.fetched_at,
            "article_count": self.article_count,
            "hype_article_count": self.hype_article_count,
            "red_flag_article_count": self.red_flag_article_count,
            "articles": self.articles,
            "observations": self.observations,
            "error": self.error,
        }


def _text(article: dict[str, Any]) -> str:
    return " ".join(
        str(article.get(key) or "")
        for key in ("title", "seendate", "socialimage", "domain")
    ).lower()


def _contains_term(text: str, terms: set[str]) -> bool:
    return any(term in text for term in terms)


def _normalise_article(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": str(item.get("title") or "").strip(),
        "url": str(item.get("url") or "").strip(),
        "domain": str(item.get("domain") or "").strip(),
        "language": str(item.get("language") or "").strip(),
        "source_country": str(item.get("sourcecountry") or "").strip(),
        "seen_date": str(item.get("seendate") or "").strip(),
    }


def _search_news_gdelt(ticker: str, *, days: int = 7, max_records: int = 25, timeout: float = 8.0) -> dict[str, Any]:
    ticker = ticker.upper().strip()
    query = f'"{ticker}"'
    params = {
        "query": query,
        "mode": "artlist",
        "maxrecords": max(1, min(int(max_records), 75)),
        "timespan": f"{max(1, int(days))}d",
        "sort": "datedesc",
        "format": "json",
    }
    fetched_at = datetime.now(timezone.utc).isoformat()

    try:
        response = requests.get(
            GDELT_URL,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        raw_articles = payload.get("articles", []) if isinstance(payload, dict) else []
        articles = [_normalise_article(item) for item in raw_articles if isinstance(item, dict)]
        articles = [article for article in articles if article["title"] or article["url"]]

        hype_count = sum(_contains_term(_text(article), HYPE_TERMS) for article in articles)
        red_flag_count = sum(_contains_term(_text(article), RED_FLAG_TERMS) for article in articles)
        observations: list[dict[str, Any]] = []

        if len(articles) >= 20:
            observations.append({
                "signal": "news_volume",
                "severity": "high",
                "text": f"GDELT returned {len(articles)} matching articles in the last {days} days; coverage is unusually dense for this prototype query.",
            })
        elif len(articles) >= 8:
            observations.append({
                "signal": "news_volume",
                "severity": "medium",
                "text": f"GDELT returned {len(articles)} matching articles in the last {days} days.",
            })
        elif articles:
            observations.append({
                "signal": "news_presence",
                "severity": "low",
                "text": f"GDELT found {len(articles)} matching article(s) in the last {days} days.",
            })

        if hype_count >= 3:
            observations.append({
                "signal": "news_hype_language",
                "severity": "medium",
                "text": f"{hype_count} returned article(s) contain pump/hype-style keywords such as targets, multibagger or urgency language.",
            })

        if red_flag_count >= 2:
            observations.append({
                "signal": "news_red_flags",
                "severity": "medium",
                "text": f"{red_flag_count} returned article(s) contain regulatory or manipulation-related keywords; these require source-level verification.",
            })

        return NewsResult(
            status="connected",
            query=query,
            fetched_at=fetched_at,
            article_count=len(articles),
            hype_article_count=int(hype_count),
            red_flag_article_count=int(red_flag_count),
            articles=articles,
            observations=observations,
        ).to_dict()
    except Exception as exc:
        return NewsResult(
            status="error",
            query=query,
            fetched_at=fetched_at,
            article_count=0,
            hype_article_count=0,
            red_flag_article_count=0,
            articles=[],
            observations=[],
            error=str(exc),
        ).to_dict()


def _news_events_to_articles(news_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    articles: list[dict[str, Any]] = []
    for item in news_events or []:
        if not isinstance(item, dict):
            continue
        articles.append({
            "title": str(item.get("headline") or item.get("title") or "").strip(),
            "url": str(item.get("link") or item.get("url") or "").strip(),
            "domain": str(item.get("source") or item.get("domain") or "").strip(),
            "language": "",
            "source_country": "IN",
            "seen_date": str(item.get("published_at") or "").strip(),
            "provider": str(item.get("source") or "Yahoo/Google"),
        })
    return articles


def search_news(ticker: str, *, days: int = 7, max_records: int = 25, timeout: float = 8.0) -> dict[str, Any]:
    """Collect Dakota GDELT evidence plus the teammate Yahoo/Google news model.

    The teammate model is additive: its fetched articles and LLM assessment are
    exposed under ``teammate_intelligence``. Dakota's explainable risk score still
    relies on the existing observation stream rather than an opaque LLM modifier.
    """
    ticker = ticker.upper().strip()
    gdelt = _search_news_gdelt(ticker, days=days, max_records=max_records, timeout=timeout)

    teammate: dict[str, Any] = {
        "status": "not_configured",
        "ticker": ticker,
        "has_recent_news": False,
        "news_events": [],
        "llm_analysis": None,
        "error": None,
        "providers": {"yahoo": "not_run", "google": "not_run"},
    }
    if verify_news_for_ticker is not None:
        try:
            teammate = verify_news_for_ticker(ticker)
            teammate["status"] = str(teammate.get("status") or "unknown")
        except Exception as exc:
            teammate["status"] = "error"
            teammate["error"] = str(exc)

    teammate_articles = _news_events_to_articles(teammate.get("news_events") or [])
    existing_urls = {str(a.get("url") or "").strip() for a in gdelt.get("articles") or [] if str(a.get("url") or "").strip()}
    merged_articles = list(gdelt.get("articles") or [])
    for article in teammate_articles:
        url = str(article.get("url") or "").strip()
        title = str(article.get("title") or "").strip().lower()
        duplicate = url and url in existing_urls
        if not duplicate and title:
            duplicate = any(title == str(old.get("title") or "").strip().lower() for old in merged_articles)
        if not duplicate:
            merged_articles.append(article)
            if url:
                existing_urls.add(url)

    result = dict(gdelt)
    result["articles"] = merged_articles[: max(1, min(int(max_records) * 2, 100))]
    result["article_count"] = len(result["articles"])
    result["providers"] = {
        "gdelt": gdelt.get("status", "unknown"),
        "yahoo_google": teammate.get("status", "unknown"),
    }
    result["teammate_intelligence"] = {
        "status": teammate.get("status"),
        "news_events": teammate.get("news_events") or [],
        "llm_analysis": teammate.get("llm_analysis"),
        "has_recent_news": bool(teammate.get("has_recent_news")),
        "error": teammate.get("error") or teammate.get("error_message"),
    }
    if result.get("status") in {"error", "unavailable"} and teammate.get("status") == "success":
        result["status"] = "connected"
    return result
