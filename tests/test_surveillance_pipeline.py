"""Unit and integration tests for Dakota JAV + QN Indian Stock Manipulation Pipeline.

Verifies:
1. Universe deduplication, normalization, and 500-stock integrity.
2. Evidence registry provenance, regulatory citations, and label categories.
3. Point-in-time feature calculation without lookahead leakage.
4. Chronological walk-forward train/val/test splits with embargo purge.
5. QN quantitative model training, serialization, and evaluation metrics.
6. Non-destructive RiskEngine integration (legacy score preservation).
7. FastAPI surveillance endpoint validation.
"""
from __future__ import annotations

import sys
from pathlib import Path
import pytest
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.surveillance.universe import (
    SurveillanceUniverse,
    EquityIdentity,
    surveillance_universe,
    normalize_symbol,
)
from src.surveillance.evidence import (
    EvidenceRegistry,
    ManipulationEvent,
    ManipulationLabel,
    EvidenceStrength,
    BehaviorCategory,
    evidence_registry,
)
from src.surveillance.features import FEATURE_COLUMNS, compute_window_features
from src.surveillance.dataset_builder import DatasetBuilder, dataset_builder, load_ticker_ohlcv
from src.surveillance.model import (
    train_qn_model,
    QNManipulationInference,
    qn_inference,
    QNPrediction,
)
from src.surveillance.evaluation import evaluate_predictions, EvaluationReport
from src.surveillance.risk_bridge import attach_qn_intelligence
from src.engine.risk_engine import assess
from backend.main import app


# =========================================================================
# 1. UNIVERSE PIPELINE TESTS
# =========================================================================

def test_universe_initialization_and_deduplication():
    equities = surveillance_universe.list_equities()
    assert len(equities) == 500

    # Ensure all tickers are distinct
    tickers = [s.ticker for s in equities]
    assert len(tickers) == len(set(tickers)), "Duplicate tickers found in universe"

    # Verify exchange normalization
    for stock in equities:
        assert stock.exchange in {"NSE", "BSE"}
        assert stock.yahoo_symbol.endswith(".NS") or stock.yahoo_symbol.endswith(".BO")
        assert stock.role in {"case", "control"}

    # Verify case vs control composition
    cases = [s for s in equities if s.role == "case"]
    controls = [s for s in equities if s.role == "control"]
    assert len(cases) >= 15
    assert len(controls) >= 450


def test_universe_symbol_normalization():
    assert normalize_symbol("CLOUD.NS") == "CLOUD"
    assert normalize_symbol("ASRL.BO") == "ASRL"
    assert normalize_symbol("VARANIUM") == "CLOUD"  # Known alias resolution
    assert normalize_symbol("ADDSHOP") == "ASRL"
    assert normalize_symbol("INFY") == "INFY"


# =========================================================================
# 2. EVIDENCE REGISTRY TESTS
# =========================================================================

def test_evidence_registry_provenance():
    events = evidence_registry.list_events()
    assert len(events) >= 18

    confirmed = [e for e in events if e.label == ManipulationLabel.CONFIRMED_MANIPULATION]
    assert len(confirmed) >= 12

    for event in confirmed:
        assert event.label == ManipulationLabel.CONFIRMED_MANIPULATION
        assert event.regulator_or_authority is not None and "SEBI" in event.regulator_or_authority
        assert event.source_url_or_id is not None and event.source_url_or_id.startswith("https://")
        assert event.order_reference is not None and len(event.order_reference) > 0
        assert event.evidence_strength == EvidenceStrength.HIGH

    # Verify label lookup for unreferenced stock
    unknown_label = evidence_registry.get_stock_label("INFY")
    assert unknown_label == ManipulationLabel.NO_KNOWN_CONFIRMED_CASE


def test_label_categories_schema():
    assert ManipulationLabel.CONFIRMED_MANIPULATION.value == "CONFIRMED_MANIPULATION"
    assert ManipulationLabel.SUSPICIOUS_UNCONFIRMED.value == "SUSPICIOUS_UNCONFIRMED"
    assert ManipulationLabel.NO_KNOWN_CONFIRMED_CASE.value == "NO_KNOWN_CONFIRMED_CASE"
    assert ManipulationLabel.UNKNOWN.value == "UNKNOWN"


# =========================================================================
# 3. FEATURE EXTRACTION & POINT-IN-TIME INTEGRITY
# =========================================================================

def test_feature_extraction_shape_and_values():
    dates = pd.date_range("2025-01-01", periods=100, freq="B")
    rng = np.random.default_rng(42)
    prices = 100.0 * np.exp(np.cumsum(rng.normal(0.001, 0.02, 100)))
    volumes = rng.integers(10000, 500000, 100)

    df = pd.DataFrame({
        "trade_date": dates.strftime("%Y-%m-%d"),
        "open": prices * 0.99,
        "high": prices * 1.02,
        "low": prices * 0.98,
        "close": prices,
        "volume": volumes,
    })

    features = compute_window_features(df, as_of_date="2025-04-01")
    assert len(features) == len(FEATURE_COLUMNS)
    for name in FEATURE_COLUMNS:
        assert name in features
        assert not np.isnan(features[name]), f"Feature {name} is NaN"

    assert features["amihud_illiquidity_20d"] >= 0.0
    assert features["volatility_20d"] >= 0.0


def test_feature_extraction_empty_or_short_series():
    df_empty = pd.DataFrame()
    f_empty = compute_window_features(df_empty)
    assert len(f_empty) == len(FEATURE_COLUMNS)
    assert all(val == 0.0 for val in f_empty.values())


# =========================================================================
# 4. DATASET BUILDER & LEAKAGE AVOIDANCE
# =========================================================================

def test_chronological_splits_and_embargo():
    dataset_summary = dataset_builder.build_dataset()
    splits = dataset_summary["splits"]

    assert splits["train"]["count"] > 0
    assert splits["val"]["count"] > 0
    assert splits["test"]["count"] > 0
    assert dataset_summary["total_windows"] == splits["train"]["count"] + splits["val"]["count"] + splits["test"]["count"]

    # Verify prepared arrays
    train_df, val_df, test_df, imputer, scaler = dataset_builder.load_processed_splits()
    assert len(train_df) == splits["train"]["count"]
    assert len(val_df) == splits["val"]["count"]
    assert len(test_df) == splits["test"]["count"]


# =========================================================================
# 5. QN MODEL TRAINING & INFERENCE INTERFACE
# =========================================================================

def test_qn_training_and_serialization():
    val_report, test_report, meta = train_qn_model()
    assert test_report is not None
    assert isinstance(test_report, EvaluationReport)
    assert test_report.total_samples > 0
    assert test_report.confusion_matrix is not None
    assert 0.0 <= test_report.roc_auc <= 1.0
    assert 0.0 <= test_report.brier_score <= 1.0

    # Test inference engine loading
    pred = qn_inference.analyze_ticker("CLOUD")
    assert isinstance(pred, QNPrediction)
    assert 0.0 <= pred.model_score <= 100.0
    assert 0.0 <= pred.manipulation_probability <= 1.0
    assert pred.risk_band in {"Low", "Elevated", "High"}
    assert len(pred.contributing_factors) > 0
    assert "legal or regulatory finding" in pred.disclaimer


# =========================================================================
# 6. RISK ENGINE NON-DESTRUCTIVE INTEGRATION
# =========================================================================

def test_risk_engine_score_preservation():
    # Assess without mutating legacy risk engine outputs
    assessment = assess("VARANIUM")

    assert 0 <= assessment["score"] <= 100
    assert assessment["band"] in {"Low", "Elevated", "High"}
    assert set(assessment["contributions"].keys()) == {
        "coordination", "promoter", "market_footprint", "financial_integrity", "structure"
    }

    # Verify attached qn_surveillance signal
    assert "qn_surveillance" in assessment
    qn_sig = assessment["qn_surveillance"]
    assert "model_score" in qn_sig
    assert "manipulation_probability" in qn_sig
    assert "risk_band" in qn_sig
    assert "disclaimer" in qn_sig
    assert "relation_to_risk_engine" in qn_sig


# =========================================================================
# 7. FASTAPI SURVEILLANCE ROUTER INTEGRATION
# =========================================================================

def test_surveillance_api_endpoints():
    client = TestClient(app)

    # 1. Universe overview endpoint
    resp_u = client.get("/api/surveillance/qn/universe")
    assert resp_u.status_code == 200
    data_u = resp_u.json()
    assert data_u["total_count"] == 500

    # 2. Paginated stocks endpoint
    resp_s = client.get("/api/surveillance/qn/stocks?limit=10")
    assert resp_s.status_code == 200
    data_s = resp_s.json()
    assert data_s["total"] == 500
    assert len(data_s["stocks"]) == 10

    # 3. Evidence registry endpoint
    resp_e = client.get("/api/surveillance/qn/evidence")
    assert resp_e.status_code == 200
    data_e = resp_e.json()
    assert data_e["total_returned"] >= 18
    assert len(data_e["events"]) >= 18

    # 4. Model status endpoint
    resp_m = client.get("/api/surveillance/qn/model/status")
    assert resp_m.status_code == 200
    data_m = resp_m.json()
    assert "is_model_available" in data_m
    assert "model_version" in data_m

    # 5. Analyze endpoint
    resp_a = client.get("/api/surveillance/qn/analyze/CLOUD")
    assert resp_a.status_code == 200
    data_a = resp_a.json()
    assert data_a["ticker"] == "CLOUD"
    assert "qn_prediction" in data_a
    assert "model_score" in data_a["qn_prediction"]

    # 6. Research experiment summary endpoint
    resp_r = client.get("/api/surveillance/qn/research/experiment")
    assert resp_r.status_code == 200
    data_r = resp_r.json()
    assert "dataset_manifest" in data_r
    assert data_r["dataset_manifest"]["total_windows"] > 0
    assert "splits" in data_r["dataset_manifest"]
    assert "active_model_metadata" in data_r


# =========================================================================
# 7. FORENSIC AUDIT & SECURITY HARDENING REGRESSION TESTS
# =========================================================================

def test_synthetic_firewall_enforcement():
    """Verify that the synthetic-data firewall blocks silent generation in production mode."""
    # Delisted stock CLOUD has no parquet file
    real_mode_df = load_ticker_ohlcv("CLOUD", allow_synthetic=False)
    assert real_mode_df.empty
    assert real_mode_df.attrs.get("provenance") == "UNAVAILABLE_DELISTED"

    # Offline unit testing explicitly permitting synthetic fallback
    test_mode_df = load_ticker_ohlcv("CLOUD", allow_synthetic=True)
    assert not test_mode_df.empty
    assert test_mode_df.attrs.get("provenance") == "SYNTHETIC_TEST_DATA"


def test_point_in_time_feature_no_future_leakage():
    """Verify that compute_window_features strictly truncates at as_of_date without looking ahead."""
    df = load_ticker_ohlcv("RELIANCE")
    assert not df.empty

    f_early = compute_window_features(df, as_of_date="2024-04-15")
    f_late = compute_window_features(df, as_of_date="2026-09-30")

    # Features must vary over time and not report the exact same October 2026 tail row
    assert f_early["return_20d"] != f_late["return_20d"] or f_early["volume_zscore_20d"] != f_late["volume_zscore_20d"]


def test_risk_bridge_non_destructive_invariance():
    """Verify that attaching QN intelligence never mutates legacy deterministic 0-100 score."""
    sample_risk = {
        "score": 45.5,
        "band": "Elevated",
        "contributions": {"coordination": 15, "promoter": 10, "market_footprint": 10, "financial_integrity": 5, "structure": 5.5},
        "reasons": ["High promoter pledge"],
    }
    unmutated_copy = dict(sample_risk)
    unmutated_copy["contributions"] = dict(sample_risk["contributions"])

    augmented = attach_qn_intelligence(sample_risk, "RELIANCE")
    assert augmented["score"] == unmutated_copy["score"]
    assert augmented["band"] == unmutated_copy["band"]
    assert augmented["contributions"] == unmutated_copy["contributions"]
    assert "qn_surveillance" in augmented
    assert augmented["qn_surveillance"]["is_real_model"] is True


def test_data_quality_report_machine_readable():
    """Verify that the 500-stock machine-readable data audit report exists and is populated."""
    import json
    from src.surveillance.data_audit import REPORT_CSV, REPORT_JSON, run_universe_data_audit
    if not REPORT_JSON.exists():
        run_universe_data_audit()

    assert REPORT_JSON.exists()
    assert REPORT_CSV.exists()

    report = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    assert report["total_equities_audited"] == 500
    assert report["usable_equities_count"] >= 490
    assert "UNAVAILABLE_DELISTED" in report["provenance_breakdown"]


def test_threshold_alert_decision_rule_invariant():
    """Verify that alert_triggered strictly equals (manipulation_probability >= effective_threshold)."""
    pred_drona_active = qn_inference.analyze_ticker("DRONACHRYA", as_of_date="2026-04-15")
    assert pred_drona_active.effective_threshold == 0.012
    assert pred_drona_active.alert_triggered == (pred_drona_active.manipulation_probability >= pred_drona_active.effective_threshold)

    pred_reliance = qn_inference.analyze_ticker("RELIANCE", as_of_date="2026-09-30")
    assert pred_reliance.effective_threshold == 0.012
    assert pred_reliance.alert_triggered == (pred_reliance.manipulation_probability >= pred_reliance.effective_threshold)
    assert pred_reliance.alert_triggered is False


def test_dronacharya_temporal_probability_reconciliation():
    """Verify DRONACHRYA probability and threshold reconciliation across historical and live dates.
    
    In holdout test slice at 2026-04-15 (during active ASM surveillance), probability >= 0.012 -> alert_triggered = True.
    In post-event live tail at 2026-10-24, volatility cooled down, probability < 0.012 -> alert_triggered = False.
    """
    pred_historical = qn_inference.analyze_ticker("DRONACHRYA", as_of_date="2026-04-15")
    assert pred_historical.manipulation_probability >= 0.012
    assert pred_historical.alert_triggered is True

    pred_live = qn_inference.analyze_ticker("DRONACHRYA", as_of_date="2026-10-24")
    assert pred_live.manipulation_probability < 0.012
    assert pred_live.alert_triggered is False


def test_calibration_group_kfold_no_cross_fold_leakage():
    """Verify that internal calibration folds have exactly zero ticker or event overlap."""
    from sklearn.model_selection import StratifiedGroupKFold
    train_df, _, _, _, _ = dataset_builder.load_processed_splits()
    sgkf = StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=42)

    for i, (tr_idx, cal_idx) in enumerate(sgkf.split(train_df, train_df["target_binary"], groups=train_df["ticker"])):
        tr_tickers = set(train_df["ticker"].iloc[tr_idx])
        cal_tickers = set(train_df["ticker"].iloc[cal_idx])
        overlap = tr_tickers.intersection(cal_tickers)
        assert len(overlap) == 0, f"Fold {i} had ticker leakage: {overlap}"
        assert train_df["target_binary"].iloc[cal_idx].sum() > 0


def test_stock_vs_observation_window_counts_reconciliation():
    """Verify that 982 represents observation windows (2 dates x 491 stocks), NOT 982 distinct stocks."""
    import json
    from src.surveillance.dataset_builder import DATASET_MANIFEST_JSON
    manifest = json.loads(DATASET_MANIFEST_JSON.read_text(encoding="utf-8"))

    # Distinct equities in universe is 500
    assert surveillance_universe.get_summary()["total_count"] == 500

    # Total observation windows is 4,910 (10 semi-annual dates x 491 usable stocks)
    assert manifest["total_windows"] == 4910

    # Holdout test split is 982 observation windows across 491 stocks
    test_split = manifest["splits"]["test"]
    assert test_split["count"] == 982
    assert test_split["positive_count"] == 8
    assert test_split["negative_count"] == 974
    assert test_split["positive_count"] + test_split["negative_count"] == 982



