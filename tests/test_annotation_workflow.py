"""Regression and verification tests for Dakota Phase 3.1 annotation workflow."""
import csv
import json
import os
import tempfile
import pytest

from scripts.annotate_financial_evidence import (
    CANONICAL_CLASSES,
    load_dataset,
    save_dataset,
    print_status,
    export_to_csv,
    import_from_csv,
    export_splits,
)


@pytest.fixture
def sample_dataset_path(tmp_path):
    """Creates a temporary annotation dataset for isolated testing."""
    records = [
        {
            "record_id": "ANN-LIVE-001",
            "ticker": "INFY",
            "original_text": "Q2 revenue up 14% with strong BFSI deal pipeline.",
            "news_headlines": ["[Reuters] Infosys raises FY26 forecast"],
            "sources": [{"name": "Reuters", "url": "https://reuters.com/article/1"}],
            "published_at": "2026-10-10T09:00:00Z",
            "collected_at": "2026-10-10T09:05:00Z",
            "duplicate_group": "group_infy_01",
            "human_reviewed_label": None,
            "annotation_rationale": None,
            "evidence_ids": ["E_INFY_01"],
            "sample": {"ticker": "INFY", "latest_price": 1820.0},
        },
        {
            "record_id": "ANN-LIVE-002",
            "ticker": "INFY",
            "original_text": "INFY target 2200 buy immediately huge upside",
            "news_headlines": ["[Reuters] Infosys raises FY26 forecast"],
            "sources": [{"name": "Reuters", "url": "https://reuters.com/article/1"}],
            "published_at": "2026-10-10T09:10:00Z",
            "collected_at": "2026-10-10T09:12:00Z",
            "duplicate_group": "group_infy_01",
            "human_reviewed_label": None,
            "annotation_rationale": None,
            "evidence_ids": ["E_INFY_02"],
            "sample": {"ticker": "INFY", "latest_price": 1820.0},
        },
        {
            "record_id": "ANN-LIVE-003",
            "ticker": "VEDL",
            "original_text": "Reports of 500 cr SEBI penalty denied by company",
            "news_headlines": ["[BSE] Vedanta clarification on penalty notice"],
            "sources": [{"name": "BSE", "url": "https://bseindia.com/1"}],
            "published_at": "2026-10-11T10:00:00Z",
            "collected_at": "2026-10-11T10:02:00Z",
            "duplicate_group": "group_vedl_01",
            "human_reviewed_label": None,
            "annotation_rationale": None,
            "evidence_ids": ["E_VEDL_01"],
            "sample": {"ticker": "VEDL", "latest_price": 450.0},
        },
        {
            "record_id": "ANN-LIVE-004",
            "ticker": "UNKNOWN",
            "original_text": "Join VIP group for 1000% multibagger stocks daily!!",
            "news_headlines": [],
            "sources": [],
            "published_at": "2026-10-12T11:00:00Z",
            "collected_at": "2026-10-12T11:01:00Z",
            "duplicate_group": "group_spam_01",
            "human_reviewed_label": None,
            "annotation_rationale": None,
            "evidence_ids": ["E_SPAM_01"],
            "sample": {"ticker": "UNKNOWN"},
        },
    ]

    data = {
        "metadata": {
            "version": "1.0",
            "description": "Test dataset",
        },
        "records": records,
    }

    file_path = str(tmp_path / "test_annotation_dataset.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return file_path


def test_load_and_save_lifecycle(sample_dataset_path):
    metadata, records = load_dataset(sample_dataset_path)
    assert len(records) == 4
    assert records[0]["review_status"] == "pending"

    # Annotate one record
    records[0]["human_reviewed_label"] = "Bullish"
    records[0]["annotation_rationale"] = "Earnings beat with 14% growth"
    records[0]["reviewer_id"] = "REV-TEST"
    records[0]["review_status"] = "completed"

    save_dataset(metadata, records, sample_dataset_path)

    # Reload and assert persistence and backup
    meta_reload, rec_reload = load_dataset(sample_dataset_path)
    assert rec_reload[0]["human_reviewed_label"] == "Bullish"
    assert rec_reload[0]["review_status"] == "completed"
    assert meta_reload["completed_annotations"] == 1
    assert meta_reload["pending_records"] == 3
    assert os.path.isfile(f"{sample_dataset_path}.bak")


def test_status_and_duplicate_collision_detection(sample_dataset_path):
    metadata, records = load_dataset(sample_dataset_path)
    # Assign conflicting labels to same duplicate group (group_infy_01)
    records[0]["human_reviewed_label"] = "Bullish"
    records[0]["review_status"] = "completed"
    records[1]["human_reviewed_label"] = "Bearish"
    records[1]["review_status"] = "completed"
    save_dataset(metadata, records, sample_dataset_path)

    status = print_status(sample_dataset_path)
    assert status["completed"] == 2
    assert status["conflicting_groups_count"] == 1


def test_csv_roundtrip_and_validation(sample_dataset_path, tmp_path):
    csv_path = str(tmp_path / "worklist.csv")
    export_to_csv(sample_dataset_path, csv_path)
    assert os.path.isfile(csv_path)

    # Read CSV and fill valid annotation
    with open(csv_path, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 4
    rows[0]["human_reviewed_label"] = "Bullish"
    rows[0]["annotation_rationale"] = "Solid revenue beat"
    rows[0]["reviewer_id"] = "REV-CSV"

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    # Import and verify
    imported = import_from_csv(csv_path, sample_dataset_path)
    assert imported == 1

    _, reloaded = load_dataset(sample_dataset_path)
    assert reloaded[0]["human_reviewed_label"] == "Bullish"
    assert reloaded[0]["reviewer_id"] == "REV-CSV"


def test_csv_rejection_of_invalid_label(sample_dataset_path, tmp_path):
    csv_path = str(tmp_path / "worklist_invalid.csv")
    export_to_csv(sample_dataset_path, csv_path)

    with open(csv_path, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    rows[0]["human_reviewed_label"] = "ExtremelyBullish"  # Invalid
    rows[0]["annotation_rationale"] = "Valid rationale"

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ValueError, match="CSV import failed validation"):
        import_from_csv(csv_path, sample_dataset_path)


def test_group_aware_split_export(sample_dataset_path, tmp_path):
    metadata, records = load_dataset(sample_dataset_path)
    # Complete annotations for all 4
    for r in records:
        r["human_reviewed_label"] = "Neutral"
        r["annotation_rationale"] = "Verified"
        r["review_status"] = "completed"
        r["reviewer_id"] = "REV-TEST"
    save_dataset(metadata, records, sample_dataset_path)

    dev_out = str(tmp_path / "dev.json")
    held_out_out = str(tmp_path / "held_out.json")

    export_splits(sample_dataset_path, dev_out, held_out_out, dev_group_ratio=0.60)

    with open(dev_out, "r") as f:
        dev_data = json.load(f)
    with open(held_out_out, "r") as f:
        held_out_data = json.load(f)

    dev_groups = {d["metadata"]["duplicate_group"] for d in dev_data}
    held_out_groups = {d["metadata"]["duplicate_group"] for d in held_out_data}

    # Strict assertion: zero group leakage
    assert not (dev_groups & held_out_groups)
    # Both INFY records must be in the same split because they share group_infy_01
    infy_dev = [d for d in dev_data if d["record_id"] in ("ANN-LIVE-001", "ANN-LIVE-002")]
    infy_held = [d for d in held_out_data if d["record_id"] in ("ANN-LIVE-001", "ANN-LIVE-002")]
    assert len(infy_dev) == 2 or len(infy_held) == 2
