"""Human Annotation Workflow for Indian Financial Evidence (Dakota Phase 3.1).

Provides an audit-compliant, robust review tool supporting:
- Interactive CLI annotation with immediate atomic saves.
- CSV export and import for spreadsheet-based review workflows.
- Strict validation against Dakota's 6 canonical classes.
- Rationale tracking, reviewer ID, review status, and UTC timestamps.
- Zero-leakage duplicate group preservation.
- Status and progress reporting with duplicate consistency checks.

Usage:
    python scripts/annotate_financial_evidence.py status
    python scripts/annotate_financial_evidence.py annotate [--reviewer REV-01] [--resume]
    python scripts/annotate_financial_evidence.py export-csv [--output data/annotation_worklist.csv]
    python scripts/annotate_financial_evidence.py import-csv --input data/annotation_worklist.csv
    python scripts/annotate_financial_evidence.py export-splits [--dev-ratio 0.65]
"""
from __future__ import annotations

import argparse
import csv
import datetime
import io
import json
import os
import shutil
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_DATASET_PATH = os.path.join(WORKSPACE_ROOT, "data", "annotation_ready_financial_evidence.json")

CANONICAL_CLASSES = [
    "Bullish",
    "Bearish",
    "Neutral",
    "Mixed",
    "Ambiguous",
    "Insufficient Evidence",
]

CLASS_SHORTCUTS = {
    "1": "Bullish",
    "2": "Bearish",
    "3": "Neutral",
    "4": "Mixed",
    "5": "Ambiguous",
    "6": "Insufficient Evidence",
    "bullish": "Bullish",
    "bearish": "Bearish",
    "neutral": "Neutral",
    "mixed": "Mixed",
    "ambiguous": "Ambiguous",
    "insufficient evidence": "Insufficient Evidence",
    "insufficient": "Insufficient Evidence",
}

REVIEW_STATUSES = ["pending", "completed", "flagged"]


def load_dataset(filepath: str = DEFAULT_DATASET_PATH) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Load and normalize the annotation dataset."""
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"Annotation dataset file not found: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    metadata = data.get("metadata", {})
    records = data.get("records", [])

    # Ensure metadata tracking fields exist on each record
    for r in records:
        if "review_status" not in r:
            r["review_status"] = "completed" if r.get("human_reviewed_label") else "pending"
        if "reviewer_id" not in r:
            r["reviewer_id"] = None
        if "reviewed_at" not in r:
            r["reviewed_at"] = None

    return metadata, records


def save_dataset(
    metadata: Dict[str, Any],
    records: List[Dict[str, Any]],
    filepath: str = DEFAULT_DATASET_PATH,
    backup: bool = True,
) -> None:
    """Save dataset atomically with a safety backup copy."""
    if backup and os.path.isfile(filepath):
        backup_path = f"{filepath}.bak"
        shutil.copy2(filepath, backup_path)

    metadata["last_updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    metadata["total_records"] = len(records)
    metadata["completed_annotations"] = sum(
        1 for r in records if r.get("human_reviewed_label") is not None and r.get("review_status") == "completed"
    )
    metadata["flagged_records"] = sum(1 for r in records if r.get("review_status") == "flagged")
    metadata["pending_records"] = sum(1 for r in records if r.get("review_status") == "pending")

    payload = {
        "metadata": metadata,
        "records": records,
    }

    tmp_path = f"{filepath}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    os.replace(tmp_path, filepath)


def print_status(filepath: str = DEFAULT_DATASET_PATH) -> Dict[str, Any]:
    """Calculate and display dataset annotation progress, label counts, and consistency."""
    metadata, records = load_dataset(filepath)
    total = len(records)

    completed = [r for r in records if r.get("review_status") == "completed" and r.get("human_reviewed_label")]
    flagged = [r for r in records if r.get("review_status") == "flagged"]
    pending = [r for r in records if r.get("review_status") == "pending"]

    print("\n" + "=" * 65)
    print("      DAKOTA PHASE 3.1 — HUMAN ANNOTATION PROGRESS REPORT")
    print("=" * 65)
    print(f"Dataset path:      {filepath}")
    print(f"Total records:     {total}")
    print(f"Completed:         {len(completed):2d} ({len(completed)/total*100:5.1f}%)")
    print(f"Flagged (Review):  {len(flagged):2d} ({len(flagged)/total*100:5.1f}%)")
    print(f"Pending:           {len(pending):2d} ({len(pending)/total*100:5.1f}%)")

    # Label distribution among completed records
    label_counts = Counter(r.get("human_reviewed_label") for r in completed)
    print("\n[Completed Label Distribution]")
    for cls_name in CANONICAL_CLASSES:
        cnt = label_counts.get(cls_name, 0)
        pct = (cnt / len(completed) * 100) if completed else 0.0
        print(f"  - {cls_name:22s}: {cnt:2d} ({pct:5.1f}%)")

    # Reviewer contributions
    reviewer_counts = Counter(r.get("reviewer_id") for r in completed if r.get("reviewer_id"))
    if reviewer_counts:
        print("\n[Reviewer Breakdown]")
        for rev, cnt in reviewer_counts.most_common():
            print(f"  - {rev:15s}: {cnt:2d} reviews")

    # Duplicate consistency check
    dup_labels: Dict[str, set] = defaultdict(set)
    for r in completed:
        grp = r.get("duplicate_group")
        lbl = r.get("human_reviewed_label")
        if grp and lbl:
            dup_labels[grp].add(lbl)

    conflicting_groups = {grp: lbls for grp, lbls in dup_labels.items() if len(lbls) > 1}
    if conflicting_groups:
        print("\n[WARNING: Duplicate Group Label Conflicts Detected!]")
        for grp, lbls in conflicting_groups.items():
            conflicting_records = [r["record_id"] for r in completed if r.get("duplicate_group") == grp]
            print(f"  - Group {grp}: Conflicting labels {list(lbls)} across records {conflicting_records}")
    else:
        print("\n[Duplicate Group Consistency]: 100% consistent (no conflicting labels in peer groups)")

    print("=" * 65 + "\n")

    return {
        "total": total,
        "completed": len(completed),
        "flagged": len(flagged),
        "pending": len(pending),
        "label_counts": dict(label_counts),
        "conflicting_groups_count": len(conflicting_groups),
    }


def run_interactive_annotation(
    reviewer_id: str,
    filepath: str = DEFAULT_DATASET_PATH,
    resume: bool = True,
) -> None:
    """Run interactive terminal-based annotation loop."""
    metadata, records = load_dataset(filepath)
    total = len(records)

    # Filter targets
    if resume:
        target_indices = [i for i, r in enumerate(records) if r.get("review_status") == "pending"]
    else:
        target_indices = list(range(total))

    if not target_indices:
        print("All records have already been reviewed! Run with --no-resume to re-review records.")
        return

    print("\n" + "=" * 70)
    print("      DAKOTA FINANCIAL EVIDENCE ANNOTATION TERMINAL")
    print(f"      Reviewer: {reviewer_id} | Records to review: {len(target_indices)}")
    print("=" * 70)
    print("Canonical Labels:")
    print("  [1] Bullish               [4] Mixed")
    print("  [2] Bearish               [5] Ambiguous")
    print("  [3] Neutral               [6] Insufficient Evidence")
    print("Commands: [F] Flag for Panel | [S] Skip | [B] Back | [Q] Save & Quit")
    print("-" * 70)

    curr_ptr = 0
    while curr_ptr < len(target_indices):
        rec_idx = target_indices[curr_ptr]
        r = records[rec_idx]

        print("\n" + "#" * 70)
        print(f"Record {curr_ptr + 1} of {len(target_indices)} | ID: {r.get('record_id')} | Status: {r.get('review_status', 'pending').upper()}")
        print(f"Ticker: {r.get('ticker')} | Group: {r.get('duplicate_group')} | Time: {r.get('published_at')}")
        print(f"Evidence IDs: {', '.join(r.get('evidence_ids', []))}")
        print("-" * 70)
        print(f"SOCIAL / ORIGINAL TEXT:")
        print(f"  \"{r.get('original_text', '').strip()}\"")

        headlines = r.get("news_headlines", [])
        if headlines:
            print(f"\nNEWS HEADLINES ({len(headlines)} items):")
            for h in headlines[:5]:
                print(f"  * {h}")
            if len(headlines) > 5:
                print(f"  * ... ({len(headlines) - 5} more headlines omitted)")
        else:
            print(f"\nNEWS HEADLINES: (None attached to this record)")

        sources = r.get("sources", [])
        if sources:
            print(f"\nSOURCES ({len(sources)} items):")
            for s in sources[:4]:
                print(f"  - {s.get('name')}: {s.get('url')}")
            if len(sources) > 4:
                print(f"  - ... ({len(sources) - 4} more sources omitted)")

        sample_data = r.get("sample", {})
        if sample_data:
            price = sample_data.get("latest_price")
            chg = sample_data.get("change_pct")
            vol = sample_data.get("volume")
            deliv = sample_data.get("delivery_pct")
            surv = sample_data.get("is_surveillance")
            risk = sample_data.get("risk_score")
            print(f"\nTELEMETRY: Price={price}, Chg%={chg}, Vol={vol}, Deliv%={deliv}, Surv={surv}, RiskScore={risk}")

        if r.get("human_reviewed_label"):
            print(f"\nCURRENT LABEL: {r.get('human_reviewed_label')} (by {r.get('reviewer_id')})")
            print(f"CURRENT RATIONALE: {r.get('annotation_rationale')}")

        print("-" * 70)

        # Get choice
        while True:
            choice = input("Select Label [1-6, F=Flag, S=Skip, B=Back, Q=Quit]: ").strip().lower()
            if choice == "q":
                save_dataset(metadata, records, filepath)
                print(f"\nProgress saved to {filepath}. Exiting.")
                return
            elif choice == "s":
                curr_ptr += 1
                break
            elif choice == "b":
                if curr_ptr > 0:
                    curr_ptr -= 1
                else:
                    print("Already at the first record.")
                break
            elif choice == "f":
                rationale = input("Enter rationale for flagging (e.g. Broken URL, Corrupted Text): ").strip()
                if not rationale:
                    print("Rationale is required when flagging a record!")
                    continue
                r["review_status"] = "flagged"
                r["reviewer_id"] = reviewer_id
                r["annotation_rationale"] = rationale
                r["reviewed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                save_dataset(metadata, records, filepath)
                print(f">> Record {r.get('record_id')} FLAGGED.")
                curr_ptr += 1
                break
            elif choice in CLASS_SHORTCUTS:
                assigned_label = CLASS_SHORTCUTS[choice]
                rationale = input(f"Enter rationale for [{assigned_label}] (required): ").strip()
                while not rationale:
                    print("Rationale cannot be blank! Please describe why this label was assigned.")
                    rationale = input(f"Enter rationale for [{assigned_label}]: ").strip()

                r["human_reviewed_label"] = assigned_label
                r["annotation_rationale"] = rationale
                r["reviewer_id"] = reviewer_id
                r["review_status"] = "completed"
                r["reviewed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

                save_dataset(metadata, records, filepath)
                print(f">> Record {r.get('record_id')} saved as [{assigned_label}].")
                curr_ptr += 1
                break
            else:
                print("Invalid input! Enter 1-6, F, S, B, or Q.")

    print("\nAnnotation loop completed!")
    print_status(filepath)


def export_to_csv(filepath: str = DEFAULT_DATASET_PATH, output_csv: Optional[str] = None) -> str:
    """Export dataset to CSV format for external spreadsheet annotation."""
    if output_csv is None:
        output_csv = os.path.join(WORKSPACE_ROOT, "data", "annotation_worklist.csv")

    metadata, records = load_dataset(filepath)

    fieldnames = [
        "record_id",
        "ticker",
        "duplicate_group",
        "published_at",
        "human_reviewed_label",
        "annotation_rationale",
        "reviewer_id",
        "review_status",
        "reviewed_at",
        "original_text",
        "news_headlines",
        "source_urls",
        "evidence_ids",
    ]

    with open(output_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for r in records:
            headlines_str = " | ".join(r.get("news_headlines", []))
            sources_str = " | ".join(s.get("url", "") for s in r.get("sources", []))
            evidence_str = ", ".join(r.get("evidence_ids", []))

            writer.writerow({
                "record_id": r.get("record_id"),
                "ticker": r.get("ticker"),
                "duplicate_group": r.get("duplicate_group"),
                "published_at": r.get("published_at"),
                "human_reviewed_label": r.get("human_reviewed_label") or "",
                "annotation_rationale": r.get("annotation_rationale") or "",
                "reviewer_id": r.get("reviewer_id") or "",
                "review_status": r.get("review_status") or "pending",
                "reviewed_at": r.get("reviewed_at") or "",
                "original_text": r.get("original_text", ""),
                "news_headlines": headlines_str,
                "source_urls": sources_str,
                "evidence_ids": evidence_str,
            })

    print(f"Exported {len(records)} records to CSV: {output_csv}")
    return output_csv


def import_from_csv(input_csv: str, filepath: str = DEFAULT_DATASET_PATH) -> int:
    """Import reviewed annotations from CSV, validating labels and rationales."""
    if not os.path.isfile(input_csv):
        raise FileNotFoundError(f"Input CSV not found: {input_csv}")

    metadata, records = load_dataset(filepath)
    records_by_id = {r.get("record_id"): r for r in records}

    updated_count = 0
    errors = []

    with open(input_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row_idx, row in enumerate(reader, start=2):
            rec_id = row.get("record_id")
            if not rec_id or rec_id not in records_by_id:
                errors.append(f"Row {row_idx}: Unknown record_id '{rec_id}'")
                continue

            r = records_by_id[rec_id]
            raw_label = (row.get("human_reviewed_label") or "").strip()
            rationale = (row.get("annotation_rationale") or "").strip()
            reviewer = (row.get("reviewer_id") or "").strip()
            status = (row.get("review_status") or "pending").strip().lower()

            if not raw_label:
                # Remains pending
                continue

            # Validate label against canonical set
            matched_label = None
            for c in CANONICAL_CLASSES:
                if raw_label.lower() == c.lower():
                    matched_label = c
                    break

            if not matched_label:
                errors.append(f"Row {row_idx} ({rec_id}): Invalid label '{raw_label}'. Allowed: {CANONICAL_CLASSES}")
                continue

            if not rationale:
                errors.append(f"Row {row_idx} ({rec_id}): Labeled record is missing annotation_rationale.")
                continue

            if not reviewer:
                reviewer = "HUMAN_REVIEWER"

            # Apply verified changes
            r["human_reviewed_label"] = matched_label
            r["annotation_rationale"] = rationale
            r["reviewer_id"] = reviewer
            r["review_status"] = "completed" if status != "flagged" else "flagged"
            r["reviewed_at"] = row.get("reviewed_at") or datetime.datetime.now(datetime.timezone.utc).isoformat()
            updated_count += 1

    if errors:
        print("\n[VALIDATION ERRORS ENCOUNTERED DURING CSV IMPORT]:")
        for err in errors[:10]:
            print(f"  * {err}")
        if len(errors) > 10:
            print(f"  * ... ({len(errors) - 10} additional errors)")
        raise ValueError(f"CSV import failed validation with {len(errors)} errors.")

    save_dataset(metadata, records, filepath)
    print(f"Successfully imported {updated_count} human annotations from {input_csv}.")
    print_status(filepath)
    return updated_count


def export_splits(
    filepath: str = DEFAULT_DATASET_PATH,
    dev_output: Optional[str] = None,
    held_out_output: Optional[str] = None,
    dev_group_ratio: float = 0.65,
) -> Tuple[str, str]:
    """Partition completed human annotations into Dev and Held-Out sets by duplicate group.
    
    Strictly preserves event clusters to prevent train/test contamination.
    """
    metadata, records = load_dataset(filepath)

    completed = [r for r in records if r.get("review_status") == "completed" and r.get("human_reviewed_label")]
    if not completed:
        raise ValueError("Cannot export splits: 0 records have completed human annotations.")

    if dev_output is None:
        dev_output = os.path.join(WORKSPACE_ROOT, "data", "financial_eval_dev.json")
    if held_out_output is None:
        held_out_output = os.path.join(WORKSPACE_ROOT, "data", "financial_eval_held_out.json")

    # Group completed records by duplicate group
    groups = defaultdict(list)
    for r in completed:
        grp = r.get("duplicate_group", "unknown")
        groups[grp].append(r)

    sorted_groups = sorted(list(groups.keys()))
    dev_records = []
    held_out_records = []

    dev_groups = set()
    held_out_groups = set()

    for idx, grp in enumerate(sorted_groups):
        members = groups[grp]
        # Assign to held-out if index hits remainder
        ratio_threshold = int(len(sorted_groups) * dev_group_ratio)
        if idx >= ratio_threshold:
            held_out_groups.add(grp)
            held_out_records.extend(members)
        else:
            dev_groups.add(grp)
            dev_records.extend(members)

    # Convert to standard evaluation format
    def format_split_payload(split_records: List[Dict[str, Any]], split_name: str) -> List[Dict[str, Any]]:
        items = []
        for r in split_records:
            items.append({
                "record_id": r["record_id"],
                "ticker": r["ticker"],
                "label": r["human_reviewed_label"],
                "evidence_ids": r.get("evidence_ids", []),
                "sample": r.get("sample", {}),
                "metadata": {
                    "split": split_name,
                    "duplicate_group": r.get("duplicate_group"),
                    "reviewer_id": r.get("reviewer_id"),
                    "annotation_rationale": r.get("annotation_rationale"),
                    "reviewed_at": r.get("reviewed_at"),
                }
            })
        return items

    dev_data = format_split_payload(dev_records, "dev")
    held_out_data = format_split_payload(held_out_records, "held_out")

    with open(dev_output, "w", encoding="utf-8") as f:
        json.dump(dev_data, f, indent=2)

    with open(held_out_output, "w", encoding="utf-8") as f:
        json.dump(held_out_data, f, indent=2)

    print(f"Created Dev split: {len(dev_records)} records ({len(dev_groups)} groups) -> {dev_output}")
    print(f"Created Held-Out split: {len(held_out_records)} records ({len(held_out_groups)} groups) -> {held_out_output}")

    # Assert cross-split group isolation
    leakage = dev_groups & held_out_groups
    assert not leakage, f"Leakage detected between splits: {leakage}"

    return dev_output, held_out_output


def main():
    parser = argparse.ArgumentParser(description="Dakota Financial Evidence Annotation Tool")
    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    # Status
    status_p = subparsers.add_parser("status", help="Display annotation progress")
    status_p.add_argument("--file", default=DEFAULT_DATASET_PATH, help="Dataset path")

    # Annotate
    annotate_p = subparsers.add_parser("annotate", help="Run interactive terminal annotation")
    annotate_p.add_argument("--reviewer", default="REV-VDISH", help="Reviewer ID code")
    annotate_p.add_argument("--file", default=DEFAULT_DATASET_PATH, help="Dataset path")
    annotate_p.add_argument("--no-resume", action="store_true", help="Start from record 1 instead of pending")

    # Export CSV
    export_p = subparsers.add_parser("export-csv", help="Export dataset to CSV")
    export_p.add_argument("--file", default=DEFAULT_DATASET_PATH, help="Dataset path")
    export_p.add_argument("--output", default=None, help="Output CSV path")

    # Import CSV
    import_p = subparsers.add_parser("import-csv", help="Import annotations from CSV")
    import_p.add_argument("--input", required=True, help="Input CSV path")
    import_p.add_argument("--file", default=DEFAULT_DATASET_PATH, help="Dataset path")

    # Export splits
    splits_p = subparsers.add_parser("export-splits", help="Partition completed annotations into dev/held-out")
    splits_p.add_argument("--file", default=DEFAULT_DATASET_PATH, help="Dataset path")
    splits_p.add_argument("--dev-output", default=None)
    splits_p.add_argument("--held-out-output", default=None)
    splits_p.add_argument("--dev-ratio", type=float, default=0.65)

    args = parser.parse_args()

    if args.command == "status":
        print_status(args.file)
    elif args.command == "annotate":
        run_interactive_annotation(
            reviewer_id=args.reviewer,
            filepath=args.file,
            resume=not args.no_resume,
        )
    elif args.command == "export-csv":
        export_to_csv(args.file, args.output)
    elif args.command == "import-csv":
        import_from_csv(args.input, args.file)
    elif args.command == "export-splits":
        export_splits(args.file, args.dev_output, args.held_out_output, args.dev_ratio)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
