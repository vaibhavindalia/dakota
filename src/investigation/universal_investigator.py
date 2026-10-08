"""Universal Dakota investigation pipeline for stock and non-stock topics."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from src.evidence.aggregate import aggregate_scores
from src.evidence.news import search_news
from src.evidence.social import collect_social_evidence
from src.investigation.impact_mapper import map_impact
from src.investigation.tip_investigator import investigate_tip


def _label(topic: str) -> str:
    return topic.replace("_", " ").strip()


def _flatten_social(social: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for value in social.values():
        if isinstance(value, dict):
            out.extend(value.get("observations") or [])
    return out


def _market_topic_observations(impact: dict[str, Any]) -> list[dict[str, Any]]:
    areas = impact.get("potentially_affected_areas") or []
    if not areas:
        return []
    return [{
        "signal": "impact_mapping",
        "severity": "low",
        "text": "Potentially affected areas identified: " + ", ".join(str(a).replace("_", " ") for a in areas[:6]) + ". This is an investigation scope, not a claimed causal relationship.",
    }]


def investigate_message(
    raw_text: str,
    classification: dict[str, Any],
    *,
    data_root: str = "data/raw",
    source_label: str = "telegram",
    timestamp: str | None = None,
) -> dict[str, Any]:
    impact = map_impact(raw_text, classification)

    if impact["status"] == "investigate_stock":
        result = investigate_tip(
            raw_text,
            data_root=data_root,
            source_label=source_label,
        )
        result["classification"] = classification
        result["impact"] = impact
        result["investigation_mode"] = "stock"
        result["investigated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        result["source"] = source_label
        result["timestamp"] = timestamp
        return result

    if impact["status"] == "classified_non_financial":
        return {
            "status": "classified_non_financial",
            "source": source_label,
            "timestamp": timestamp,
            "classification": classification,
            "impact": impact,
            "investigation_mode": "none",
            "investigated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "risk": None,
            "evidence": {},
        }

    if impact["status"] == "needs_entity_resolution":
        return {
            "status": "needs_entity_resolution",
            "source": source_label,
            "timestamp": timestamp,
            "classification": classification,
            "impact": impact,
            "investigation_mode": "unresolved",
            "investigated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "risk": None,
            "evidence": {},
        }

    entity = str(impact.get("entity") or "").strip()
    label = _label(entity)
    web_enabled = os.getenv("DAKOTA_WEB_EVIDENCE", "1").strip().lower() not in {"0", "false", "no", "off"}

    if web_enabled:
        news = search_news(label)
        social = collect_social_evidence(label)
    else:
        news = {"status": "disabled", "query": label, "articles": [], "observations": [], "error": None}
        social = {"status": "disabled"}

    tip_observations = _market_topic_observations(impact)
    news_observations = (news.get("observations") or [])
    social_observations = _flatten_social(social)

    risk = aggregate_scores(
        tip_observations=tip_observations,
        market_observations=[],
        news_observations=news_observations,
        social_observations=social_observations,
    )

    coverage = {
        "market": "not_applicable_topic",
        "news": str(news.get("status") or "unknown"),
        "reddit": str((social.get("reddit") or {}).get("status") or "unknown"),
        "x": str((social.get("x") or {}).get("status") or "unknown"),
        "instagram": str((social.get("instagram") or {}).get("status") or "unknown"),
        "telegram": "ingestion_source",
    }

    return {
        "status": "ok",
        "source": source_label,
        "timestamp": timestamp,
        "classification": classification,
        "impact": impact,
        "investigation_mode": "market_topic",
        "investigated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "entity": entity,
        "risk": risk,
        "evidence": {
            "news": news,
            "social": social,
            "impact_areas": impact.get("potentially_affected_areas", []),
        },
        "source_status": coverage,
        "next_steps": [
            "Map the resolved topic to concrete affected listed securities.",
            "Check whether the message is repeated across channels or sources.",
            "Collect point-in-time market evidence for the affected securities before increasing confidence.",
        ],
        "disclaimer": (
            "Dakota reports risk indicators from available evidence. "
            "It does not determine fraud and does not provide buy/sell advice."
        ),
    }
