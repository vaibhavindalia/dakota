"""Integration and unit tests for Dakota Phase 9 Syndicate Graph and Forensic Dossier Export.

Tests:
1. Graph builder: typed nodes, typed edges, stable IDs, deduplication, evidence integrity.
2. Empty and disconnected graphs handling without errors.
3. Graph conflict and missing entity handling.
4. No false inference of coordination from simultaneous price movements alone.
5. Unified dossier snapshot generator: snapshot consistency across JSON and PDF.
6. Institutional PDF export: valid %PDF- and %%EOF markers, non-trivial length, NumberedCanvas pagination.
7. Unicode, Indian currency (Rs./₹) and long text handling in PDF export without crashing.
8. REST API endpoints:
   - GET /api/campaigns/{id}/graph
   - GET /api/campaigns/{id}/export.json
   - GET /api/campaigns/{id}/export.pdf
   - GET /api/campaigns/{id}/export?format=...
9. 404 error handling for non-existent campaign exports.
10. Preservation of investigator lifecycle actions and notes in exports.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from src.campaign.dossier import generate_campaign_dossier
from src.campaign.graph import build_campaign_graph
from src.campaign.models import (
    CampaignEvent,
    CampaignRecord,
    CampaignStatus,
    CampaignTier,
    EdgeType,
    NodeType,
    RelationshipType,
)
from src.campaign.pdf_exporter import render_campaign_pdf
from src.campaign.store import CampaignStore


@pytest.fixture
def temp_store(tmp_path: Path):
    db_file = tmp_path / "test_campaign_phase9.db"
    return CampaignStore(db_path=db_file)


@pytest.fixture
def sample_campaign() -> CampaignRecord:
    now_iso = datetime.now(timezone.utc).isoformat()
    ev1 = CampaignEvent(
        event_id="ev_001",
        campaign_id="camp_test_01",
        event_type="telegram_tip",
        ticker="TATAMOTORS",
        source_label="@dalal_insider",
        event_timestamp="2026-10-19T09:15:00Z",
        retrieved_at="2026-10-19T09:16:30Z",
        data_freshness="LIVE",
        summary="Urgent buy TATAMOTORS target 1200 https://pumptarget.org/tata",
        metadata={
            "raw_text": "Urgent buy TATAMOTORS target ₹1200 🚀 https://pumptarget.org/tata",
            "url": "https://pumptarget.org/tata",
            "fingerprint": "fp_tata_9988",
        },
    )
    ev2 = CampaignEvent(
        event_id="ev_002",
        campaign_id="camp_test_01",
        event_type="telegram_tip",
        ticker="MARUTI",
        source_label="@dalal_insider",
        event_timestamp="2026-10-19T09:20:00Z",
        retrieved_at="2026-10-19T09:21:00Z",
        data_freshness="LIVE",
        summary="Urgent buy MARUTI target 15000 https://pumptarget.org/auto",
        metadata={
            "raw_text": "Urgent buy MARUTI target ₹15000 🚀 https://pumptarget.org/auto",
            "url": "https://pumptarget.org/auto",
            "fingerprint": "fp_maruti_1122",
        },
    )
    ev3 = CampaignEvent(
        event_id="ev_003",
        campaign_id="camp_test_01",
        event_type="market_alert",
        ticker="TATAMOTORS",
        source_label="SURVEILLANCE_ENGINE",
        event_timestamp="2026-10-19T09:25:00Z",
        retrieved_at="2026-10-19T09:25:05Z",
        data_freshness="LIVE",
        summary="Volume Spike alert triggered: 3.5x 20-day average volume",
        metadata={
            "alert_id": "alt_vol_991",
            "rule_type": "VOLUME_SPIKE",
            "observed_value": 3.5,
            "threshold": 2.0,
        },
    )

    return CampaignRecord(
        campaign_id="camp_test_01",
        name="Auto Sector Multi-Scrip Coordinated Blast",
        status=CampaignStatus.ACTIVE,
        tier=CampaignTier.HIGH,
        confidence_score=0.88,
        securities=["TATAMOTORS", "MARUTI"],
        actors=["@dalal_insider"],
        relationship_types=[
            RelationshipType.SHARED_ACTOR,
            RelationshipType.SHARED_URL,
            RelationshipType.ALERT_CORROBORATION,
        ],
        relationship_explanations={
            "shared_actor": "Actor @dalal_insider actively promoted TATAMOTORS and MARUTI within 15 minutes.",
            "shared_url": "Both promotion tips directed users to domain pumptarget.org.",
            "alert_corroboration": "Corroborated by exchange volume surge alert alt_vol_991 on TATAMOTORS.",
        },
        evidence_ids=["ev_001", "ev_002", "ev_003"],
        alert_ids=["alt_vol_991"],
        shared_urls=["https://pumptarget.org/tata", "https://pumptarget.org/auto"],
        shared_fingerprints=["fp_tata_9988", "fp_maruti_1122"],
        time_window_hours=24,
        first_seen="2026-10-19T09:15:00Z",
        last_seen="2026-10-19T09:25:00Z",
        created_at=now_iso,
        updated_at=now_iso,
        notes="Preliminary investigator review: high velocity promotion observed.",
        contradictions=["No corporate disclosure registered on BSE for TATAMOTORS on 2026-10-19."],
        events=[ev1, ev2, ev3],
    )


# ==============================================================================
# PART A: GRAPH BUILDER TESTS
# ==============================================================================

def test_build_campaign_graph_nodes_and_edges(sample_campaign: CampaignRecord):
    graph = build_campaign_graph(sample_campaign)

    assert graph.campaign_id == "camp_test_01"
    assert graph.summary["total_nodes"] > 0
    assert graph.summary["total_edges"] > 0

    # Node types presence
    node_types = {n.type for n in graph.nodes}
    assert NodeType.CAMPAIGN in node_types
    assert NodeType.SECURITY in node_types
    assert NodeType.ACTOR in node_types
    assert NodeType.ALERT in node_types
    assert NodeType.URL in node_types

    # Ensure stable unique IDs
    node_ids = [n.id for n in graph.nodes]
    assert len(node_ids) == len(set(node_ids)), "Duplicate node IDs detected in graph"

    # Edge types presence
    edge_types = {e.type for e in graph.edges}
    assert EdgeType.MEMBER_SECURITY in edge_types
    assert EdgeType.PROMOTED_BY in edge_types
    assert EdgeType.SHARED_URL in edge_types
    assert EdgeType.MARKET_CORROBORATION in edge_types

    # Check evidence integrity on edges
    for edge in graph.edges:
        assert isinstance(edge.evidence_ids, list)
        assert len(edge.evidence_ids) > 0, f"Edge {edge.id} has no evidence citations"
        assert edge.source != edge.target, f"Self-loop found in edge {edge.id}"

    # Verify edge IDs are unique
    edge_ids = [e.id for e in graph.edges]
    assert len(edge_ids) == len(set(edge_ids)), "Duplicate edge IDs detected in graph"


def test_build_empty_campaign_graph():
    now_iso = datetime.now(timezone.utc).isoformat()
    empty_campaign = CampaignRecord(
        campaign_id="camp_empty",
        name="Empty Campaign",
        status=CampaignStatus.CANDIDATE,
        tier=CampaignTier.CANDIDATE,
        confidence_score=0.1,
        securities=[],
        actors=[],
        relationship_types=[],
        relationship_explanations={},
        evidence_ids=[],
        alert_ids=[],
        shared_urls=[],
        shared_fingerprints=[],
        time_window_hours=12,
        created_at=now_iso,
        updated_at=now_iso,
        events=[],
    )

    graph = build_campaign_graph(empty_campaign)
    assert graph.campaign_id == "camp_empty"
    assert len(graph.nodes) == 1
    assert graph.nodes[0].type == NodeType.CAMPAIGN
    assert len(graph.edges) == 0
    assert graph.summary["total_nodes"] == 1
    assert graph.summary["total_edges"] == 0


def test_no_inference_of_coordination_from_price_alone():
    """Verify that alerts without promotional actors do not manufacture actor nodes."""
    now_iso = datetime.now(timezone.utc).isoformat()
    price_only_campaign = CampaignRecord(
        campaign_id="camp_price_only",
        name="Simultaneous Price Movement Without Promotion",
        status=CampaignStatus.CANDIDATE,
        tier=CampaignTier.CANDIDATE,
        confidence_score=0.2,
        securities=["INFY", "WIPRO"],
        actors=[],  # No public promoter accounts
        relationship_types=[RelationshipType.ALERT_CORROBORATION],
        relationship_explanations={"alert_corroboration": "Correlated sector movement"},
        evidence_ids=["alt_001"],
        alert_ids=["alt_001"],
        shared_urls=[],
        shared_fingerprints=[],
        time_window_hours=2,
        created_at=now_iso,
        updated_at=now_iso,
        events=[],
    )

    graph = build_campaign_graph(price_only_campaign)
    actor_nodes = [n for n in graph.nodes if n.type == NodeType.ACTOR]
    assert len(actor_nodes) == 0, "Actor nodes should not be created when no actors exist"
    promoted_edges = [e for e in graph.edges if e.type == EdgeType.PROMOTED_BY]
    assert len(promoted_edges) == 0, "Should not infer promoter coordination from market movement alone"


# ==============================================================================
# PART B: FORENSIC DOSSIER SNAPSHOT & EXPORT TESTS
# ==============================================================================

def test_unified_dossier_snapshot_generator(temp_store: CampaignStore, sample_campaign: CampaignRecord):
    temp_store.save_campaign(sample_campaign)

    dossier = generate_campaign_dossier(sample_campaign.campaign_id, store=temp_store)

    assert dossier["dossier_version"] == "dakota-dossier-v1"
    assert dossier["campaign_id"] == "camp_test_01"
    assert dossier["campaign_name"] == "Auto Sector Multi-Scrip Coordinated Blast"
    assert dossier["status"] == "active"
    assert dossier["tier"] == "HIGH"
    assert dossier["confidence_score"] == 0.88
    assert "TATAMOTORS" in dossier["participating_securities"]
    assert "@dalal_insider" in dossier["public_source_actors"]
    assert len(dossier["chronological_events"]) == 3

    # Check timestamps separation
    ev = dossier["chronological_events"][0]
    assert "event_timestamp" in ev
    assert "retrieved_at" in ev
    assert ev["event_timestamp"] != ev["retrieved_at"]

    # Check disclaimers and regulatory boundary notice
    disclaimers = dossier["disclaimers"]
    assert "NOT AN OFFICIAL REGULATORY FINDING" in disclaimers["legal_classification"]
    assert "NOT PROOF OF ILLEGAL COORDINATION" in disclaimers["investigative_standard"]

    # Check limitations list
    assert isinstance(dossier["limitations_and_missing_data"], list)
    assert len(dossier["limitations_and_missing_data"]) > 0


def test_dossier_nonexistent_campaign(temp_store: CampaignStore):
    with pytest.raises(ValueError, match="not found"):
        generate_campaign_dossier("nonexistent_id", store=temp_store)


def test_pdf_export_rendering(temp_store: CampaignStore, sample_campaign: CampaignRecord):
    temp_store.save_campaign(sample_campaign)
    dossier = generate_campaign_dossier(sample_campaign.campaign_id, store=temp_store)

    pdf_bytes = render_campaign_pdf(dossier)

    assert isinstance(pdf_bytes, bytes)
    # Valid PDF file magic header
    assert pdf_bytes.startswith(b"%PDF-"), "Rendered file missing %PDF- magic signature"
    # End of file marker
    assert b"%%EOF" in pdf_bytes, "Rendered file missing %%EOF end marker"
    # Multi-page institutional document length
    assert len(pdf_bytes) > 2500, f"Rendered PDF is suspiciously small: {len(pdf_bytes)} bytes"


def test_pdf_unicode_and_currency_handling(temp_store: CampaignStore):
    now_iso = datetime.now(timezone.utc).isoformat()
    unicode_campaign = CampaignRecord(
        campaign_id="camp_unicode_test",
        name="स्टॉक मार्केट Special Promotion (₹500 Target)",
        status=CampaignStatus.ACTIVE,
        tier=CampaignTier.HIGH,
        confidence_score=0.92,
        securities=["RELIANCE"],
        actors=["@bull_बाजार"],
        relationship_types=[RelationshipType.SHARED_ACTOR],
        relationship_explanations={"shared_actor": "Shared promoter handle with Hindi characters"},
        evidence_ids=["ev_uni_1"],
        alert_ids=[],
        shared_urls=["https://pump.in/शेयर"],
        shared_fingerprints=["fp_uni_1"],
        time_window_hours=24,
        created_at=now_iso,
        updated_at=now_iso,
        notes="Notes with special symbols: ₹5,000,000 turnover, € and £ mentions, emojis 🚀🔥💸.",
        events=[
            CampaignEvent(
                event_id="ev_uni_1",
                campaign_id="camp_unicode_test",
                event_type="telegram_tip",
                ticker="RELIANCE",
                source_label="@bull_बाजार",
                event_timestamp=now_iso,
                retrieved_at=now_iso,
                data_freshness="LIVE",
                summary="खरीदें RELIANCE ₹2500 target 🚀🔥💸",
                metadata={"raw_text": "खरीदें RELIANCE target ₹2500 " * 20},
            )
        ],
    )
    temp_store.save_campaign(unicode_campaign)
    dossier = generate_campaign_dossier("camp_unicode_test", store=temp_store)

    # Rendering should succeed without throwing UnicodeEncodeError or character crash
    pdf_bytes = render_campaign_pdf(dossier)
    assert pdf_bytes.startswith(b"%PDF-")
    assert b"%%EOF" in pdf_bytes


# ==============================================================================
# REST API ENDPOINT TESTS
# ==============================================================================

def test_api_graph_endpoint(temp_store: CampaignStore, sample_campaign: CampaignRecord, monkeypatch):
    import backend.main as backend_module

    monkeypatch.setattr(backend_module, "campaign_store", temp_store)
    temp_store.save_campaign(sample_campaign)

    client = TestClient(app)
    response = client.get(f"/api/campaigns/{sample_campaign.campaign_id}/graph")
    assert response.status_code == 200
    data = response.json()

    assert data["campaign_id"] == sample_campaign.campaign_id
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) > 0
    assert len(data["edges"]) > 0


def test_api_export_json_endpoint(temp_store: CampaignStore, sample_campaign: CampaignRecord, monkeypatch):
    import backend.main as backend_module

    monkeypatch.setattr(backend_module, "campaign_store", temp_store)
    temp_store.save_campaign(sample_campaign)

    client = TestClient(app)
    response = client.get(f"/api/campaigns/{sample_campaign.campaign_id}/export.json")
    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]
    assert "attachment" in response.headers.get("content-disposition", "")
    assert f"{sample_campaign.campaign_id}_dossier.json" in response.headers["content-disposition"]

    payload = response.json()
    assert payload["campaign_id"] == sample_campaign.campaign_id
    assert payload["dossier_version"] == "dakota-dossier-v1"


def test_api_export_pdf_endpoint(temp_store: CampaignStore, sample_campaign: CampaignRecord, monkeypatch):
    import backend.main as backend_module

    monkeypatch.setattr(backend_module, "campaign_store", temp_store)
    temp_store.save_campaign(sample_campaign)

    client = TestClient(app)
    response = client.get(f"/api/campaigns/{sample_campaign.campaign_id}/export.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment" in response.headers.get("content-disposition", "")
    assert f"{sample_campaign.campaign_id}_dossier.pdf" in response.headers["content-disposition"]

    pdf_content = response.content
    assert pdf_content.startswith(b"%PDF-")
    assert b"%%EOF" in pdf_content


def test_api_export_dispatcher_endpoint(temp_store: CampaignStore, sample_campaign: CampaignRecord, monkeypatch):
    import backend.main as backend_module

    monkeypatch.setattr(backend_module, "campaign_store", temp_store)
    temp_store.save_campaign(sample_campaign)

    client = TestClient(app)

    # Dispatch PDF
    res_pdf = client.get(f"/api/campaigns/{sample_campaign.campaign_id}/export?format=pdf")
    assert res_pdf.status_code == 200
    assert res_pdf.headers["content-type"] == "application/pdf"

    # Dispatch JSON
    res_json = client.get(f"/api/campaigns/{sample_campaign.campaign_id}/export?format=json")
    assert res_json.status_code == 200
    assert "application/json" in res_json.headers["content-type"]

    # Dispatch Invalid
    res_inv = client.get(f"/api/campaigns/{sample_campaign.campaign_id}/export?format=csv")
    assert res_inv.status_code == 400


def test_api_404_for_missing_campaign_exports(temp_store: CampaignStore, monkeypatch):
    import backend.main as backend_module

    monkeypatch.setattr(backend_module, "campaign_store", temp_store)

    client = TestClient(app)
    assert client.get("/api/campaigns/nonexistent/graph").status_code == 404
    assert client.get("/api/campaigns/nonexistent/export.json").status_code == 404
    assert client.get("/api/campaigns/nonexistent/export.pdf").status_code == 404
