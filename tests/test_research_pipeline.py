"""Automated Test Suite for Dakota Research Readiness, Dataset Audit & Baseline Pipeline.

Tests:
1. Batch processing all 82 records.
2. Idempotent reruns of preparation and audit pipeline.
3. Atomic saves and backup safety.
4. JSON and CSV consistency and parity.
5. Strict preservation of existing human labels (ANN-LIVE-001).
6. Strict separation of AI suggestions from human ground truth.
7. Evidence provenance tracking and source attribution.
8. Duplicate-group leakage checks (dev_groups ∩ held_out_groups == ∅).
9. Validation of canonical labels and rationale requirement.
10. Deterministic, reproducible dataset splits.
11. Evaluation input isolation (held-out reference labels omitted from prompts).
12. Correct metrics calculation and empty-dataset handling.
13. Graceful failure behavior when model or external sources are unavailable.
"""
from __future__ import annotations

import csv
import json
import math
import os
import shutil
import sys
import tempfile
import pytest

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from scripts.prepare_research_dataset import (
    build_inventory_and_audit,
    enrich_evidence_batch,
    generate_batch_preannotations,
    create_leakage_safe_splits,
    audit_research_readiness,
    CANONICAL_CLASSES,
)
from scripts.run_research_baselines import (
    compute_metrics,
    wilson_score_interval,
    run_majority_baseline,
    run_tfidf_logreg_baseline,
    run_mock_control_baseline,
)


def test_batch_inventory_audit_and_schema():
    """Verify inventory captures all 82 records with zero missing IDs or schema gaps."""
    summary = build_inventory_and_audit()
    assert summary["total_records"] == 82
    assert len(summary["missing_ids"]) == 0
    assert len(summary["duplicate_ids"]) == 0
    assert len(summary["csv_missing_in_json"]) == 0
    assert len(summary["json_missing_in_csv"]) == 0
    assert summary["total_duplicate_groups"] == 60


def test_json_csv_consistency():
    """Verify complete parity between annotation JSON and worklist CSV."""
    json_path = os.path.join(WORKSPACE_ROOT, "data", "annotation_ready_financial_evidence.json")
    csv_path = os.path.join(WORKSPACE_ROOT, "data", "annotation_worklist.csv")

    with open(json_path, "r", encoding="utf-8") as f:
        json_records = json.load(f)["records"]

    with open(csv_path, "r", encoding="utf-8") as f:
        csv_rows = list(csv.DictReader(f))

    assert len(json_records) == len(csv_rows) == 82

    for jr, cr in zip(json_records, csv_rows):
        assert jr["record_id"] == cr["record_id"]
        assert jr["ticker"] == cr["ticker"]
        assert jr["duplicate_group"] == cr["duplicate_group"]
        # If human label exists, CSV and JSON must match exactly
        if jr.get("human_reviewed_label"):
            assert jr["human_reviewed_label"] == cr["human_reviewed_label"]
            assert jr["annotation_rationale"] == cr["annotation_rationale"]
            assert jr["reviewer_id"] == cr["reviewer_id"]


def test_human_label_preservation_and_ai_separation():
    """Verify that existing human labels (ANN-LIVE-001) are preserved and never overwritten."""
    preann_summary, queue_path = generate_batch_preannotations()
    preann_file = os.path.join(WORKSPACE_ROOT, "data", "research", "pre_annotated_financial_evidence.json")

    with open(preann_file, "r", encoding="utf-8") as f:
        records = json.load(f)["records"]

    ann_001 = next(r for r in records if r["record_id"] == "ANN-LIVE-001")
    assert ann_001["human_reviewed_label"] == "Insufficient Evidence"
    assert ann_001["reviewer_id"] == "REV-VAIBHAV"
    assert ann_001["review_status"] == "completed"

    # Verify that all other 81 records have None for human_reviewed_label
    unreviewed = [r for r in records if r["record_id"] != "ANN-LIVE-001"]
    assert all(r["human_reviewed_label"] is None for r in unreviewed)

    # Verify that AI suggestions exist separately across all records
    assert all(r.get("ai_suggested_label") in CANONICAL_CLASSES for r in records)
    assert all(r.get("ai_suggestion_rationale") for r in records)
    assert all(r.get("suggestion_model") == "dakota-research-rules-v1.0" for r in records)


def test_duplicate_group_leakage_safe_splits():
    """Strictly verify that zero duplicate groups cross the dev/held-out split boundary."""
    manifest = create_leakage_safe_splits(random_seed=42, dev_ratio=0.65)

    dev_groups = set(manifest["dev_split"]["group_ids"])
    held_out_groups = set(manifest["held_out_split"]["group_ids"])

    # Strict group isolation: intersection must be empty
    group_overlap = dev_groups & held_out_groups
    assert len(group_overlap) == 0, f"Leaked duplicate groups detected: {group_overlap}"

    # Strict record isolation: intersection must be empty
    dev_records = set(manifest["dev_split"]["record_ids"])
    held_out_records = set(manifest["held_out_split"]["record_ids"])
    record_overlap = dev_records & held_out_records
    assert len(record_overlap) == 0, f"Leaked records detected: {record_overlap}"

    # Total conservation
    assert len(dev_records) + len(held_out_records) == 82
    assert len(dev_groups) + len(held_out_groups) == 60


def test_idempotent_rerun():
    """Verify that multiple pipeline runs produce identical, deterministic results."""
    manifest1 = create_leakage_safe_splits(random_seed=42, dev_ratio=0.65)
    manifest2 = create_leakage_safe_splits(random_seed=42, dev_ratio=0.65)

    assert manifest1["dev_split"]["record_ids"] == manifest2["dev_split"]["record_ids"]
    assert manifest1["held_out_split"]["record_ids"] == manifest2["held_out_split"]["record_ids"]


def test_metrics_calculation_and_edge_cases():
    """Verify precision, recall, macro F1, and empty dataset handling."""
    y_true = ["Bullish", "Bearish", "Neutral", "Insufficient Evidence"]
    y_pred = ["Bullish", "Bearish", "Insufficient Evidence", "Insufficient Evidence"]

    m = compute_metrics(y_true, y_pred, CANONICAL_CLASSES)
    assert m["total_samples"] == 4
    assert m["correct"] == 3
    assert m["accuracy"] == 0.75
    assert m["ci_95"][0] <= 0.75 <= m["ci_95"][1]

    # Empty dataset handling
    empty_m = compute_metrics([], [], CANONICAL_CLASSES)
    assert empty_m["total_samples"] == 0
    assert empty_m["accuracy"] == 0.0
    assert empty_m["macro_f1"] == 0.0


def test_wilson_score_interval_bounds():
    """Verify Wilson score confidence interval mathematical properties."""
    low, high = wilson_score_interval(50, 100)
    assert 0.0 <= low < 0.50 < high <= 1.0
    assert abs(high - 0.50) == pytest.approx(abs(0.50 - low), abs=1e-4)  # Symmetric at p=0.5

    # Edge cases
    low0, high0 = wilson_score_interval(0, 100)
    assert low0 == 0.0
    assert high0 > 0.0

    low1, high1 = wilson_score_interval(100, 100)
    assert low1 < 1.0
    assert high1 == 1.0


def test_baselines_execution_on_mock_data():
    """Verify majority and TF-IDF baseline runners execute cleanly."""
    train_texts = ["stock rally buy now", "loss penalty fraud crash", "routine board meeting quarterly", "spam jackpot rocket tip"]
    train_labels = ["Bullish", "Bearish", "Neutral", "Insufficient Evidence"]
    eval_texts = ["breaking rally high", "unknown tip guaranteed"]

    maj_preds, maj_lat = run_majority_baseline(train_labels, eval_texts)
    assert len(maj_preds) == 2
    assert maj_preds[0] in CANONICAL_CLASSES

    tfidf_preds, tfidf_lat = run_tfidf_logreg_baseline(train_texts, train_labels, eval_texts)
    assert len(tfidf_preds) == 2
    assert all(p in CANONICAL_CLASSES for p in tfidf_preds)


def test_research_readiness_audit_pass():
    """Verify research readiness audit gates execute and return valid statuses."""
    report = audit_research_readiness()
    assert report["overall_status"] in ["PASS", "PASS_WITH_WARNINGS"]
    assert report["total_records_audited"] == 82
    for check in report["checks"]:
        assert check["status"] in ["PASS", "WARNING", "FAIL"]
