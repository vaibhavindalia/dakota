"""Unit tests for JEV evaluation, metrics, walk-forward splitting, and baselines."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import pytest

from src.intelligence.jev.evaluation.metrics import (
    compute_brier_score,
    compute_ece,
    compute_nll,
    compute_all_metrics,
)
from src.intelligence.jev.evaluation.splits import WalkForwardSplitter
from src.intelligence.jev.evaluation.baselines import (
    MajorityClassBaseline,
    TfidfLogisticRegressionBaseline,
    FrontierReferenceBaseline,
)
from src.intelligence.jev.evaluation.benchmark import BenchmarkRunner
from src.intelligence.jev.adapters.mock_adapter import MockClassifierAdapter
from src.intelligence.jev.dataset import get_curated_indian_equity_dataset


def test_brier_score_perfect_and_worst_cases():
    classes = ["Bullish", "Bearish", "Neutral"]
    # Perfect predictions: score = 0.0
    y_true = ["Bullish", "Bearish"]
    y_probs_perfect = [
        {"Bullish": 1.0, "Bearish": 0.0, "Neutral": 0.0},
        {"Bullish": 0.0, "Bearish": 1.0, "Neutral": 0.0},
    ]
    brier_perfect = compute_brier_score(y_true, y_probs_perfect, classes)
    assert brier_perfect == 0.0

    # Completely wrong predictions: score = 2.0
    y_probs_worst = [
        {"Bullish": 0.0, "Bearish": 1.0, "Neutral": 0.0},
        {"Bullish": 1.0, "Bearish": 0.0, "Neutral": 0.0},
    ]
    brier_worst = compute_brier_score(y_true, y_probs_worst, classes)
    assert brier_worst == 2.0


def test_ece_perfect_calibration():
    # If confidence matches empirical accuracy in each bin, ECE is 0.0
    y_true = ["A", "A", "B", "B"]
    y_preds = ["A", "A", "B", "C"]  # 3 correct, 1 wrong
    y_confs = [1.0, 1.0, 1.0, 1.0]   # 75% accuracy with 100% confidence
    ece = compute_ece(y_true, y_preds, y_confs, n_bins=5)
    assert abs(ece - 0.25) < 1e-4


def test_walk_forward_splitter_temporal_invariants():
    # Construct 10 timestamps spaced by 12 hours
    base_time = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    records = [
        {"id": i, "timestamp": (base_time + timedelta(hours=i * 12)).isoformat(), "label": "Bullish"}
        for i in range(10)
    ]

    splitter = WalkForwardSplitter(n_splits=2, purge_window_hours=24.0, min_train_fraction=0.4)
    folds = splitter.split(records)

    assert len(folds) >= 1
    for fold in folds:
        # Assert strict temporal ordering
        assert fold.train_end < fold.test_start
        # Assert purge window is respected
        assert fold.test_start >= fold.train_end + timedelta(hours=24.0)
        # Assert no overlap in indices
        train_set = set(fold.train_indices)
        test_set = set(fold.test_indices)
        assert len(train_set.intersection(test_set)) == 0


def test_majority_baseline_prior_distribution():
    classes = ["A", "B", "C"]
    train_data = [
        {"label": "A"},
        {"label": "A"},
        {"label": "A"},
        {"label": "B"},
    ]
    baseline = MajorityClassBaseline(classes=classes)
    baseline.fit(train_data)

    res = baseline.predict_one({"text": "test"})
    assert res.predicted_label == "A"
    assert res.is_calibrated is True
    assert res.class_scores["A"] > res.class_scores["B"]
    assert res.confidence == pytest.approx(res.class_scores["A"])


def test_tfidf_logistic_regression_baseline():
    classes = ["Bullish", "Bearish"]
    train_data = [
        {"claim": "Record profits massive revenue increase high dividend", "label": "Bullish"},
        {"claim": "Record EBITDA jump institutional buying expansion", "label": "Bullish"},
        {"claim": "Severe loss auditor resignation fraud debt default", "label": "Bearish"},
        {"claim": "SEBI penalty regulatory shutdown bank default", "label": "Bearish"},
    ]
    model = TfidfLogisticRegressionBaseline(classes=classes)
    model.fit(train_data)

    test_sample = {"claim": "Strong profit growth revenue expansion"}
    pred = model.predict_one(test_sample)
    assert pred.predicted_label == "Bullish"
    assert pred.confidence > 0.5


def test_benchmark_runner_end_to_end_walk_forward():
    dataset = get_curated_indian_equity_dataset()
    runner = BenchmarkRunner(samples=dataset, n_splits=2, purge_window_hours=24.0)

    # Use deterministic mock adapter with tuned class preferences
    adapter = MockClassifierAdapter()
    report = runner.run(adapter)

    assert report.total_samples == len(dataset)
    assert report.n_folds >= 1
    assert "Majority Baseline" in report.model_summaries
    assert "TF-IDF + LogReg" in report.model_summaries
    assert f"JEV ({adapter.model_id})" in report.model_summaries

    md_table = report.to_markdown_table()
    assert "| Model | Accuracy | Macro-F1 |" in md_table
    assert f"JEV ({adapter.model_id})" in md_table


def test_frontier_reference_baseline_requires_api_key_or_raises():
    """Verify FrontierReferenceBaseline refuses to peek at ground truth without an API key."""
    import os
    orig = os.environ.get("OPENAI_API_KEY")
    try:
        os.environ.pop("OPENAI_API_KEY", None)
        baseline = FrontierReferenceBaseline()
        with pytest.raises(ValueError, match="OPENAI_API_KEY is not configured"):
            baseline.predict_one({"claim": "Test claim"})
    finally:
        if orig is not None:
            os.environ["OPENAI_API_KEY"] = orig

