"""Explainable evidence aggregation for Dakota's investigation prototype."""
from __future__ import annotations

from typing import Any


def _points(observations: list[dict[str, Any]], weights: dict[str, int]) -> tuple[int, list[str]]:
    points = 0
    reasons: list[str] = []
    for item in observations:
        severity = str(item.get("severity") or "low")
        points += weights.get(severity, weights.get("low", 1))
        text = str(item.get("text") or "").strip()
        if text:
            reasons.append(text)
    return points, reasons


def aggregate_scores(
    *,
    tip_observations: list[dict[str, Any]],
    market_observations: list[dict[str, Any]],
    news_observations: list[dict[str, Any]],
    social_observations: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return a prototype 0-100 score plus transparent coverage information.

    Only currently connected evidence is scored. Company filings, X, Instagram,
    Telegram and index context are not silently treated as clean/negative; their
    absence is reflected in the coverage field.
    """
    tip_raw, tip_reasons = _points(tip_observations, {"high": 7, "medium": 4, "low": 1})
    market_raw, market_reasons = _points(market_observations, {"high": 10, "medium": 6, "low": 2})
    news_raw, news_reasons = _points(news_observations, {"high": 7, "medium": 4, "low": 1})
    social_raw, social_reasons = _points(social_observations, {"high": 7, "medium": 4, "low": 1})

    caps = {"tip": 20, "market": 35, "news": 20, "social": 15}
    components = {
        "tip": min(tip_raw, caps["tip"]),
        "market": min(market_raw, caps["market"]),
        "news": min(news_raw, caps["news"]),
        "social": min(social_raw, caps["social"]),
    }
    available_points = sum(caps.values())
    raw_score = sum(components.values())
    normalized = round((raw_score / available_points) * 100, 1) if available_points else 0.0

    reasons = tip_reasons + market_reasons + news_reasons + social_reasons
    if normalized >= 70:
        band = "High"
    elif normalized >= 40:
        band = "Elevated"
    else:
        band = "Low"

    return {
        "score": normalized,
        "band": band,
        "raw_score": raw_score,
        "available_score_points": available_points,
        "components": components,
        "reasons": reasons[:20],
        "method": "Prototype available-evidence score; not the final Dakota model.",
    }
