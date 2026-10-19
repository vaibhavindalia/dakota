"""Unit and Integration Tests for JEV Intelligence API Endpoints."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_jev_models_endpoint(client):
    response = client.get("/api/intelligence/jev/models")
    assert response.status_code == 200
    data = response.json()
    assert "active_model_id" in data
    assert "backend" in data
    assert "supported_tasks" in data
    assert "sentiment_divergence" in data["supported_tasks"]


def test_jev_classify_endpoint(client):
    payload = {
        "ticker": "CDSL",
        "claim": "CDSL target ₹1,500 breakout buy immediately!",
    }
    response = client.post("/api/intelligence/jev/classify", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "predicted_label" in data
    assert "confidence" in data
    assert len(data["class_scores"]) == 6
    assert "Ambiguous" in data["class_scores"]
    assert "Insufficient Evidence" in data["class_scores"]


def test_jev_analyze_endpoint(client):
    payload = {
        "ticker": "CDSL",
        "claim": "Massive target ₹1500 guaranteed returns VIP group",
    }
    response = client.post("/api/intelligence/jev/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "prediction" in data
    assert "analysis" in data
    analysis = data["analysis"]
    assert analysis["ticker"] == "CDSL"
    assert "executive_summary" in analysis
    assert "citations" in analysis
    assert "disclaimer" in analysis


def test_jev_benchmark_endpoint(client):
    response = client.get("/api/intelligence/jev/benchmark?n_splits=2&purge_hours=24")
    assert response.status_code == 200
    data = response.json()
    assert "report" in data
    assert "markdown_table" in data
    report = data["report"]
    assert report["total_samples"] > 0
    assert "Majority Baseline" in report["evaluated_models"]
    assert "TF-IDF + LogReg" in report["evaluated_models"]
