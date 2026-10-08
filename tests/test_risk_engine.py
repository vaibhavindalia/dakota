"""Risk engine tests — the core acceptance test:

    cases score meaningfully higher than controls.

If this test fails, fix the engine/data — never loosen the test to pass.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import pytest

from src.engine.risk_engine import assess
from src.ingest.market_data import load_universe
from src.tipcheck.privacy import make_report_record


@pytest.fixture(scope="module")
def universe():
    return load_universe()


def test_score_shape(universe):
    v = assess(universe.ticker.iloc[0])
    assert 0 <= v["score"] <= 100
    assert set(v["contributions"]) == {
        "coordination", "promoter", "market_footprint", "financial_integrity", "structure"}
    assert v["band"] in {"Low", "Elevated", "High"}


def test_cases_outscore_controls(universe):
    cases = [assess(t)["score"] for t in universe[universe.role == "case"].ticker]
    ctrls = [assess(t)["score"] for t in universe[universe.role == "control"].ticker]
    assert pd.Series(cases).median() > pd.Series(ctrls).median() + 15, (
        f"median case {pd.Series(cases).median()} vs control {pd.Series(ctrls).median()}")


def test_sme_structure_points(universe):
    v = assess("CTRL01")  # SME control: structure points but nothing else
    assert v["contributions"]["structure"] > 0


def test_point_in_time_no_lookahead():
    # A score as of a date BEFORE the synthetic pump window must be lower.
    early = assess("VARANIUM", as_of="2023-02-01")
    late = assess("VARANIUM")
    assert late["score"] > early["score"]


def test_coordination_from_reports():
    now = pd.Timestamp.now()
    reports = pd.DataFrame(
        [make_report_record("CTRL02", now, "urgent ctrl02 guaranteed vip template")
         for _ in range(25)])
    reports["n_scam_markers"] = 3
    with_reports = assess("CTRL02", tip_reports=reports)
    without = assess("CTRL02")
    assert with_reports["contributions"]["coordination"] > without["contributions"]["coordination"]
