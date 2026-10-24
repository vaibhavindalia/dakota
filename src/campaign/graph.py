"""Syndicate Relationship Graph Builder for Dakota Campaign Intelligence.

Transforms persistent CampaignRecords into typed, evidence-backed graph
representations connecting campaigns, securities, promoters, alerts, URLs,
and message events with deterministic layout properties and citation integrity.
"""
from __future__ import annotations

import hashlib
from typing import Any

from src.alerts.store import alert_store
from src.campaign.models import (
    CampaignGraph,
    CampaignRecord,
    CampaignTier,
    EdgeType,
    GraphEdge,
    GraphNode,
    NodeType,
    RelationshipType,
)


def _slug(text: str) -> str:
    """Generate deterministic short alphanumeric hash slug."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def build_campaign_graph(campaign: CampaignRecord) -> CampaignGraph:
    """Build a typed, schema-validated relationship graph for a campaign entity."""
    nodes: dict[str, GraphNode] = {}
    edges: dict[str, GraphEdge] = {}

    # 1. Central Campaign Node
    cmp_id = f"cmp_{campaign.campaign_id}"
    nodes[cmp_id] = GraphNode(
        id=cmp_id,
        type=NodeType.CAMPAIGN,
        label=campaign.name,
        sublabel=f"{campaign.tier.value} Confidence ({int(campaign.confidence_score * 100)}%)",
        status=campaign.status.value,
        properties={
            "campaign_id": campaign.campaign_id,
            "status": campaign.status.value,
            "tier": campaign.tier.value,
            "confidence_score": campaign.confidence_score,
            "time_window_hours": campaign.time_window_hours,
            "first_seen": campaign.first_seen,
            "last_seen": campaign.last_seen,
        },
        evidence_ids=campaign.evidence_ids,
    )

    # 2. Security Nodes
    for tk in campaign.securities:
        clean_tk = tk.upper().strip()
        sec_id = f"sec_{clean_tk}"
        nodes[sec_id] = GraphNode(
            id=sec_id,
            type=NodeType.SECURITY,
            label=clean_tk,
            sublabel="NSE / BSE Listed",
            status="active",
            properties={
                "ticker": clean_tk,
                "exchange": "NSE/BSE",
                "campaign_id": campaign.campaign_id,
            },
            evidence_ids=[ev for ev in campaign.evidence_ids if clean_tk in ev],
        )

        # Edge: Campaign -> Security
        e_id = f"edge_cmp_sec_{clean_tk}"
        edges[e_id] = GraphEdge(
            id=e_id,
            source=cmp_id,
            target=sec_id,
            type=EdgeType.MEMBER_SECURITY,
            label="Participating Security",
            rationale=f"Security {clean_tk} identified as participant in syndicate campaign {campaign.campaign_id}.",
            confidence=campaign.confidence_score,
            evidence_references=campaign.evidence_ids,
        )

    # 3. Promoter / Source Actor Nodes
    for actor in campaign.actors:
        clean_actor = actor.strip()
        act_id = f"act_{_slug(clean_actor)}"
        nodes[act_id] = GraphNode(
            id=act_id,
            type=NodeType.ACTOR,
            label=clean_actor,
            sublabel="Public Channel / Promoter",
            status="unverified_identity",
            properties={
                "handle": clean_actor,
                "platform": "telegram" if clean_actor.startswith("@") or "telegram" in clean_actor.lower() else "intake",
                "attribution": "Public broadcast channel; legal individual identity unverified.",
            },
            evidence_ids=campaign.evidence_ids,
        )

        # Connect Actor to each Security promoted in this campaign
        for tk in campaign.securities:
            clean_tk = tk.upper().strip()
            sec_id = f"sec_{clean_tk}"
            e_id = f"edge_act_sec_{_slug(clean_actor)}_{clean_tk}"
            edges[e_id] = GraphEdge(
                id=e_id,
                source=act_id,
                target=sec_id,
                type=EdgeType.PROMOTED_BY,
                label="Promotes Security",
                rationale=f"Public promoter '{clean_actor}' published directional tips/recommendations for {clean_tk}.",
                confidence=0.85,
                evidence_references=[ev for ev in campaign.evidence_ids if clean_tk in ev] or campaign.evidence_ids,
            )

    # 4. Corroborating Market Alerts
    for aid in campaign.alert_ids:
        alt = alert_store.get_alert(aid)
        alt_id = f"alt_{aid}"
        rule_name = alt.rule_name if alt else "Market Alert"
        severity = alt.severity.value if alt else "warning"
        ticker = alt.ticker if alt else (campaign.securities[0] if campaign.securities else "UNKNOWN")

        nodes[alt_id] = GraphNode(
            id=alt_id,
            type=NodeType.ALERT,
            label=rule_name,
            sublabel=f"{severity.upper()} • {ticker}",
            status=severity,
            properties={
                "alert_id": aid,
                "rule_name": rule_name,
                "severity": severity,
                "ticker": ticker,
                "trigger_value": alt.trigger_value if alt else None,
                "threshold_value": alt.threshold_value if alt else None,
                "observation_timestamp": alt.observation_timestamp if alt else None,
                "data_freshness": alt.data_freshness if alt else "LIVE",
            },
            evidence_ids=[aid],
        )

        # Edge: Alert -> Security
        sec_id = f"sec_{ticker}"
        if sec_id in nodes:
            e_id = f"edge_alt_sec_{aid}"
            edges[e_id] = GraphEdge(
                id=e_id,
                source=alt_id,
                target=sec_id,
                type=EdgeType.MARKET_CORROBORATION,
                label="Corroborates Anomaly",
                rationale=(
                    f"Exchange alert '{rule_name}' ({severity}) corroborated market anomaly on {ticker} "
                    f"during active promotional window."
                ),
                confidence=0.90,
                evidence_references=[aid],
            )

    # 5. Shared URLs
    for url in campaign.shared_urls:
        clean_url = url.strip()
        url_id = f"url_{_slug(clean_url)}"
        display_label = clean_url.replace("https://", "").replace("http://", "")[:32]
        if len(clean_url) > 35:
            display_label += "..."

        nodes[url_id] = GraphNode(
            id=url_id,
            type=NodeType.URL,
            label=display_label,
            sublabel="Shared Campaign Link",
            status="external_link",
            properties={
                "url": clean_url,
                "domain": clean_url.split("/")[2] if "://" in clean_url else clean_url.split("/")[0],
            },
            evidence_ids=[clean_url],
        )

        # Connect URL to Campaign & Participating Securities
        for tk in campaign.securities:
            clean_tk = tk.upper().strip()
            e_id = f"edge_sec_url_{clean_tk}_{_slug(clean_url)}"
            edges[e_id] = GraphEdge(
                id=e_id,
                source=f"sec_{clean_tk}",
                target=url_id,
                type=EdgeType.SHARED_URL,
                label="Shares Link",
                rationale=f"Promotion on {clean_tk} included shared campaign URL: {clean_url}",
                confidence=0.80,
                evidence_references=[clean_url],
            )

    # 6. Cross-Scrip Peer Relationships
    if len(campaign.securities) >= 2:
        sorted_secs = sorted(campaign.securities)
        for i in range(len(sorted_secs)):
            for j in range(i + 1, len(sorted_secs)):
                tk1 = sorted_secs[i]
                tk2 = sorted_secs[j]

                # Shared message template edge
                if RelationshipType.SHARED_TEMPLATE.value in campaign.relationship_types:
                    e_tmpl = f"edge_peer_tmpl_{tk1}_{tk2}"
                    edges[e_tmpl] = GraphEdge(
                        id=e_tmpl,
                        source=f"sec_{tk1}",
                        target=f"sec_{tk2}",
                        type=EdgeType.SHARED_TEMPLATE,
                        label="Shared Message Template",
                        rationale=f"Identical or near-duplicate normalized promotional copy template circulated across {tk1} and {tk2}.",
                        confidence=0.85,
                        evidence_references=campaign.shared_fingerprints,
                    )

                # Temporal burst edge
                if RelationshipType.TEMPORAL_BURST.value in campaign.relationship_types:
                    e_burst = f"edge_peer_burst_{tk1}_{tk2}"
                    edges[e_burst] = GraphEdge(
                        id=e_burst,
                        source=f"sec_{tk1}",
                        target=f"sec_{tk2}",
                        type=EdgeType.TEMPORAL_BURST,
                        label="Synchronized Burst",
                        rationale=f"Tip volume and promotional bursts on {tk1} and {tk2} occurred within {campaign.time_window_hours}h window.",
                        confidence=0.75,
                        evidence_references=campaign.evidence_ids,
                    )

    # 7. Timeline Tip / Message Events (up to 8 most relevant events to prevent graph overload)
    sample_events = campaign.events[:8] if campaign.events else []
    for ev in sample_events:
        if ev.event_type == "tip":
            ev_node_id = f"ev_{_slug(ev.event_id)}"
            nodes[ev_node_id] = GraphNode(
                id=ev_node_id,
                type=NodeType.MESSAGE,
                label=f"Tip: {ev.ticker}",
                sublabel=f"{ev.source_label} • {ev.event_timestamp[:10]}",
                status="observed_tip",
                properties={
                    "event_id": ev.event_id,
                    "ticker": ev.ticker,
                    "source": ev.source_label,
                    "summary": ev.summary,
                    "event_timestamp": ev.event_timestamp,
                    "retrieved_at": ev.retrieved_at,
                    "data_freshness": ev.data_freshness,
                },
                evidence_ids=[ev.event_id],
            )

            # Edge from event to security
            sec_id = f"sec_{ev.ticker.upper().strip()}"
            if sec_id in nodes:
                e_id = f"edge_ev_sec_{_slug(ev.event_id)}"
                edges[e_id] = GraphEdge(
                    id=e_id,
                    source=ev_node_id,
                    target=sec_id,
                    type=EdgeType.PROMOTED_BY,
                    label="Promotional Tip",
                    rationale=f"Tip event recorded at {ev.event_timestamp} for {ev.ticker}.",
                    confidence=0.90,
                    evidence_references=[ev.event_id],
                )

    # 8. Contradictions & Missing Evidence Nodes
    for i, c in enumerate(campaign.contradictions):
        contra_id = f"contra_{i}_{_slug(c)}"
        nodes[contra_id] = GraphNode(
            id=contra_id,
            type=NodeType.DISCLOSURE,
            label="Limitation / Contradiction",
            sublabel=c[:36] + ("..." if len(c) > 36 else ""),
            status="caution",
            properties={"explanation": c},
            evidence_ids=[],
        )
        e_contra = f"edge_contra_cmp_{i}"
        edges[e_contra] = GraphEdge(
            id=e_contra,
            source=contra_id,
            target=cmp_id,
            type=EdgeType.CONTRADICTED_BY,
            label="Context Limitation",
            rationale=c,
            confidence=0.50,
            evidence_references=[],
        )

    # Missing evidence signals
    missing_evidence: list[str] = []
    if not campaign.alert_ids:
        missing_evidence.append("No corroborating exchange alert recorded yet (awaiting market spike or delivery drop verification).")
    if not campaign.shared_urls:
        missing_evidence.append("No shared external URL identified in promotional copy.")
    if not campaign.actors or any(a == "unverified_source" for a in campaign.actors):
        missing_evidence.append("Promoter channel identity is unverified or operates through anonymous forwarders.")

    metrics = {
        "total_nodes": len(nodes),
        "total_edges": len(edges),
        "securities_count": len(campaign.securities),
        "promoter_count": len(campaign.actors),
        "alert_count": len(campaign.alert_ids),
        "url_count": len(campaign.shared_urls),
        "events_count": len(campaign.events),
    }

    return CampaignGraph(
        campaign_id=campaign.campaign_id,
        name=campaign.name,
        tier=campaign.tier,
        status=campaign.status,
        confidence_score=campaign.confidence_score,
        nodes=list(nodes.values()),
        edges=list(edges.values()),
        metrics=metrics,
        contradictions=campaign.contradictions,
        missing_evidence=missing_evidence,
    )
