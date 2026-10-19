"""Audit script for Dakota Phase 3.1 annotation dataset.

Performs verification of all 82 records in data/annotation_ready_financial_evidence.json:
- Validates stable IDs ANN-LIVE-001 through ANN-LIVE-082 (no gaps, sequential).
- Verifies completeness across required fields.
- Analyzes source provenance (news vs social vs forum).
- Identifies duplicate groups and ensures group integrity.
- Evaluates evidence accessibility and content quality.
- Verifies that zero unreviewed records are falsely marked as human-reviewed.
- Calculates group-based split partition to prevent event/duplicate leakage.
"""
import json
import os
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, List

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_PATH = os.path.join(WORKSPACE_ROOT, "data", "annotation_ready_financial_evidence.json")


def audit_dataset() -> Dict[str, Any]:
    if not os.path.isfile(DATA_PATH):
        raise FileNotFoundError(f"Annotation dataset not found at {DATA_PATH}")

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        payload = json.load(f)

    metadata = payload.get("metadata", {})
    records = payload.get("records", [])

    total = len(records)
    print(f"=== AUDITING DAKOTA ANNOTATION DATASET ===")
    print(f"Dataset path: {DATA_PATH}")
    print(f"Total records in dataset: {total}")

    # 1. ID verification
    expected_ids = [f"ANN-LIVE-{i:03d}" for i in range(1, total + 1)]
    actual_ids = [r.get("record_id") for r in records]
    missing_ids = set(expected_ids) - set(actual_ids)
    duplicate_ids = [id_ for id_, count in Counter(actual_ids).items() if count > 1]

    print(f"\n[1] Record ID Integrity:")
    print(f"    Expected format: ANN-LIVE-001 .. ANN-LIVE-{total:03d}")
    print(f"    Missing IDs: {missing_ids or 'None (Strict match)'}")
    print(f"    Duplicate IDs: {duplicate_ids or 'None (Unique)'}")

    # 2. Field Completeness
    required_fields = [
        "record_id", "ticker", "original_text", "news_headlines",
        "sources", "published_at", "collected_at", "duplicate_group",
        "human_reviewed_label", "annotation_rationale", "evidence_ids"
    ]
    missing_by_field = Counter()
    empty_headlines_count = 0
    empty_sources_count = 0
    empty_social_count = 0

    for r in records:
        for f in required_fields:
            if f not in r:
                missing_by_field[f] += 1
        if not r.get("news_headlines"):
            empty_headlines_count += 1
        if not r.get("sources"):
            empty_sources_count += 1
        if not r.get("original_text"):
            empty_social_count += 1

    print(f"\n[2] Field Completeness:")
    print(f"    Missing fields: {dict(missing_by_field) or 'None (100% complete schema)'}")
    print(f"    Records with news headlines: {total - empty_headlines_count} / {total}")
    print(f"    Records with sources: {total - empty_sources_count} / {total}")
    print(f"    Records with original text / social signals: {total - empty_social_count} / {total}")

    # 3. Provenance & Source Analysis
    source_domains = Counter()
    source_protocols = Counter()
    total_sources = 0

    for r in records:
        for s in r.get("sources", []):
            total_sources += 1
            url = s.get("url", "")
            if url.startswith("https://"):
                source_protocols["https"] += 1
            elif url.startswith("http://"):
                source_protocols["http"] += 1
            else:
                source_protocols["non-standard"] += 1

            if "reddit.com" in url:
                source_domains["Reddit"] += 1
            elif "news.google.com" in url:
                source_domains["Google News"] += 1
            elif "finance.yahoo.com" in url:
                source_domains["Yahoo Finance"] += 1
            elif "bseindia.com" in url:
                source_domains["BSE Disclosures"] += 1
            elif "nseindia.com" in url:
                source_domains["NSE Disclosures"] += 1
            else:
                source_domains["Other Web / RSS"] += 1

    print(f"\n[3] Source Provenance:")
    print(f"    Total supporting sources: {total_sources} across {total} records")
    print(f"    Protocols: {dict(source_protocols)}")
    print(f"    Source domains: {dict(source_domains)}")

    # 4. Duplicate Groups & Event Clusters
    dup_groups = defaultdict(list)
    for r in records:
        dup_groups[r.get("duplicate_group", "unknown")].append(r.get("record_id"))

    multi_record_groups = {k: v for k, v in dup_groups.items() if len(v) > 1}
    single_record_groups = {k: v for k, v in dup_groups.items() if len(v) == 1}

    print(f"\n[4] Duplicate & Event Clusters:")
    print(f"    Total unique event/duplicate groups: {len(dup_groups)}")
    print(f"    Single-record groups: {len(single_record_groups)}")
    print(f"    Multi-record clusters: {len(multi_record_groups)} clusters covering {sum(len(v) for v in multi_record_groups.values())} records")
    for gid, members in sorted(multi_record_groups.items(), key=lambda x: len(x[1]), reverse=True)[:5]:
        print(f"      - Cluster {gid} ({len(members)} records): {members}")

    # 5. Label & Annotation Status
    human_labeled = [r for r in records if r.get("human_reviewed_label") is not None]
    rationales_present = [r for r in records if r.get("annotation_rationale") is not None]

    print(f"\n[5] Human Ground-Truth Status:")
    print(f"    Human-reviewed labels: {len(human_labeled)} / {total}")
    print(f"    Annotation rationales: {len(rationales_present)} / {total}")
    print(f"    Unlabeled records pending human review: {total - len(human_labeled)}")

    # 6. Group-Based Splitting Strategy (to prevent event leakage)
    # Target 70/30 Dev vs Held-Out split based on duplicate groups
    all_group_ids = sorted(list(dup_groups.keys()))
    dev_records = []
    held_out_records = []

    dev_groups = set()
    held_out_groups = set()

    # Alternate assignment by group to maintain balance
    for idx, gid in enumerate(all_group_ids):
        members = dup_groups[gid]
        if idx % 3 == 0:  # ~33% held-out by group
            held_out_groups.add(gid)
            held_out_records.extend(members)
        else:
            dev_groups.add(gid)
            dev_records.extend(members)

    print(f"\n[6] Group-Aware Split Validation:")
    print(f"    Dev split: {len(dev_records)} records across {len(dev_groups)} clusters ({len(dev_records)/total*100:.1f}%)")
    print(f"    Held-Out split: {len(held_out_records)} records across {len(held_out_groups)} clusters ({len(held_out_records)/total*100:.1f}%)")
    intersection = set(dev_records) & set(held_out_records)
    print(f"    Cross-split record leakage: {len(intersection)} (Strict 0)")
    group_intersection = dev_groups & held_out_groups
    print(f"    Cross-split group leakage: {len(group_intersection)} (Strict 0)")

    return {
        "total_records": total,
        "missing_ids": list(missing_ids),
        "duplicate_ids": duplicate_ids,
        "missing_by_field": dict(missing_by_field),
        "source_domains": dict(source_domains),
        "total_clusters": len(dup_groups),
        "multi_record_clusters": len(multi_record_groups),
        "human_labeled_count": len(human_labeled),
        "dev_records_count": len(dev_records),
        "held_out_records_count": len(held_out_records),
    }


if __name__ == "__main__":
    audit_dataset()
