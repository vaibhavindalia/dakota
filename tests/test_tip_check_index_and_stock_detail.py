"""Regression tests for Tip Authenticity index query support and stock_detail endpoint."""
import pytest
from src.tipcheck.parser import check_tip, parse_tip
from src.market.universe_manager import get_or_assess_stock
from backend.main import stock_detail


def test_tip_check_nifty_index_detection():
    """Verify entering 'NIFTY' triggers benchmark index detection and informative guidance."""
    res = check_tip("NIFTY")
    parsed = res.get("parsed")
    assert getattr(parsed, "is_index", False) is True
    assert "NIFTY" in getattr(parsed, "index_name", "")
    assert "Market Benchmark Index Detected" in res.get("headline", "")
    assert len(res.get("next_steps", [])) > 0
    assert any("benchmark index" in step.lower() for step in res.get("next_steps", []))


def test_tip_check_banknifty_index_detection():
    """Verify entering 'BANK NIFTY' detects index call properly."""
    res = check_tip("BANK NIFTY BUY CALL 54000")
    parsed = res.get("parsed")
    assert getattr(parsed, "is_index", False) is True
    assert "BANK NIFTY" in getattr(parsed, "index_name", "")


def test_tip_check_single_stock_verdict():
    """Verify single stock tip returns valid stock verdicts."""
    res = check_tip("BUY HDFCBANK TARGET 1800")
    assert len(res.get("stock_verdicts", [])) > 0
    assert res["stock_verdicts"][0]["ticker"] == "HDFCBANK"


def test_universe_manager_get_or_assess_stock_with_force_refresh():
    """Verify get_or_assess_stock accepts force_refresh and max_age_seconds without TypeError."""
    res = get_or_assess_stock("HDFCBANK", force_refresh=False, max_age_seconds=3600)
    assert res.get("ticker") == "HDFCBANK"
    assert res.get("status") in ("completed", "pending")


def test_stock_detail_endpoint_success():
    """Verify stock_detail endpoint returns full risk, meta, and decision payload for HDFCBANK."""
    data = stock_detail("HDFCBANK", force_refresh=False)
    assert data["ticker"] == "HDFCBANK"
    assert "risk" in data
    assert "meta" in data
    assert data["risk"].get("score") is not None
    assert data["risk"].get("band") is not None
