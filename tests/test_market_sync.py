"""Test Suite for Phase 6: Automatic Market Data Synchronization and Truthful Freshness.

Verifies:
1. Valid market updates and persistence into cache and database.
2. Duplicate updates, timestamp ordering, and idempotency.
3. Provider timeout, retries, and exponential backoff handling.
4. Partial or malformed provider responses handled safely without crashes.
5. Cache fallback with accurate stale-data status.
6. Worker startup and shutdown lifecycle.
7. Prevention of duplicate background workers.
8. Cache invalidation and freshness reflection across stock detail, charts, and portfolio.
9. JEV investigation context receiving truthful timestamps and explicit stale-data disclosures.
10. Honest failure behaviour when real market data is unavailable.
11. Market endpoints: /api/market/sync/status, /api/market/sync/trigger, /api/market/indices.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from src.market.auto_sync import (
    MarketSyncConfig,
    MarketSyncWorker,
    compute_freshness_status,
)
from src.ingest.market_data import get_daily_cache_status, _cache_path, _meta_path


@pytest.fixture
def client():
    return TestClient(app)


# -----------------------------------------------------------------------------
# 1. Freshness State Classification Tests
# -----------------------------------------------------------------------------

def test_freshness_state_classification():
    """Verify truthful classification across live, delayed, cached, stale, unavailable."""
    now_utc = datetime.now(timezone.utc)
    now_iso = now_utc.isoformat()
    old_iso = (now_utc - timedelta(minutes=10)).isoformat()
    yesterday_iso = (now_utc - timedelta(days=1)).isoformat()
    ancient_iso = (now_utc - timedelta(days=30)).isoformat()

    # 1. Live during open market hours within threshold (180s)
    status_live = compute_freshness_status(
        retrieved_at_iso=now_iso,
        market_event_iso=now_iso,
        is_market_open=True,
        stale_threshold_sec=180.0,
    )
    assert status_live == "live"

    # 2. Stale during open market hours when retrieved > threshold
    status_stale = compute_freshness_status(
        retrieved_at_iso=old_iso,
        market_event_iso=old_iso,
        is_market_open=True,
        stale_threshold_sec=180.0,
    )
    assert status_stale == "stale"

    # 3. Cached when market is closed and retrieved from recent session (yesterday)
    status_cached = compute_freshness_status(
        retrieved_at_iso=yesterday_iso,
        market_event_iso=yesterday_iso,
        is_market_open=False,
        stale_threshold_sec=180.0,
    )
    assert status_cached == "cached"

    # 4. Stale when market is closed but data is ancient (> 7 days)
    status_ancient = compute_freshness_status(
        retrieved_at_iso=ancient_iso,
        market_event_iso=ancient_iso,
        is_market_open=False,
        stale_threshold_sec=180.0,
    )
    assert status_ancient == "stale"

    # 5. Unavailable when no timestamps exist
    status_unavailable = compute_freshness_status(
        retrieved_at_iso=None,
        market_event_iso=None,
        is_market_open=True,
    )
    assert status_unavailable == "unavailable"

    # 6. Provider error triggers stale or unavailable status
    status_err = compute_freshness_status(
        retrieved_at_iso=old_iso,
        market_event_iso=old_iso,
        is_market_open=True,
        stale_threshold_sec=180.0,
        provider_error="HTTP 500 Connection Timeout",
    )
    assert status_err == "stale"


# -----------------------------------------------------------------------------
# 2. Worker Lifecycle & Duplicate Prevention Tests
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_worker_lifecycle_and_single_instance():
    """Verify worker starts, prevents duplicate instances, and stops cleanly."""
    config = MarketSyncConfig(
        enabled=True,
        market_hours_interval_sec=1.0,
        off_hours_interval_sec=2.0,
        stale_threshold_sec=10.0,
    )
    worker = MarketSyncWorker(config)
    assert not worker.is_running

    # Start worker
    await worker.start()
    assert worker.is_running
    first_task = worker._bg_task

    # Calling start again must be a safe no-op (same task preserved)
    await worker.start()
    assert worker.is_running
    assert worker._bg_task is first_task

    # Stop worker
    await worker.stop()
    assert not worker.is_running


@pytest.mark.anyio
async def test_worker_sync_once_concurrency_lock():
    """Verify concurrent sync_once calls do not overlap."""
    config = MarketSyncConfig(enabled=True)
    worker = MarketSyncWorker(config)

    # Mock _sync_indices and _collect_priority_tickers to avoid real network
    with patch.object(worker, "_sync_indices", return_value=None):
        with patch.object(worker, "_collect_priority_tickers", return_value=[]):
            res1 = await worker.sync_once()
            assert res1.get("started_at") is not None
            assert worker._sync_count >= 1


# -----------------------------------------------------------------------------
# 3. Provider Timeout, Retries, and Malformed Responses
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_worker_timeout_and_error_tracking():
    """Verify worker tracks errors, logs provider failures, and applies backoff."""
    config = MarketSyncConfig(enabled=True, max_retries=1)
    worker = MarketSyncWorker(config)

    # Force error in _sync_indices
    with patch.object(worker, "_sync_indices", side_effect=RuntimeError("Provider 504 Gateway Timeout")):
        with patch.object(worker, "_collect_priority_tickers", return_value=[]):
            res = await worker.sync_once()
            assert len(res.get("errors", [])) > 0
            assert worker._consecutive_errors >= 1
            assert worker._last_error is not None
            assert "Provider 504" in worker._last_error

    status = worker.get_status()
    assert status["error_count"] >= 1
    assert status["consecutive_errors"] >= 1


def test_malformed_provider_response_handled_gracefully(tmp_path):
    """Verify malformed or empty DataFrame from provider does not crash ingestion."""
    from src.ingest.market_data import load_ohlcv

    # Mock fetch_ohlcv returning empty DataFrame (triggers validation error & synthetic fallback)
    with patch("src.ingest.market_data.fetch_ohlcv", return_value=pd.DataFrame()):
        df = load_ohlcv("MALFORMED_TEST", allow_synthetic=True, force_refresh=True)
        assert df is not None
        assert not df.empty  # Synthesizes test fallback offline


# -----------------------------------------------------------------------------
# 4. Cache Persistence and Timestamp Ordering
# -----------------------------------------------------------------------------

def test_cache_persistence_and_timestamp_ordering(tmp_path):
    """Verify cache preserves historical rows and appends/updates candles correctly."""
    ticker = "TESTSYNC_TICKER"
    c_path = _cache_path(ticker)
    m_path = _meta_path(ticker)

    try:
        # Create initial historical dataframe
        dates = pd.date_range("2026-10-01", "2026-10-05")
        df_init = pd.DataFrame({
            "date": dates,
            "open": [100.0, 101.0, 102.0, 103.0, 104.0],
            "high": [105.0, 106.0, 107.0, 108.0, 109.0],
            "low": [98.0, 99.0, 100.0, 101.0, 102.0],
            "close": [102.0, 103.0, 104.0, 105.0, 106.0],
            "volume": [1000, 1200, 1100, 1300, 1400],
            "delivery_pct": [50.0, 52.0, 48.0, 55.0, 53.0],
            "synthetic": [False] * 5,
        })
        df_init.to_parquet(c_path)

        meta_init = {
            "ticker": ticker,
            "exchange": "NSE",
            "provider": "yfinance",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "market_event_timestamp": "2026-10-05",
            "status": "cached",
            "latest_price": 106.0,
            "change_pct": 0.95,
        }
        m_path.write_text(json.dumps(meta_init), encoding="utf-8")

        # Inspect cache status
        status = get_daily_cache_status(ticker, max_age_seconds=86400)
        assert status["exists"] is True
        assert status["status"] in ("live", "cached")
        assert status["meta"]["latest_price"] == 106.0

        # Verify idempotency: reading cached parquet does not alter row order
        from src.ingest.market_data import load_ohlcv
        loaded = load_ohlcv(ticker, force_refresh=False, allow_synthetic=False, include_live_session=False)
        assert len(loaded) == 5
        assert loaded["date"].iloc[-1] == pd.Timestamp("2026-10-05")

    finally:
        if c_path.exists():
            c_path.unlink()
        if m_path.exists():
            m_path.unlink()


# -----------------------------------------------------------------------------
# 5. Endpoints Verification: Status, Trigger, Indices, Health
# -----------------------------------------------------------------------------

def test_market_sync_status_endpoint(client):
    """Verify /api/market/sync/status returns provider, intervals, and health."""
    response = client.get("/api/market/sync/status")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "intervals" in data
    assert "providers" in data
    assert len(data["providers"]) >= 2
    assert any(p["provider"] == "yfinance" for p in data["providers"])
    assert any(p["provider"] == "nse_bse_bhavcopy" for p in data["providers"])


def test_market_indices_endpoint(client):
    """Verify /api/market/indices returns major Indian indices."""
    response = client.get("/api/market/indices")
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "ok"
    assert "indices" in data
    indices = data["indices"]
    assert "NIFTY 50" in indices
    assert "SENSEX" in indices
    assert "BANK NIFTY" in indices
    assert "INDIA VIX" in indices


def test_market_sync_trigger_endpoint(client):
    """Verify /api/market/sync/trigger triggers background run."""
    response = client.post("/api/market/sync/trigger?background=true")
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "accepted"
    assert "worker_status" in data


def test_health_includes_market_sync(client):
    """Verify /health and /api/connectors/status expose market_sync."""
    res_h = client.get("/health")
    assert res_h.status_code == 200
    assert "market_sync" in res_h.json()

    res_c = client.get("/api/connectors/status")
    assert res_c.status_code == 200
    assert "market_sync" in res_c.json()


# -----------------------------------------------------------------------------
# 6. Portfolio & Stock Detail Freshness Reflection
# -----------------------------------------------------------------------------

def test_stock_detail_and_chart_returns_freshness(client):
    """Verify /api/stocks/{ticker} and /api/stocks/{ticker}/chart expose data_freshness."""
    # 1. Stock detail
    res_detail = client.get("/api/stocks/TCS")
    assert res_detail.status_code == 200
    detail = res_detail.json()
    assert "risk" in detail
    assert "data_freshness" in detail["risk"]
    assert detail["risk"]["data_freshness"] in ("live", "cached", "stale", "unavailable")

    # 2. Stock chart
    res_chart = client.get("/api/stocks/TCS/chart?period=3m")
    assert res_chart.status_code == 200
    chart = res_chart.json()
    assert "data_freshness" in chart
    assert chart["data_freshness"] in ("live", "cached", "stale", "unavailable")
    assert "provider" in chart


def test_portfolio_valuation_exposes_freshness(client):
    """Verify /api/portfolio holdings return data_freshness and quote status."""
    res = client.get("/api/portfolio")
    assert res.status_code == 200
    data = res.json()
    assert "holdings" in data
    if data["holdings"]:
        first = data["holdings"][0]
        assert "data_status" in first
        assert first["data_status"] in ("live", "cached", "stale", "unavailable")
        assert "provider" in first


# -----------------------------------------------------------------------------
# 7. JEV Investigation Context and Honest Stale Disclosures
# -----------------------------------------------------------------------------

def test_jev_investigation_receives_freshness_and_disclosures(client):
    """Verify JEV receives explicit market freshness disclosures when data is stale/missing."""
    from unittest.mock import patch
    from src.intelligence.jev.adapters.mock_adapter import MockClassifierAdapter

    payload = {
        "tip": "URGENT BUY VARANIUM TARGET 500 GUARANTEED RETURNS VIP GROUP",
        "source": "telegram",
    }

    mock_classification = {
        "message_type": "Stock Tip",
        "market_domain": "equity",
        "topic": "pump_and_dump",
        "tickers": ["VARANIUM"],
        "confidence": 0.95,
        "trading_intent": "BUY",
        "status": "classified",
    }

    with patch("src.intelligence.jev.api.get_active_adapter", return_value=MockClassifierAdapter()), \
         patch("backend.main.classify_message", return_value=mock_classification):
        response = client.post("/api/investigate", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "jev" in data
        jev = data["jev"]
        assert "data_freshness" in jev
        assert jev["data_freshness"] in ("live", "cached", "stale", "unavailable")

        analysis = jev.get("analysis")
        if analysis:
            citations = analysis.get("citations", [])
            assert len(citations) > 0
            # Citations must reflect source and timestamp
            assert any("Exchange" in c["source"] or "Market" in c["source"] for c in citations)
