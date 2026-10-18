import pandas as pd
import pytest
from src.market.technical_analyzer import compute_supertrend, analyze_technicals
from backend.main import stock_chart


def test_compute_supertrend():
    # Synthetic trending data
    n = 30
    df = pd.DataFrame({
        "open": [100 + i for i in range(n)],
        "high": [102 + i for i in range(n)],
        "low": [99 + i for i in range(n)],
        "close": [101 + i for i in range(n)],
        "volume": [1000] * n,
        "date": [f"2026-01-{i+1:02d}" for i in range(n)],
    })
    st, direction = compute_supertrend(df, length=10, mult=3.0)
    assert len(st) == n
    assert len(direction) == n
    # During steady uptrend, direction should be 1 (bullish)
    assert direction[-1] == 1
    assert st[-1] is not None
    assert st[-1] < df["close"].iloc[-1]


def test_analyze_technicals_includes_supertrend():
    n = 40
    df = pd.DataFrame({
        "open": [100 + i for i in range(n)],
        "high": [105 + i for i in range(n)],
        "low": [95 + i for i in range(n)],
        "close": [102 + i for i in range(n)],
        "volume": [10000] * n,
        "date": [f"2026-01-{i+1:02d}" for i in range(n)],
    })
    res = analyze_technicals(df, "TESTCO")
    assert res["status"] == "ok"
    names = [ind["name"] for ind in res["moving_averages"]["indicators"]]
    assert "Supertrend (10, 3)" in names
    osc_names = [ind["name"] for ind in res["oscillators"]["indicators"]]
    assert "Bollinger Bands" in osc_names


def test_stock_chart_overlays():
    res = stock_chart("TATAPOWER", period="1m")
    assert res["ticker"] == "TATAPOWER"
    assert "overlays_latest" in res
    assert "points" in res
    if res["points"]:
        last = res["points"][-1]
        assert "ema_20" in last
        assert "sma_50" in last
        assert "sma_200" in last
        assert "bb_upper" in last
        assert "bb_mid" in last
        assert "bb_lower" in last
        assert "supertrend" in last
        assert "supertrend_dir" in last
        assert "volume" in last
        assert "is_up" in last
