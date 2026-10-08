"""Tip parser tests — run with: pytest tests/ -v"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.tipcheck.parser import parse_tip
from src.tipcheck import privacy


SAMPLE = ("URGENT!! VARANIUM target Rs 500 by Friday. Guaranteed returns, 100% sure. "
          "Join my VIP telegram channel, only 10 slots left. Call 98765 43210.")


def test_extracts_ticker_and_target():
    tip = parse_tip(SAMPLE)
    assert "VARANIUM" in tip.tickers
    assert tip.price_target == 500.0


def test_scam_markers_detected():
    tip = parse_tip(SAMPLE)
    assert "guaranteed_returns" in tip.markers_found
    assert "vip_funnel" in tip.markers_found
    assert tip.urgency
    assert tip.n_scam_markers >= 3


def test_clean_tip_has_no_markers():
    tip = parse_tip("Any fundamental view on CTRL01 for long term holding?")
    assert tip.n_scam_markers == 0
    assert not tip.urgency


def test_pii_scrubbed_before_parse():
    tip = parse_tip(SAMPLE)
    assert "98765" not in tip.clean_text
    assert "[phone]" in tip.clean_text


def test_sebi_number_not_auto_verified():
    tip = parse_tip("SEBI registered advisor INA000012345 recommends VARANIUM.")
    assert tip.sebi_reg_claimed
    assert tip.sebi_reg_number == "INA000012345"
    assert tip.sebi_reg_verified is None  # never claim verified without checking


def test_fingerprint_stable_and_template_based():
    t1 = privacy.fingerprint("VARANIUM target 500, guaranteed returns!!")
    t2 = privacy.fingerprint("varanium target 900 guaranteed returns")
    t3 = privacy.fingerprint("completely different message about fundamentals")
    assert t1 == t2          # same template, different numbers -> same fingerprint
    assert t1 != t3
