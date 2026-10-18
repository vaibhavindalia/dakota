"""API integration tests for Dakota Intelligence endpoints."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_api_intelligence_status():
    res = client.get("/api/intelligence/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "online"
    assert "provider" in data
    assert "capabilities" in data


def test_api_intelligence_query():
    res = client.post("/api/intelligence/query", json={"query": "What is the risk score for VARANIUM?"})
    assert res.status_code == 200
    data = res.json()
    assert "summary" in data
    assert "detailed_text" in data
    assert "evidence_items" in data
    assert "citations" in data
    assert len(data["evidence_items"]) > 0


def test_api_intelligence_search():
    res = client.get("/api/intelligence/search?search=VARANIUM&limit=5")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["total"] > 0
    assert len(data["results"]) > 0


def test_api_intelligence_conversations_flow():
    # 1. Create session
    create_res = client.post("/api/intelligence/conversations", json={"title": "Forensic Session Test"})
    assert create_res.status_code == 200
    conv = create_res.json()
    cid = conv["id"]

    # 2. List sessions
    list_res = client.get("/api/intelligence/conversations")
    assert list_res.status_code == 200
    convs = list_res.json().get("conversations", [])
    assert any(c["id"] == cid for c in convs)

    # 3. Get history
    hist_res = client.get(f"/api/intelligence/conversations/{cid}")
    assert hist_res.status_code == 200
    assert hist_res.json()["conversation_id"] == cid

    # 4. Delete session
    del_res = client.delete(f"/api/intelligence/conversations/{cid}")
    assert del_res.status_code == 200
    assert del_res.json()["deleted"] == cid


def test_api_intelligence_report_generation():
    res = client.post("/api/intelligence/report", json={"ticker": "VARANIUM", "report_type": "company_brief"})
    assert res.status_code == 200
    data = res.json()
    assert "report" in data
    assert "markdown" in data
    assert "html" in data
    assert data["report"]["title"].startswith("Dakota Intelligence Brief")
