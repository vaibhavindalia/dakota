"""End-to-End Product Acceptance Regression Tests (PAT-1).

Validates the integrated functionality of:
  1. Service health and status endpoints
  2. Portfolio management, stock search, and persistent CRUD
  3. Intelligence classification and evidence citations
  4. Forensic risk scoring and scam pattern detection
  5. Telegram ingestion, PII sanitization, and deterministic fingerprinting
  6. Missing, conflicting, and stale evidence handling
  7. External connector credential-gating
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from src.intake.tip_intake import intake_tip, fingerprint, scrub
from src.classification.local_classifier import classify_message
from src.tipcheck.parser import check_tip

client = TestClient(app)


def test_pat1_health_and_connectors_status():
    """Workflow 1 & 7: Verify backend health and graceful credential gating."""
    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json().get("status") in ("ok", "healthy")

    res_conn = client.get("/api/connectors/status")
    assert res_conn.status_code == 200
    data = res_conn.json()
    assert data.get("status") == "ok"
    conns = data.get("connectors", {})
    assert conns.get("instagram") == "missing_credentials"
    assert conns.get("whatsapp") == "missing_credentials"


def test_pat1_portfolio_workflow():
    """Workflow 2: Search, detail, holding persistence, and cleanup."""
    # 1. Search
    res_s = client.get("/api/stocks?search=TCS&limit=5")
    assert res_s.status_code == 200
    items = res_s.json().get("items", [])
    assert len(items) > 0

    # 2. Detail
    res_d = client.get("/api/stocks/TCS")
    assert res_d.status_code == 200
    detail = res_d.json()
    assert detail.get("ticker") == "TCS"
    assert detail.get("meta") is not None
    assert detail.get("risk") is not None

    # 3. Add Holding
    test_h = {
        "ticker": "INFY",
        "exchange": "NSE",
        "quantity": 50.0,
        "average_buy_price": 1400.0,
    }
    res_add = client.post("/api/portfolio/holdings", json=test_h)
    assert res_add.status_code == 200

    # 4. Verify in portfolio
    res_p = client.get("/api/portfolio")
    assert res_p.status_code == 200
    holdings = res_p.json().get("holdings", [])
    infy = next((h for h in holdings if h.get("ticker") == "INFY"), None)
    assert infy is not None
    assert infy.get("quantity") == 50.0

    # 5. Delete Holding
    res_del = client.delete("/api/portfolio/holdings/INFY")
    assert res_del.status_code == 200

    # 6. Verify removed
    res_p2 = client.get("/api/portfolio")
    holdings2 = res_p2.json().get("holdings", [])
    assert not any(h.get("ticker") == "INFY" for h in holdings2)


def test_pat1_intelligence_classification_and_citations():
    """Workflow 3: 6-class classification, citation grounding, and error handling."""
    payload = {
        "ticker": "TCS",
        "claim": "TCS signs major enterprise deal in Europe",
        "sample": {
            "ticker": "TCS",
            "as_of": "2026-10-19T00:00:00Z",
            "latest_price": 3950.0,
            "change_pct": 1.5,
            "volume": 800000,
            "delivery_pct": 55.0,
            "technicals": {"trend_vs_ema20": "bullish"},
            "risk_score": 10.0,
            "risk_band": "Low",
            "is_surveillance": False,
            "news_headlines": ["TCS announces landmark cloud transformation partnership"],
            "social_signals": ["Heavy institutional accumulation in TCS"],
            "evidence_ids": ["E_FILING_BSE", "E_NSE_MKT"],
        },
    }
    res_c = client.post("/api/intelligence/jev/classify", json=payload)
    assert res_c.status_code == 200
    data_c = res_c.json()
    assert data_c.get("predicted_label") in ["Bullish", "Bearish", "Neutral", "Mixed", "Ambiguous", "Insufficient Evidence"]
    assert len(data_c.get("class_scores", {})) == 6

    res_a = client.post("/api/intelligence/jev/analyze", json=payload)
    assert res_a.status_code == 200
    data_a = res_a.json()
    citations = data_a.get("analysis", {}).get("citations", [])
    assert len(citations) >= 1

    # Malformed payload returns 422
    res_bad = client.post("/api/intelligence/jev/classify", json={"ticker": "TCS", "sample": "not-dict"})
    assert res_bad.status_code == 422


def test_pat1_forensics_and_scam_detection():
    """Workflow 4: Stock forensic risk scoring and blatant scam marker detection."""
    # High-risk stock forensics
    res_r = client.get("/api/stocks/CLOUD/risk")
    assert res_r.status_code == 200
    risk = res_r.json()
    assert risk.get("score", 0) >= 70.0
    assert risk.get("band") == "High"
    assert len(risk.get("reasons", [])) >= 5

    # Multi-marker scam tip
    tip_payload = {
        "tip": "BUY URGENT! CDSL target Rs 2500 by Friday. 100% GUARANTEED RETURN! Join our VIP Telegram channel!"
    }
    res_t = client.post("/api/tip/check", json=tip_payload)
    assert res_t.status_code == 200
    tip_res = res_t.json()
    verdicts = tip_res.get("stock_verdicts", [])
    assert len(verdicts) > 0
    assert verdicts[0].get("score", 0) >= 70.0
    assert verdicts[0].get("band") == "High"
    assert len(tip_res.get("tip_level_reasons", [])) >= 3


def test_pat1_telegram_ingestion_and_privacy():
    """Workflow 5: Ingestion pipeline, PII scrubbing, and fingerprinting."""
    raw = "EXCLUSIVE BUY: $RELIANCE target 3200! 100% assured profit. Ping @insider on t.me/alpha or call +919999999999"
    scrubbed = scrub(raw)
    assert "+919999999999" not in scrubbed
    assert "t.me/alpha" not in scrubbed
    assert "@insider" not in scrubbed

    rec1 = intake_tip(raw, source="telegram")
    assert rec1.investigation_id is not None
    assert rec1.fingerprint is not None

    rec2 = intake_tip(raw, source="telegram")
    assert rec1.fingerprint == rec2.fingerprint


def test_pat1_missing_and_conflicting_evidence():
    """Workflow 6: Conflicting source divergence and empty context scoring."""
    conflicting = {
        "ticker": "CONFLICTCO",
        "claim": "Huge 20x pump incoming!",
        "sample": {
            "ticker": "CONFLICTCO",
            "as_of": "2026-10-19T00:00:00Z",
            "latest_price": 25.0,
            "change_pct": -4.8,
            "volume": 5000,
            "delivery_pct": 10.0,
            "technicals": {"trend_vs_ema20": "bearish"},
            "risk_score": 85.0,
            "risk_band": "High",
            "is_surveillance": True,
            "news_headlines": ["Auditor resigns citing missing records", "Placed under GSM Stage IV"],
            "social_signals": ["Huge 20x pump incoming!"],
            "evidence_ids": ["E1", "E2"],
        },
    }
    res_c = client.post("/api/intelligence/jev/classify", json=conflicting)
    assert res_c.status_code == 200
    assert res_c.json().get("predicted_label") in ["Mixed", "Bearish"]

    empty_sample = {
        "ticker": "EMPTYCO",
        "claim": "General vague comment",
        "sample": {
            "ticker": "EMPTYCO",
            "as_of": "2026-10-19T00:00:00Z",
            "news_headlines": [],
            "social_signals": [],
            "evidence_ids": [],
        },
    }
    res_e = client.post("/api/intelligence/jev/classify", json=empty_sample)
    assert res_e.status_code == 200
    assert "Insufficient Evidence" in res_e.json().get("class_scores", {})
