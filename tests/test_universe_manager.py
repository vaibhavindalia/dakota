import pytest
from src.market.universe_manager import query_stocks, get_or_assess_stock


def test_query_stocks_pagination():
    res = query_stocks(limit=10, page=1)
    assert "stocks" in res
    assert "total" in res
    assert res["total"] >= 2600
    assert len(res["stocks"]) == 10
    assert res["page"] == 1


def test_query_stocks_search():
    res = query_stocks(search="TATA", limit=10)
    assert res["total"] > 0
    symbols = [s["ticker"] for s in res["stocks"]]
    names = [s["name"].upper() for s in res["stocks"]]
    # At least one must contain TATA in ticker or name
    assert any("TATA" in sym or "TATA" in n for sym, n in zip(symbols, names))


def test_query_stocks_filter_segment():
    res = query_stocks(segment="surveillance", limit=20)
    assert res["total"] > 0
    for s in res["stocks"]:
        assert s["is_surveillance"] == 1


def test_get_or_assess_stock():
    # RELIANCE is already in the database
    stock = get_or_assess_stock("RELIANCE")
    assert stock["ticker"] == "RELIANCE"
    assert "score" in stock
