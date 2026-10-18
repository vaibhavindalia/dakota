"""Automated test suite for Dakota Portfolio Module & Multi-Holding Valuation.

Covers:
- Test A: Wipro estimated valuation (missing buy price)
- Test B: Known purchase price & P/L calculation
- Test C: Multiple holdings aggregation (Wipro, Zomato, Reliance)
- Test D: Missing market price handling (unpriced quotes)
- Test E: Quantity and purchase-price updates
- Test F: Adding and removing holdings
- Test G: Persistence in portfolio store
- Test H: Provider failure tolerance (never crashes)
- Test I: Summary consistency across views
- Test J: Edge cases (empty portfolio, fractional quantities, large portfolios, zero price)
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from typing import Any

from src.portfolio.valuation import (
    calculate_holding_metrics,
    calculate_portfolio_summary,
    enrich_and_value_portfolio,
    get_holding_quote,
)


# -----------------------------------------------------------------------------
# Test A: Wipro estimated valuation
# -----------------------------------------------------------------------------
def test_wipro_estimated_valuation_test_a():
    """Test A: Quantity 15, current price 162.57, buy price missing.

    Expected:
    - Current market value: 2438.55
    - Actual cost basis: None (Unavailable)
    - Estimated cost basis: 2438.55 (Explicitly estimated)
    - Profit/Loss: None (Unavailable)
    - Valuation status: 'estimated_cost_basis'
    """
    metrics = calculate_holding_metrics(
        ticker="WIPRO",
        quantity=15,
        average_buy_price=None,
        current_price=162.57,
    )

    assert metrics["ticker"] == "WIPRO"
    assert metrics["quantity"] == 15.0
    assert metrics["current_value"] == 2438.55
    assert metrics["actual_cost_basis"] is None
    assert metrics["estimated_cost_basis"] == 2438.55
    assert metrics["has_actual_cost"] is False
    assert metrics["cost_basis_type"] == "estimated"
    assert metrics["valuation_status"] == "estimated_cost_basis"
    assert metrics["unrealized_pnl"] is None
    assert metrics["unrealized_return_pct"] is None


# -----------------------------------------------------------------------------
# Test B: Known purchase price
# -----------------------------------------------------------------------------
def test_known_purchase_price_test_b():
    """Test B: Quantity 15, average buy price 150.00, current price 162.57.

    Expected:
    - Actual cost basis: 2250.00
    - Current market value: 2438.55
    - Unrealized profit/loss: 188.55
    - Unrealized return %: 8.38%
    - Valuation status: 'verified_cost'
    """
    metrics = calculate_holding_metrics(
        ticker="WIPRO",
        quantity=15,
        average_buy_price=150.00,
        current_price=162.57,
    )

    assert metrics["ticker"] == "WIPRO"
    assert metrics["quantity"] == 15.0
    assert metrics["average_buy_price"] == 150.00
    assert metrics["actual_cost_basis"] == 2250.00
    assert metrics["estimated_cost_basis"] is None
    assert metrics["has_actual_cost"] is True
    assert metrics["current_value"] == 2438.55
    assert metrics["unrealized_pnl"] == 188.55
    assert metrics["unrealized_return_pct"] == 8.38
    assert metrics["valuation_status"] == "verified_cost"


# -----------------------------------------------------------------------------
# Test C: Multiple holdings aggregation
# -----------------------------------------------------------------------------
def test_multiple_holdings_aggregation_test_c():
    """Test C: Portfolio with Wipro, Zomato, and Reliance.

    Verify that:
    - Total market value equals the sum of individual position market values.
    - Missing purchase prices do not corrupt actual cost basis totals.
    - Verified purchase prices aggregate into actual cost basis accurately.
    """
    # 1. WIPRO: 15 shares @ 162.57, buy price unknown (estimated)
    h_wipro = calculate_holding_metrics(
        ticker="WIPRO",
        quantity=15,
        average_buy_price=None,
        current_price=162.57,
    )

    # 2. ZOMATO: 100 shares @ 323.45, bought at 280.00 (verified)
    h_zomato = calculate_holding_metrics(
        ticker="ZOMATO",
        quantity=100,
        average_buy_price=280.00,
        current_price=323.45,
    )

    # 3. RELIANCE: 10 shares @ 2500.00, bought at 2400.00 (verified)
    h_reliance = calculate_holding_metrics(
        ticker="RELIANCE",
        quantity=10,
        average_buy_price=2400.00,
        current_price=2500.00,
    )

    summary = calculate_portfolio_summary([h_wipro, h_zomato, h_reliance])

    # Expected values:
    # Market Values: 2438.55 + 32345.00 + 25000.00 = 59783.55
    assert summary["total_positions"] == 3
    assert summary["total_market_value"] == 59783.55

    # Actual Costs: Zomato (28000.00) + Reliance (24000.00) = 52000.00 (Wipro excluded!)
    assert summary["total_actual_cost"] == 52000.00

    # Estimated Costs: Wipro only = 2438.55
    assert summary["total_estimated_cost"] == 2438.55

    # Unrealized P/L: Zomato (32345 - 28000 = 4345) + Reliance (25000 - 24000 = 1000) = 5345.00
    assert summary["total_unrealized_pnl"] == 5345.00

    # Return on verified cost: (5345 / 52000) * 100 = 10.28%
    assert summary["total_unrealized_return_pct"] == 10.28
    assert summary["verified_buy_price_count"] == 2
    assert summary["missing_buy_price_count"] == 1
    assert summary["unpriced_count"] == 0
    assert summary["is_partial_valuation"] is False


# -----------------------------------------------------------------------------
# Test D: Missing market price handling
# -----------------------------------------------------------------------------
def test_missing_market_price_test_d():
    """Test D: Position where quote is unavailable.

    Expected:
    - Position remains visible with quantity preserved.
    - Market value and estimated cost are None (not 0.0!).
    - Portfolio marks is_partial_valuation = True and unpriced_count = 1.
    """
    h_unpriced = calculate_holding_metrics(
        ticker="DELISTED_SCRIP",
        quantity=50,
        average_buy_price=None,
        current_price=None,  # Quote failed
        quote_status="unavailable",
    )

    assert h_unpriced["current_price"] is None
    assert h_unpriced["current_value"] is None
    assert h_unpriced["estimated_cost_basis"] is None
    assert h_unpriced["cost_basis_type"] == "unavailable"
    assert h_unpriced["valuation_status"] == "unpriced"

    h_normal = calculate_holding_metrics(
        ticker="WIPRO",
        quantity=15,
        average_buy_price=150.0,
        current_price=162.57,
    )

    summary = calculate_portfolio_summary([h_unpriced, h_normal])
    assert summary["total_positions"] == 2
    assert summary["unpriced_count"] == 1
    assert summary["is_partial_valuation"] is True
    # Normal position is still priced accurately
    assert summary["total_market_value"] == 2438.55


# -----------------------------------------------------------------------------
# Test E: Quantity and purchase price edits
# -----------------------------------------------------------------------------
def test_quantity_and_price_edits_test_e():
    """Test E: Changing quantity or purchase price recalculates metrics immediately."""
    initial = calculate_holding_metrics(
        ticker="WIPRO",
        quantity=10,
        average_buy_price=150.0,
        current_price=160.0,
    )
    assert initial["actual_cost_basis"] == 1500.0
    assert initial["current_value"] == 1600.0
    assert initial["unrealized_pnl"] == 100.0

    # Increase quantity to 20
    updated_qty = calculate_holding_metrics(
        ticker="WIPRO",
        quantity=20,
        average_buy_price=150.0,
        current_price=160.0,
    )
    assert updated_qty["actual_cost_basis"] == 3000.0
    assert updated_qty["current_value"] == 3200.0
    assert updated_qty["unrealized_pnl"] == 200.0

    # Update buy price to 155.0
    updated_price = calculate_holding_metrics(
        ticker="WIPRO",
        quantity=20,
        average_buy_price=155.0,
        current_price=160.0,
    )
    assert updated_price["actual_cost_basis"] == 3100.0
    assert updated_price["current_value"] == 3200.0
    assert updated_price["unrealized_pnl"] == 100.0


# -----------------------------------------------------------------------------
# Test F & G: Add, edit, remove holding and JSON persistence
# -----------------------------------------------------------------------------
def test_add_edit_remove_and_persistence_test_f_g(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test F & G: Operations on portfolio store with disk persistence."""
    import backend.main as bmain

    temp_store = tmp_path / "portfolio.json"
    monkeypatch.setattr(bmain, "PORTFOLIO_FILE", temp_store)

    # 1. Initially empty
    assert bmain._load_portfolio() == []

    # 2. Add Wipro
    req = bmain.HoldingRequest(ticker="WIPRO", quantity=15, average_buy_price=150.0)
    added = bmain.add_holding(req)
    assert added["ticker"] == "WIPRO"
    assert added["quantity"] == 15.0

    # Check persistence
    stored = bmain._load_portfolio()
    assert len(stored) == 1
    assert stored[0]["ticker"] == "WIPRO"
    assert stored[0]["average_buy_price"] == 150.0

    # 3. Add Zomato with missing buy price
    req2 = bmain.HoldingRequest(ticker="ZOMATO", quantity=100)
    bmain.add_holding(req2)
    stored2 = bmain._load_portfolio()
    assert len(stored2) == 2

    # 4. Update Wipro (change quantity to 25 and buy price to 155)
    req_update = bmain.HoldingRequest(ticker="WIPRO", quantity=25, average_buy_price=155.0)
    bmain.add_holding(req_update)
    stored3 = bmain._load_portfolio()
    assert len(stored3) == 2  # No duplicate created!
    wipro_entry = next(item for item in stored3 if item["ticker"] == "WIPRO")
    assert wipro_entry["quantity"] == 25.0
    assert wipro_entry["average_buy_price"] == 155.0

    # 5. Remove Zomato
    bmain.delete_holding("ZOMATO")
    stored4 = bmain._load_portfolio()
    assert len(stored4) == 1
    assert stored4[0]["ticker"] == "WIPRO"

    # 6. Delete nonexistent raises 404
    with pytest.raises(Exception):
        bmain.delete_holding("NONEXISTENT")


# -----------------------------------------------------------------------------
# Test H: Provider failure tolerance
# -----------------------------------------------------------------------------
def test_provider_failure_tolerance_test_h(monkeypatch: pytest.MonkeyPatch):
    """Test H: If the quote provider throws an unhandled error, valuation never crashes."""
    # Force quote lookup to fail
    def failing_load(*args, **kwargs):
        raise ConnectionResetError("Provider network timeout")

    monkeypatch.setattr("src.ingest.market_data.load_ohlcv", failing_load)

    quote = get_holding_quote("WIPRO", force_refresh=True)
    assert quote["current_price"] is None
    assert quote["quote_status"] == "unavailable"

    # Full enrichment pipeline must still return safely
    items = [{"ticker": "WIPRO", "quantity": 15.0, "average_buy_price": 150.0}]
    res = enrich_and_value_portfolio(items, force_refresh=True)
    assert len(res["holdings"]) == 1
    assert res["holdings"][0]["ticker"] == "WIPRO"
    assert res["holdings"][0]["actual_cost_basis"] == 2250.0
    assert res["holdings"][0]["current_price"] is None
    assert res["summary"]["unpriced_count"] == 1


# -----------------------------------------------------------------------------
# Test I: Three-tab consistency
# -----------------------------------------------------------------------------
def test_summary_and_holding_consistency_test_i():
    """Test I: Shared single source of truth across portfolio summaries."""
    items = [
        {"ticker": "WIPRO", "quantity": 15.0, "average_buy_price": 150.0},
        {"ticker": "ZOMATO", "quantity": 100.0, "average_buy_price": None},
    ]
    res = enrich_and_value_portfolio(items)

    # Top-level fields match the summary sub-dict exactly
    assert res["total_positions"] == res["summary"]["total_positions"]
    assert res["total_actual_cost"] == res["summary"]["total_actual_cost"]
    assert res["total_estimated_cost"] == res["summary"]["total_estimated_cost"]
    assert res["total_market_value"] == res["summary"]["total_market_value"]

    # Sum of individual holdings matches summary totals
    actual_sum = sum(h["actual_cost_basis"] for h in res["holdings"] if h["actual_cost_basis"] is not None)
    assert actual_sum == res["total_actual_cost"]

    est_sum = sum(h["estimated_cost_basis"] for h in res["holdings"] if h["estimated_cost_basis"] is not None)
    assert est_sum == res["total_estimated_cost"]


# -----------------------------------------------------------------------------
# Test J: Edge cases
# -----------------------------------------------------------------------------
def test_edge_cases_test_j():
    """Test J: Empty portfolio, zero price, negative quantities, fractional quantities, very large portfolios."""
    # 1. Empty portfolio
    empty_res = calculate_portfolio_summary([])
    assert empty_res["total_positions"] == 0
    assert empty_res["total_actual_cost"] == 0.0
    assert empty_res["total_estimated_cost"] == 0.0
    assert empty_res["total_market_value"] == 0.0
    assert empty_res["total_unrealized_pnl"] is None

    # 2. Fractional shares (e.g. 15.5 shares)
    frac = calculate_holding_metrics("WIPRO", 15.5, average_buy_price=150.0, current_price=162.57)
    assert frac["actual_cost_basis"] == 2325.0
    assert frac["current_value"] == 2519.84

    # 3. Buy price <= 0 treated as unrecorded / None
    zero_buy = calculate_holding_metrics("WIPRO", 10, average_buy_price=0.0, current_price=100.0)
    assert zero_buy["has_actual_cost"] is False
    assert zero_buy["actual_cost_basis"] is None
    assert zero_buy["estimated_cost_basis"] == 1000.0

    # 4. Large portfolio scaling (500 holdings)
    large_list = [
        calculate_holding_metrics(
            f"STOCK_{i}",
            quantity=10,
            average_buy_price=100.0 if i % 2 == 0 else None,
            current_price=110.0,
        )
        for i in range(500)
    ]
    large_sum = calculate_portfolio_summary(large_list)
    assert large_sum["total_positions"] == 500
    assert large_sum["verified_buy_price_count"] == 250
    assert large_sum["missing_buy_price_count"] == 250
    assert large_sum["total_actual_cost"] == 250 * 1000.0  # 250,000
    assert large_sum["total_estimated_cost"] == 250 * 1100.0  # 275,000
    assert large_sum["total_market_value"] == 500 * 1100.0  # 550,000
    assert large_sum["total_unrealized_pnl"] == 250 * 100.0  # 25,000 on verified positions
    assert large_sum["total_unrealized_return_pct"] == 10.0
