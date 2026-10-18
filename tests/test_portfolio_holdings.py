"""Unit and regression tests for portfolio holding price calculation and storage."""
import pytest
from backend.main import HoldingRequest, _holding_value, add_holding, portfolio, _save_portfolio, _load_portfolio


def test_holding_request_accepts_average_buy_price():
    """Verify HoldingRequest schema accepts average_buy_price sent by frontend."""
    req = HoldingRequest(
        exchange="NSE",
        ticker="INFY",
        quantity=50.0,
        average_buy_price=1650.75,
    )
    assert req.average_buy_price == 1650.75
    assert req.quantity == 50.0


def test_holding_value_calculation():
    """Verify holding value computation calculates accurately across different key aliases."""
    item1 = {"quantity": 100, "average_buy_price": 250.0}
    assert _holding_value(item1) == 25000.0

    item2 = {"quantity": 10, "avg_buy_price": 500.0}
    assert _holding_value(item2) == 5000.0

    item3 = {"quantity": 5, "averagePrice": 120.0}
    assert _holding_value(item3) == 600.0

    item_empty = {"quantity": 50}
    assert _holding_value(item_empty) == 0.0


def test_add_and_retrieve_portfolio_holding(tmp_path, monkeypatch):
    """Verify holding addition preserves buy price and total invested calculation."""
    test_file = tmp_path / "portfolio.json"
    monkeypatch.setattr("backend.main.PORTFOLIO_FILE", test_file)

    req = HoldingRequest(
        exchange="NSE",
        ticker="TATAMOTORS",
        quantity=20.0,
        average_buy_price=950.0,
    )
    saved = add_holding(req)
    assert saved["average_buy_price"] == 950.0
    assert saved["avg_buy_price"] == 950.0

    result = portfolio()
    assert result["count"] == 1
    assert result["total_invested"] == 19000.0
    holding = result["holdings"][0]
    assert holding["ticker"] == "TATAMOTORS"
    assert holding["average_buy_price"] == 950.0
    assert holding["invested_value"] == 19000.0
