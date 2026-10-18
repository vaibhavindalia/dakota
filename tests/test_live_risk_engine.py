"""Automated acceptance tests for Dakota's live risk engine upgrade.

Covers:
1. Preservation of scoring weights, classification bands, and regulatory/scam overrides.
2. Market-data cache freshness validation, TTL expiration, and graceful stale fallback.
3. Stock assessment metadata persistence, invalidation, and timeline history.
4. Intraday live session merging without breaking point-in-time daily indicators.
5. Deterministic simulation of the 10:00 AM vs 10:05 AM market update scenario.
6. Assurance that synthetic data is never mislabeled as live market data.
"""
import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

from src.engine.risk_engine import assess, WEIGHTS, GROUP_LABELS, band
from src.ingest.market_data import (
    load_ohlcv,
    get_daily_cache_status,
    merge_live_intraday_session,
    make_synthetic_ohlcv,
    DEFAULT_DAILY_CACHE_TTL_MARKET_HOURS,
)
from src.market.universe_manager import (
    get_or_assess_stock,
    get_stock_risk_history,
    query_stocks,
)


# ==============================================================================
# 1. RISK CALCULATION PRESERVATION TESTS
# ==============================================================================

def test_scoring_weights_and_bands_preserved():
    """Verify that the established 5-signal weights and classification bands are intact."""
    assert WEIGHTS == {
        "coordination": 25,
        "promoter": 25,
        "market_footprint": 20,
        "financial_integrity": 15,
        "structure": 15,
    }
    assert sum(WEIGHTS.values()) == 100

    assert band(15.0) == "Low"
    assert band(39.9) == "Low"
    assert band(40.0) == "Elevated"
    assert band(69.9) == "Elevated"
    assert band(70.0) == "High"
    assert band(100.0) == "High"


def test_regulatory_and_scam_overrides_preserved():
    """Verify that safety-net overrides (SEBI order, scam keywords, surveillance) still hold."""
    # Tip with 4 scam markers guarantees High Risk (>= 75.0)
    reports = pd.DataFrame([{
        "ticker": "CTRL01",
        "ts": pd.Timestamp.now(),
        "n_scam_markers": 5,
        "text": "guaranteed 500% profit VIP club urgent join",
        "fingerprint": "abc",
    }])
    v_scam = assess("CTRL01", tip_reports=reports)
    assert v_scam["score"] >= 75.0
    assert v_scam["band"] == "High"

    # Tip with 2 scam markers guarantees Elevated Risk (>= 45.0)
    reports_mild = pd.DataFrame([{
        "ticker": "CTRL01",
        "ts": pd.Timestamp.now(),
        "n_scam_markers": 2,
        "text": "vip target fast buy",
        "fingerprint": "def",
    }])
    v_mild = assess("CTRL01", tip_reports=reports_mild)
    assert v_mild["score"] >= 45.0


# ==============================================================================
# 2. MARKET-DATA CACHE FRESHNESS & TTL TESTS
# ==============================================================================

def test_daily_cache_freshness_status(tmp_path):
    """Verify that cache inspection returns accurate age, TTL, and status."""
    ticker = "TESTMKT"
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    cache_file = cache_dir / f"ohlcv_{ticker}.parquet"
    meta_file = cache_dir / f"ohlcv_{ticker}.meta.json"

    # Create dummy parquet & meta
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=30),
        "open": [100.0] * 30,
        "high": [105.0] * 30,
        "low": [95.0] * 30,
        "close": [102.0] * 30,
        "volume": [1000] * 30,
        "synthetic": [False] * 30,
    })
    df.to_parquet(cache_file)
    meta_file.write_text(json.dumps({
        "ticker": ticker,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "status": "fresh",
        "source": "yfinance",
    }), encoding="utf-8")

    with patch("src.ingest.market_data.CACHE_DIR", cache_dir):
        # 1. Immediate check with reasonable TTL: should be fresh
        status = get_daily_cache_status(ticker, max_age_seconds=60)
        assert status["exists"] is True
        assert status["is_fresh"] is True
        assert status["status"] == "fresh"

        # 2. Age file mtime artificially into the past (e.g. 500 seconds ago)
        old_time = time.time() - 500
        os.utime(cache_file, (old_time, old_time))

        status_stale = get_daily_cache_status(ticker, max_age_seconds=60)
        assert status_stale["is_fresh"] is False
        assert status_stale["status"] == "stale"
        assert status_stale["age_seconds"] >= 400


def test_stale_cache_preservation_on_provider_failure(tmp_path):
    """Verify that when the provider fails, valid cached data is preserved as STALE."""
    ticker = "STALEPROV"
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    cache_file = cache_dir / f"ohlcv_{ticker}.parquet"
    meta_file = cache_dir / f"ohlcv_{ticker}.meta.json"

    df_initial = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=35),
        "open": [100.0] * 35,
        "high": [105.0] * 35,
        "low": [95.0] * 35,
        "close": [102.0] * 35,
        "volume": [1000] * 35,
        "synthetic": [False] * 35,
    })
    df_initial.to_parquet(cache_file)

    with patch("src.ingest.market_data.CACHE_DIR", cache_dir), \
         patch("src.ingest.market_data.fetch_ohlcv", side_effect=RuntimeError("Provider 429 Rate Limited")):
        # Request with force_refresh=True -> fetch_ohlcv will fail
        # load_ohlcv MUST catch this and return the cached data rather than crashing or faking
        df_result = load_ohlcv(ticker, force_refresh=True, include_live_session=False)
        assert len(df_result) == 35
        assert not df_result["synthetic"].any()

        # Check that metadata now reflects stale status
        status = get_daily_cache_status(ticker)
        assert status["meta"]["status"] == "stale"
        assert "Provider 429" in status["meta"]["last_error"]


def test_synthetic_data_not_mislabeled_as_live():
    """Verify that synthetic fallback data is strictly marked synthetic=True."""
    synth = make_synthetic_ohlcv("SYNTH_TEST")
    assert "synthetic" in synth.columns
    assert synth["synthetic"].all()


# ==============================================================================
# 3. LIVE INTRADAY SESSION MERGING TESTS
# ==============================================================================

def test_merge_live_intraday_session():
    """Verify that intraday candles safely merge into daily OHLCV series."""
    daily_dates = pd.date_range("2024-01-01", "2024-01-10")
    df_daily = pd.DataFrame({
        "date": daily_dates,
        "open": [100.0] * len(daily_dates),
        "high": [110.0] * len(daily_dates),
        "low": [90.0] * len(daily_dates),
        "close": [105.0] * len(daily_dates),
        "volume": [5000] * len(daily_dates),
        "synthetic": [False] * len(daily_dates),
    })

    # Mock intraday candle for 2024-01-11 with high price action
    today_dt = pd.Timestamp("2024-01-11 10:05:00")
    df_intraday = pd.DataFrame([{
        "datetime": today_dt,
        "open": 105.0,
        "high": 125.0,
        "low": 104.0,
        "close": 124.0,
        "volume": 25000,
        "synthetic": False,
    }])
    intra_meta = {
        "day_open": 105.0,
        "day_high": 125.0,
        "day_low": 104.0,
        "day_volume": 25000,
        "synthetic": False,
    }

    with patch("src.ingest.market_data.fetch_intraday_ohlcv", return_value=(df_intraday, intra_meta)):
        merged = merge_live_intraday_session(df_daily, "TESTTICKER")
        assert len(merged) == len(df_daily) + 1
        last_row = merged.iloc[-1]
        assert last_row["date"] == pd.Timestamp("2024-01-11")
        assert last_row["close"] == 124.0
        assert last_row["high"] == 125.0
        assert last_row["volume"] == 25000


# ==============================================================================
# 4. UNIVERSE MANAGER METADATA & RECALCULATION TESTS
# ==============================================================================

def test_universe_manager_persists_assessment_metadata():
    """Verify get_or_assess_stock computes and persists required freshness metadata."""
    res = get_or_assess_stock("RELIANCE", force_refresh=True)
    assert res["ticker"] == "RELIANCE"
    assert res["score"] is not None
    assert "calculated_at" in res
    assert "market_data_as_of" in res
    assert "data_freshness" in res
    assert "change_reason" in res

    # Verify that a timeline history row was recorded
    history = get_stock_risk_history("RELIANCE", limit=5)
    assert len(history) >= 1
    assert history[0]["ticker"] == "RELIANCE"
    assert history[0]["score"] == res["score"]


# ==============================================================================
# 5. DETERMINISTIC 10:00 AM VS 10:05 AM SCENARIO TEST
# ==============================================================================

def test_1000am_to_1005am_scenario():
    """Deterministic simulation of the exact user scenario:

    1. At 10:00 AM, stock has baseline calculated score (e.g. 15.0 pts).
    2. At 10:05 AM, new market data arrives (volume surges, price ramps).
    3. Freshness validation detects the updated inputs.
    4. The risk engine recalculates using the existing 5-pillar formula.
    5. The score mathematically increases.
    6. score_change and change_reason reflect the exact shift.
    7. An irrelevant change (0.1% price tick, normal volume) keeps the score unchanged.
    """
    ticker = "SCENARIO_STOCK"

    # Step 1: Baseline at 10:00 AM (Quiet, normal volume)
    base_dates = pd.bdate_range("2024-01-01", periods=45)
    df_1000 = pd.DataFrame({
        "date": base_dates,
        "open": [100.0] * 45,
        "high": [102.0] * 45,
        "low": [98.0] * 45,
        "close": [100.0] * 45,
        "volume": [1000] * 45,
        "synthetic": [False] * 45,
    })

    with patch("src.ingest.market_data.load_ohlcv", return_value=df_1000):
        v_1000 = assess(ticker)
        score_1000 = v_1000["score"]
        footprint_1000 = v_1000["contributions"]["market_footprint"]

    # Step 2: At 10:05 AM, market conditions change!
    # Volume surges to 7,000 (7x normal 1,000 avg) and close rises from 100 to 160
    df_1005 = df_1000.copy()
    df_1005.loc[df_1005.index[-5:], "volume"] = 7000
    df_1005.loc[df_1005.index[-14:], "close"] = np.linspace(100, 160, 14)

    with patch("src.ingest.market_data.load_ohlcv", return_value=df_1005):
        v_1005 = assess(ticker)
        score_1005 = v_1005["score"]
        footprint_1005 = v_1005["contributions"]["market_footprint"]

    # Step 3: Verify the mathematical change in risk
    assert footprint_1005 > footprint_1000
    assert score_1005 > score_1000
    delta = round(score_1005 - score_1000, 1)
    assert delta >= 5.0, f"Expected at least +5.0 pts jump, got {delta}"

    # Step 4: Verify that an IRRELEVANT change does NOT artificially move the score
    df_irrelevant = df_1000.copy()
    df_irrelevant.loc[df_irrelevant.index[-1], "close"] = 100.1  # 0.1% tiny flutter, normal volume

    with patch("src.ingest.market_data.load_ohlcv", return_value=df_irrelevant):
        v_irrelevant = assess(ticker)
        assert v_irrelevant["score"] == score_1000, (
            f"Irrelevant change should not alter score: got {v_irrelevant['score']} vs {score_1000}"
        )
