"""Unified Forensic Campaign Dossier Snapshot Generator.

Generates a single, canonical, immutable evidence snapshot used for BOTH
JSON and PDF exports, ensuring zero contradiction between export formats.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from src.alerts.store import alert_store
from src.campaign.graph import build_campaign_graph
from src.campaign.models import CampaignRecord
from src.campaign.store import campaign_store


def generate_campaign_dossier(campaign_id: str) -> dict[str, Any]:
    """Generate an authoritative forensic dossier snapshot for a campaign."""
    campaign = campaign_store.get_campaign(campaign_id, include_events=True)
    if not campaign:
        raise ValueError(f"Campaign '{campaign_id}' not found.")

    now_utc = datetime.now(timezone.utc)
    export_ts = now_utc.isoformat()
    dossier_id = f"DOSSIER-{campaign.campaign_id.upper()}-{int(time.time())}"

    # 1. Enrich Securities with Market Telemetry & Disclosures
    enriched_securities: list[dict[str, Any]] = []
    for tk in campaign.securities:
        clean_tk = tk.upper().strip()
        sec_info: dict[str, Any] = {
            "ticker": clean_tk,
            "exchange": "NSE/BSE",
            "relationship_reasons": [
                expl for rel, expl in campaign.relationship_explanations.items()
                if clean_tk in expl or "across" in expl or "multiple" in expl
            ] or [f"Identified as target of coordinated promotional activity during {campaign.time_window_hours}h window."],
            "market_telemetry": {
                "latest_price": None,
                "previous_close": None,
                "session_change_pct": None,
                "volume_ratio_20d": None,
                "delivery_pct": None,
                "data_freshness": "unavailable",
                "observation_timestamp": None,
                "feed_type": "MARKET_TELEMETRY",
            },
            "surveillance": {
                "gsm_asm_framework": False,
                "trade_to_trade": False,
            },
        }

        # Try obtaining latest market snapshot from universe_manager cache
        try:
            from src.market.universe_manager import get_or_assess_stock
            mkt_data = get_or_assess_stock(clean_tk, force_refresh=False, ttl_seconds=900)
            if mkt_data and "market" in mkt_data and "snapshot" in mkt_data["market"]:
                snap = mkt_data["market"]["snapshot"]
                sec_info["market_telemetry"]["latest_price"] = snap.get("close")
                sec_info["market_telemetry"]["previous_close"] = snap.get("previous_close")
                sec_info["market_telemetry"]["volume_ratio_20d"] = snap.get("volume_ratio_20")
                sec_info["market_telemetry"]["delivery_pct"] = snap.get("delivery_pct")
                sec_info["market_telemetry"]["data_freshness"] = mkt_data.get("risk", {}).get("data_freshness", "cached")
                sec_info["market_telemetry"]["observation_timestamp"] = mkt_data.get("market", {}).get("last_date")
        except Exception:
            pass

        enriched_securities.append(sec_info)

    # 2. Public Promoters / Actors with Uncertainty Documentation
    public_actors: list[dict[str, Any]] = []
    for actor in campaign.actors:
        clean_act = actor.strip()
        public_actors.append({
            "identifier": clean_act,
            "platform": "telegram" if clean_act.startswith("@") or "telegram" in clean_act.lower() else "public_web",
            "attribution_type": "public_broadcast_channel",
            "uncertainty_note": (
                "Entity represents a public broadcast channel handle. "
                "Legal natural person identity, ownership, and behind-the-scenes syndicate control "
                "are unverified and cannot be inferred solely from channel usernames."
            ),
        })

    # 3. Promotional Events & Message Provenance
    promotional_events: list[dict[str, Any]] = []
    for ev in campaign.events:
        promotional_events.append({
            "event_id": ev.event_id,
            "event_type": ev.event_type,
            "ticker": ev.ticker,
            "source_label": ev.source_label,
            "publication_timestamp": ev.event_timestamp,
            "retrieved_at_timestamp": ev.retrieved_at,
            "data_freshness": ev.data_freshness,
            "summary": ev.summary,
            "metadata": ev.metadata,
        })

    # 4. Corroborating Market Alerts Details
    alert_details: list[dict[str, Any]] = []
    for aid in campaign.alert_ids:
        alt = alert_store.get_alert(aid)
        if alt:
            alert_details.append({
                "alert_id": alt.alert_id,
                "rule_name": alt.rule_name,
                "rule_type": alt.rule_type.value if hasattr(alt.rule_type, "value") else str(alt.rule_type),
                "ticker": alt.ticker,
                "severity": alt.severity.value if hasattr(alt.severity, "value") else str(alt.severity),
                "title": alt.title,
                "message": alt.message,
                "trigger_value": alt.trigger_value,
                "threshold_value": alt.threshold_value or alt.threshold_value_str,
                "observation_timestamp": alt.observation_timestamp,
                "retrieved_at": alt.retrieved_at,
                "data_freshness": alt.data_freshness,
            })
        else:
            alert_details.append({
                "alert_id": aid,
                "status": "unresolved_record",
                "note": "Alert referenced by campaign, but primary record unavailable in current partition.",
            })

    # 5. JEV Analytical Intelligence
    jev_intel: dict[str, Any] | None = None
    if campaign.jev_assessment and isinstance(campaign.jev_assessment, dict):
        pred = campaign.jev_assessment.get("prediction", {})
        analysis = campaign.jev_assessment.get("analysis", {})
        jev_intel = {
            "status": "completed",
            "model_id": pred.get("model_id", "qwen2.5-1.5b-instruct-nf4"),
            "predicted_label": pred.get("predicted_label", "Analyzed"),
            "confidence": pred.get("confidence", 0.0),
            "executive_summary": analysis.get("executive_summary", ""),
            "cited_evidence_tokens": pred.get("evidence_ids", []),
            "disclaimer": "JEV analytical classification is an automated NLP assessment; it does not constitute legal proof of coordinated manipulation.",
        }

    # 6. Graph Relationships Summary
    graph = build_campaign_graph(campaign)
    graph_summary = {
        "nodes_count": len(graph.nodes),
        "edges_count": len(graph.edges),
        "metrics": graph.metrics,
        "key_edges": [
            {
                "source": e.source,
                "target": e.target,
                "type": e.type.value if hasattr(e.type, "value") else str(e.type),
                "label": e.label,
                "rationale": e.rationale,
                "evidence_references": e.evidence_references,
            }
            for e in graph.edges[:12]
        ],
    }

    # 7. Investigator Review & Action History
    investigator_history: list[dict[str, Any]] = []
    if campaign.acknowledged_at:
        investigator_history.append({"action": "acknowledged", "timestamp": campaign.acknowledged_at, "note": "Campaign candidate formally acknowledged by investigator."})
    if campaign.resolved_at:
        investigator_history.append({"action": "resolved", "timestamp": campaign.resolved_at, "note": "Campaign investigation resolved."})
    if campaign.dismissed_at:
        investigator_history.append({"action": "dismissed", "timestamp": campaign.dismissed_at, "note": "Campaign candidate dismissed."})
    for ev in campaign.events:
        if ev.event_type == "action":
            investigator_history.append({
                "action": ev.metadata.get("status", "action"),
                "timestamp": ev.event_timestamp,
                "note": ev.summary,
            })

    # 8. Forensic Disclaimers & Methodology Limitations
    contradictions_and_limitations = list(campaign.contradictions)
    if not campaign.alert_ids:
        contradictions_and_limitations.append("Absence of corroborated market anomaly alerts: Price/volume impact on participants remains unverified.")
    contradictions_and_limitations.append("Temporal proximity caution: Simultaneous promotion across securities does not establish financial conspiracy without forensic ownership records.")
    contradictions_and_limitations.append("Independent verification mandatory: Public regulatory databases (SEBI SCORES, BSE/NSE Corporate Announcements) must be cross-referenced.")

    dossier = {
        "schema_version": "dakota-forensic-dossier-v1.0",
        "dossier_id": dossier_id,
        "campaign_id": campaign.campaign_id,
        "title": campaign.name,
        "status": campaign.status.value,
        "tier": campaign.tier.value,
        "confidence_score": campaign.confidence_score,
        "time_window_hours": campaign.time_window_hours,
        "first_seen_utc": campaign.first_seen,
        "last_seen_utc": campaign.last_seen,
        "exported_at_utc": export_ts,
        "securities": enriched_securities,
        "public_actors": public_actors,
        "shared_urls": campaign.shared_urls,
        "shared_fingerprints": campaign.shared_fingerprints,
        "relationship_types": campaign.relationship_types,
        "relationship_explanations": campaign.relationship_explanations,
        "promotional_events": promotional_events,
        "market_alerts": alert_details,
        "jev_intelligence": jev_intel,
        "graph_summary": graph_summary,
        "contradictions_and_limitations": contradictions_and_limitations,
        "investigator_notes": campaign.notes,
        "investigator_history": investigator_history,
        "methodology": (
            "Dakota correlates publicly observable financial promotions, standardized copy fingerprints, "
            "temporal clustering, and exchange surveillance alerts. All associations reflect probabilistic "
            "and factual evidence matching, not definitive regulatory findings."
        ),
        "regulatory_disclaimer": (
            "CONFIDENTIAL INVESTIGATIVE DOSSIER FOR ANALYTICAL AND REGULATORY REVIEW ONLY. "
            "This report is generated automatically by Dakota Financial Intelligence. It documents observed "
            "correlations across public sources and exchange data. It does NOT constitute an official SEBI finding, "
            "adjudicated securities fraud determination, legal accusation, or financial investment advice."
        ),
    }

    return dossier
