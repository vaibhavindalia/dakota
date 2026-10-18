"""Unit tests for the 3-pillar unified Dakota investment decision engine."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from src.market.decision_engine import evaluate_investment_stance


def test_decision_shape():
    res = evaluate_investment_stance("RELIANCE")
    assert "stance" in res
    assert res["stance"] in {
        "FAVORABLE_SETUP",
        "SAFE_DOWNTREND",
        "CONSOLIDATING_WATCHLIST",
        "SURVEILLANCE_CAUTION",
        "CRITICAL_AVOID",
    }
    assert "pillars" in res
    assert set(res["pillars"].keys()) == {"forensic", "technical", "fundamental"}
    assert "checklist" in res
    assert len(res["checklist"]) == 5
    assert res["checklist_total_count"] == 5
    assert 0 <= res["checklist_passed_count"] <= 5


def test_fraud_case_triggers_critical_avoid():
    res = evaluate_investment_stance("CLOUD")
    assert res["stance"] == "CRITICAL_AVOID"
    assert res["pillars"]["forensic"]["status"] == "FAIL"
    assert res["theme"] == "red"


def test_clean_stock_forensic_pass():
    res = evaluate_investment_stance("RELIANCE")
    assert res["pillars"]["forensic"]["status"] == "PASS"
    assert res["pillars"]["forensic"]["score"] < 40.0
