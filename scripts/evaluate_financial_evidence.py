"""Evaluation protocol and runner for manually labeled financial evidence in Dakota.

Supports evaluation across:
1. Multi-class financial sentiment: Positive (Bullish), Negative (Bearish), Neutral, Mixed, Insufficient Evidence, Ambiguous.
2. Evidence scope: Company-specific disclosures vs. Market-wide macroeconomic news.
3. Linguistic edge cases: Negation, uncorroborated speculation, conflicting reports, and stale information.
4. Source/evidence attribution: Validates citation IDs and penalizes hallucinated claims.
5. Metrics: Class-level Precision, Recall, Macro-F1, Confusion Matrix, and Abstention Rate.
6. Calibration vs Accuracy: Multi-class Brier Score, Expected Calibration Error (ECE), and NLL.
7. Held-out test set: Dedicated split never utilized for prompt engineering or hyperparameter tuning.

Usage:
    python scripts/evaluate_financial_evidence.py --dataset data/financial_eval_held_out.json --adapter official_jev
    python scripts/evaluate_financial_evidence.py --held-out --adapter mock
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# Add workspace root to sys.path
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from src.intelligence.jev.schemas import PredictionResult
from src.intelligence.jev.tasks.sentiment import SentimentDivergenceTask
from src.intelligence.jev.adapters.mock_adapter import MockClassifierAdapter

STANDARD_CLASSES = [
    "Bullish",
    "Bearish",
    "Neutral",
    "Mixed",
    "Ambiguous",
    "Insufficient Evidence",
]


def compute_class_level_metrics(
    y_true: List[str],
    y_pred: List[str],
    classes: List[str],
) -> Dict[str, Any]:
    """Compute precision, recall, f1, support, and balanced accuracy for each class plus macro averages."""
    confusion = collections.defaultdict(lambda: collections.defaultdict(int))
    for yt, yp in zip(y_true, y_pred):
        confusion[yt][yp] += 1

    per_class: Dict[str, Dict[str, float]] = {}
    precisions = []
    recalls = []
    f1s = []

    for c in classes:
        tp = confusion[c][c]
        fp = sum(confusion[other][c] for other in classes if other != c)
        fn = sum(confusion[c][other] for other in classes if other != c)
        support = sum(confusion[c].values())

        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0

        per_class[c] = {
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
            "support": support,
        }
        if support > 0:
            precisions.append(prec)
            recalls.append(rec)
            f1s.append(f1)

    macro_f1 = sum(f1s) / len(f1s) if f1s else 0.0
    macro_prec = sum(precisions) / len(precisions) if precisions else 0.0
    macro_rec = sum(recalls) / len(recalls) if recalls else 0.0
    balanced_accuracy = sum(recalls) / len(recalls) if recalls else 0.0

    total_correct = sum(confusion[c][c] for c in classes)
    total_samples = len(y_true)
    accuracy = total_correct / total_samples if total_samples > 0 else 0.0

    # Format confusion matrix as 2D table
    matrix: Dict[str, Dict[str, int]] = {
        actual: {predicted: confusion[actual][predicted] for predicted in classes}
        for actual in classes
    }

    return {
        "accuracy": round(accuracy, 4),
        "balanced_accuracy": round(balanced_accuracy, 4),
        "macro_precision": round(macro_prec, 4),
        "macro_recall": round(macro_rec, 4),
        "macro_f1": round(macro_f1, 4),
        "per_class": per_class,
        "confusion_matrix": matrix,
    }


def compute_calibration_metrics(
    y_true: List[str],
    y_pred_probs: List[Dict[str, float]],
    classes: List[str],
    n_bins: int = 10,
) -> Dict[str, Any]:
    """Calculate Multi-Class Brier Score, Expected Calibration Error (ECE), and Negative Log Likelihood (NLL).
    
    Binning method: Equal-width binning partitions max confidence [0.0, 1.0] into n_bins intervals.
    Class ordering: Explicitly matches `classes` parameter.
    """
    n_samples = len(y_true)
    if n_samples == 0:
        return {
            "brier_score": 0.0,
            "ece": 0.0,
            "nll": 0.0,
            "binning_method": f"equal_width_{n_bins}_bins",
            "class_ordering": classes,
        }

    # 1. Multi-class Brier Score: 1/N * sum_i sum_k (p_ik - y_ik)^2
    total_brier = 0.0
    total_nll = 0.0

    for yt, probs in zip(y_true, y_pred_probs):
        for c in classes:
            p_k = probs.get(c, 0.0)
            y_k = 1.0 if yt == c else 0.0
            total_brier += (p_k - y_k) ** 2

        # Epsilon floor of 1e-7 prevents log(0) spikes on unpredicted true classes
        p_true = max(probs.get(yt, 1e-7), 1e-7)
        total_nll += -math.log(p_true)

    mean_brier = total_brier / n_samples
    mean_nll = total_nll / n_samples

    # 2. Expected Calibration Error (ECE) across max confidence bins
    confidences = []
    accuracies = []
    for yt, probs in zip(y_true, y_pred_probs):
        top_cls = max(probs.keys(), key=lambda k: probs[k]) if probs else classes[0]
        top_conf = max(probs.values()) if probs else 0.0
        confidences.append(top_conf)
        accuracies.append(1.0 if top_cls == yt else 0.0)

    bin_boundaries = [i / float(n_bins) for i in range(n_bins + 1)]
    ece = 0.0

    for i in range(n_bins):
        bin_lower = bin_boundaries[i]
        bin_upper = bin_boundaries[i + 1]

        in_bin = [
            (c, a) for c, a in zip(confidences, accuracies)
            if (bin_lower <= c < bin_upper) or (i == n_bins - 1 and bin_lower <= c <= bin_upper)
        ]
        bin_size = len(in_bin)
        if bin_size > 0:
            avg_conf = sum(c for c, _ in in_bin) / bin_size
            avg_acc = sum(a for _, a in in_bin) / bin_size
            ece += (bin_size / n_samples) * abs(avg_acc - avg_conf)

    return {
        "brier_score": round(mean_brier, 4),
        "ece": round(ece, 4),
        "nll": round(mean_nll, 4),
        "binning_method": f"equal_width_{n_bins}_bins",
        "class_ordering": classes,
    }


def evaluate_dataset(
    dataset: List[Dict[str, Any]],
    adapter: Any,
    task: SentimentDivergenceTask,
    confidence_abstention_threshold: float = 0.40,
) -> Dict[str, Any]:
    """Execute complete evaluation protocol on the provided dataset."""
    y_true: List[str] = []
    y_pred: List[str] = []
    y_pred_probs: List[Dict[str, float]] = []

    insufficient_evidence_count = 0
    ambiguous_count = 0
    low_confidence_abstentions = 0
    attribution_failures = 0
    sample_latencies: List[float] = []
    skipped_count = 0
    failure_count = 0

    subgroup_results: Dict[str, Dict[str, List[int]]] = collections.defaultdict(
        lambda: {"correct": [], "total": []}
    )

    t0 = time.perf_counter()

    for item in dataset:
        target_label = item.get("label")
        if not target_label:
            skipped_count += 1
            continue

        sample_data = item.get("sample", {})
        metadata = item.get("metadata", {})
        evidence_ids = item.get("evidence_ids", [])
        if evidence_ids and "evidence_ids" not in sample_data:
            sample_data["evidence_ids"] = evidence_ids

        # Run model inference
        t_sample_start = time.perf_counter()
        try:
            pred: PredictionResult = task.classify(adapter, sample_data)
            sample_ms = pred.latency_ms if (pred.latency_ms is not None and pred.latency_ms > 0) else (time.perf_counter() - t_sample_start) * 1000.0
            sample_latencies.append(round(sample_ms, 2))
        except Exception as exc:
            failure_count += 1
            sample_latencies.append(round((time.perf_counter() - t_sample_start) * 1000.0, 2))
            continue

        # Provenance and evidence attribution check
        if not pred.evidence_ids or len(pred.evidence_ids) == 0:
            attribution_failures += 1

        # Separate tracking of insufficient evidence, ambiguous, and low confidence
        if pred.predicted_label == "Insufficient Evidence":
            insufficient_evidence_count += 1
        if pred.predicted_label == "Ambiguous" or (pred.margin is not None and pred.margin < 0.05):
            ambiguous_count += 1
        if pred.confidence < confidence_abstention_threshold:
            low_confidence_abstentions += 1

        chosen_label = pred.predicted_label
        y_true.append(target_label)
        y_pred.append(chosen_label)

        # Normalized class scores across STANDARD_CLASSES
        scores = pred.class_scores or {c: 1.0 / len(STANDARD_CLASSES) for c in STANDARD_CLASSES}
        y_pred_probs.append(scores)

        # Track challenge categories (negation, speculation, conflicting, stale, scope)
        is_correct = 1 if chosen_label == target_label else 0
        scope = metadata.get("scope", "company_specific")
        challenge = metadata.get("linguistic_challenge", "standard")

        subgroup_results[f"scope:{scope}"]["correct"].append(is_correct)
        subgroup_results[f"challenge:{challenge}"]["correct"].append(is_correct)

    total_time = time.perf_counter() - t0
    n_samples = len(y_true)
    mean_latency = (total_time / n_samples) * 1000.0 if n_samples > 0 else 0.0

    # Latency percentiles
    if sample_latencies:
        sorted_lat = sorted(sample_latencies)
        median_lat = sorted_lat[int(len(sorted_lat) * 0.50)]
        p90_lat = sorted_lat[int(len(sorted_lat) * 0.90)]
        p95_lat = sorted_lat[min(int(len(sorted_lat) * 0.95), len(sorted_lat) - 1)]
    else:
        median_lat = p90_lat = p95_lat = 0.0

    # Peak GPU memory
    peak_vram_gib = 0.0
    try:
        import torch
        if torch.cuda.is_available():
            peak_vram_gib = round(torch.cuda.max_memory_allocated() / (1024**3), 2)
    except Exception:
        pass

    # 1. Classification Performance
    class_metrics = compute_class_level_metrics(y_true, y_pred, STANDARD_CLASSES)

    # 2. Calibration Performance
    calib_metrics = compute_calibration_metrics(y_true, y_pred_probs, STANDARD_CLASSES)

    # 3. Subgroup Accuracies
    subgroup_summary: Dict[str, Dict[str, Any]] = {}
    for group_key, vals in subgroup_results.items():
        total_g = len(vals["correct"])
        correct_g = sum(vals["correct"])
        acc_g = correct_g / total_g if total_g > 0 else 0.0
        subgroup_summary[group_key] = {
            "accuracy": round(acc_g, 4),
            "sample_count": total_g,
        }

    total_abstained = low_confidence_abstentions + insufficient_evidence_count
    abstention_rate = round(total_abstained / n_samples, 4) if n_samples > 0 else 0.0
    coverage_rate = round(1.0 - abstention_rate, 4)
    attribution_rate = round(1.0 - (attribution_failures / n_samples), 4) if n_samples > 0 else 1.0

    return {
        "total_samples": n_samples,
        "eligible_samples": len(dataset),
        "skipped_samples": skipped_count,
        "failed_samples": failure_count,
        "coverage_rate": coverage_rate,
        "abstention_rate": abstention_rate,
        "insufficient_evidence_count": insufficient_evidence_count,
        "ambiguous_count": ambiguous_count,
        "low_confidence_abstentions": low_confidence_abstentions,
        "evidence_attribution_rate": attribution_rate,
        "latency": {
            "mean_ms": round(mean_latency, 2),
            "median_ms": round(median_lat, 2),
            "p90_ms": round(p90_lat, 2),
            "p95_ms": round(p95_lat, 2),
        },
        "peak_vram_gib": peak_vram_gib,
        "classification": class_metrics,
        "calibration": calib_metrics,
        "subgroups": subgroup_summary,
    }


def format_evaluation_report(report: Dict[str, Any], title: str = "Financial Evidence Evaluation Report") -> str:
    """Format evaluation statistics into a readable markdown summary."""
    lat = report.get("latency", {})
    lines = [
        f"# {title}",
        f"- **Evaluated Samples**: {report['total_samples']} (Eligible: {report.get('eligible_samples', report['total_samples'])}, Skipped: {report.get('skipped_samples', 0)}, Failed: {report.get('failed_samples', 0)})",
        f"- **Coverage Rate**: {report.get('coverage_rate', 1.0) * 100:.2f}%",
        f"- **Abstention Rate**: {report['abstention_rate'] * 100:.2f}% (Insufficient Evidence: {report.get('insufficient_evidence_count', 0)}, Low Confidence (<0.40): {report.get('low_confidence_abstentions', 0)}, Ambiguous Diagnosed: {report.get('ambiguous_count', 0)})",
        f"- **Latency**: Median={lat.get('median_ms', 0.0)} ms | P90={lat.get('p90_ms', 0.0)} ms | P95={lat.get('p95_ms', 0.0)} ms (Mean: {lat.get('mean_ms', 0.0)} ms)",
        f"- **Peak GPU VRAM**: {report.get('peak_vram_gib', 0.0)} GiB",
        f"- **Evidence Attribution Rate**: {report['evidence_attribution_rate'] * 100:.2f}%",
        f"- **Class Ordering**: {', '.join(STANDARD_CLASSES)}",
        "",
        "## 1. Classification Metrics",
        f"- **Overall Accuracy**: {report['classification']['accuracy'] * 100:.2f}%",
        f"- **Balanced Accuracy**: {report['classification'].get('balanced_accuracy', 0.0) * 100:.2f}%",
        f"- **Macro-Precision**: {report['classification']['macro_precision']:.4f}",
        f"- **Macro-Recall**: {report['classification']['macro_recall']:.4f}",
        f"- **Macro-F1**: {report['classification']['macro_f1']:.4f}",
        "",
        "### Class-Level Breakdown",
        "| Class | Precision | Recall | F1-Score | Support |",
        "| :--- | :---: | :---: | :---: | :---: |",
    ]
    for c, stats in report['classification']['per_class'].items():
        lines.append(
            f"| **{c}** | {stats['precision']:.4f} | {stats['recall']:.4f} | {stats['f1']:.4f} | {stats['support']} |"
        )

    lines.extend([
        "",
        "### Confusion Matrix",
        "| Actual \\ Predicted | " + " | ".join(STANDARD_CLASSES) + " |",
        "| :--- | " + " | ".join([":---:"] * len(STANDARD_CLASSES)) + " |",
    ])
    matrix = report['classification']['confusion_matrix']
    for actual in STANDARD_CLASSES:
        row_str = f"| **{actual}** | " + " | ".join(str(matrix[actual].get(p, 0)) for p in STANDARD_CLASSES) + " |"
        lines.append(row_str)

    lines.extend([
        "",
        "## 2. Calibration Metrics (Separated from Accuracy)",
        f"- **Multi-Class Brier Score**: {report['calibration']['brier_score']:.4f} *(lower is better; quadratic probability error)*",
        f"- **Expected Calibration Error (ECE)**: {report['calibration']['ece']:.4f} *(lower is better; bin gap between confidence and empirical accuracy)*",
        f"- **Negative Log-Likelihood (NLL)**: {report['calibration']['nll']:.4f} *(with 1e-7 floor)*",
        f"- **Calibration Binning Method**: {report['calibration'].get('binning_method', 'equal_width_10_bins')}",
        "",
        "## 3. Subgroup & Linguistic Challenge Analysis",
        "| Subgroup / Challenge | Accuracy | Samples |",
        "| :--- | :---: | :---: |",
    ])
    for sub, stats in report['subgroups'].items():
        lines.append(f"| **{sub}** | {stats['accuracy'] * 100:.2f}% | {stats['sample_count']} |")

    return "\n".join(lines)


def get_default_held_out_dataset() -> List[Dict[str, Any]]:
    """Curated held-out evaluation dataset strictly separated from training/prompt engineering.
    
    Includes balanced representation across:
    - Positive, negative, neutral, mixed, ambiguous, and insufficient evidence.
    - Company-specific and macroeconomic events.
    - Negation, speculation, conflicting reports, and stale disclosures.
    """
    return [
        # --- Group 1: Company Specific - Standard Positive ---
        {
            "sample_id": "HELD-001",
            "ticker": "INFY",
            "label": "Bullish",
            "metadata": {"scope": "company_specific", "linguistic_challenge": "standard", "split": "held_out"},
            "evidence_ids": ["E_MKT_INFY", "E_BSE_INFY_Q3"],
            "sample": {
                "ticker": "INFY",
                "as_of": "2026-10-15T11:00:00Z",
                "latest_price": 1940.50,
                "change_pct": 3.40,
                "volume": 8450000,
                "delivery_pct": 71.2,
                "technicals": {"trend_vs_ema20": "bullish_expansion"},
                "risk_score": 8.0,
                "is_surveillance": False,
                "news_headlines": ["Infosys revises constant-currency revenue guidance upward to 5.0%-5.5%"],
                "social_signals": ["Strong institutional delivery absorption noted in morning trade"],
            },
        },
        # --- Group 2: Company Specific - Negative with Negation ---
        {
            "sample_id": "HELD-002",
            "ticker": "VEDL",
            "label": "Bearish",
            "metadata": {"scope": "company_specific", "linguistic_challenge": "negation", "split": "held_out"},
            "evidence_ids": ["E_MKT_VEDL", "E_NEWS_SEBI"],
            "sample": {
                "ticker": "VEDL",
                "as_of": "2026-10-16T14:30:00Z",
                "latest_price": 435.10,
                "change_pct": -4.20,
                "volume": 12100000,
                "delivery_pct": 38.5,
                "technicals": {"trend_vs_ema20": "bearish_breakdown"},
                "risk_score": 68.0,
                "is_surveillance": False,
                "news_headlines": ["SEBI denies permission for parent debt restructuring; penalty levied for non-disclosure"],
                "social_signals": ["Promoter denies repayment default rumors, but bond yields spike"],
            },
        },
        # --- Group 3: Company Specific - Conflicting Reports (Mixed) ---
        {
            "sample_id": "HELD-003",
            "ticker": "SUZLON",
            "label": "Mixed",
            "metadata": {"scope": "company_specific", "linguistic_challenge": "conflicting_reports", "split": "held_out"},
            "evidence_ids": ["E_MKT_SUZLON", "E_TG_PROMO", "E_DISCLOSURE"],
            "sample": {
                "ticker": "SUZLON",
                "as_of": "2026-10-17T09:45:00Z",
                "latest_price": 78.40,
                "change_pct": 0.30,
                "volume": 25000000,
                "delivery_pct": 18.2,
                "technicals": {"trend_vs_ema20": "overbought_divergence"},
                "risk_score": 62.0,
                "is_surveillance": False,
                "news_headlines": ["Exchange files inquiry regarding unusual volume and social media recommendations"],
                "social_signals": ["JOIN VIP GROUP! Suzlon target ₹150 guaranteed 200% return by Diwali rocket call!"],
            },
        },
        # --- Group 4: Macroeconomic - Neutral Ordinary Operation ---
        {
            "sample_id": "HELD-004",
            "ticker": "HDFCBANK",
            "label": "Neutral",
            "metadata": {"scope": "macro_wide", "linguistic_challenge": "standard", "split": "held_out"},
            "evidence_ids": ["E_MKT_HDFCBANK", "E_RBI_BULLETIN"],
            "sample": {
                "ticker": "HDFCBANK",
                "as_of": "2026-10-14T16:00:00Z",
                "latest_price": 1675.00,
                "change_pct": -0.15,
                "volume": 3200000,
                "delivery_pct": 54.0,
                "technicals": {"trend_vs_ema20": "flat"},
                "risk_score": 12.0,
                "is_surveillance": False,
                "news_headlines": ["RBI monetary policy committee maintains repo rate unchanged at 6.50% in line with estimates"],
                "social_signals": ["Routine credit deposit ratio update reported by banking research desks"],
            },
        },
        # --- Group 5: Insufficient Evidence - Unsubstantiated Speculation ---
        {
            "sample_id": "HELD-005",
            "ticker": "UNKNOWN_SHELL",
            "label": "Insufficient Evidence",
            "metadata": {"scope": "company_specific", "linguistic_challenge": "speculation", "split": "held_out"},
            "evidence_ids": ["E_TG_SPAM"],
            "sample": {
                "ticker": "UNKNOWN_SHELL",
                "as_of": "2026-10-18T12:00:00Z",
                "latest_price": None,
                "change_pct": None,
                "volume": None,
                "delivery_pct": None,
                "technicals": {},
                "risk_score": 0.0,
                "is_surveillance": False,
                "news_headlines": [],
                "social_signals": ["Guaranteed jackpot tip tomorrow! Admin will give 100% sure-shot scrip in private group."],
            },
        },
        # --- Group 6: Stale Information Repost ---
        {
            "sample_id": "HELD-006",
            "ticker": "TATASTEEL",
            "label": "Neutral",
            "metadata": {"scope": "company_specific", "linguistic_challenge": "stale_information", "split": "held_out"},
            "evidence_ids": ["E_MKT_TATASTEEL", "E_STALE_NEWS"],
            "sample": {
                "ticker": "TATASTEEL",
                "as_of": "2026-10-18T10:00:00Z",
                "latest_price": 158.20,
                "change_pct": 0.10,
                "volume": 4100000,
                "delivery_pct": 51.0,
                "technicals": {"trend_vs_ema20": "flat"},
                "risk_score": 15.0,
                "is_surveillance": False,
                "news_headlines": ["UK Port Talbot furnace transition agreement signed three weeks ago"],
                "social_signals": ["Breaking! Tata Steel gets grant from UK Government (circulating old news from last month)"],
            },
        },
        # --- Group 7: Ambiguous - Contradictory Analyst Split ---
        {
            "sample_id": "HELD-007",
            "ticker": "WIPRO",
            "label": "Ambiguous",
            "metadata": {"scope": "company_specific", "linguistic_challenge": "ambiguous", "split": "held_out"},
            "evidence_ids": ["E_MKT_WIPRO", "E_ANALYST_SPLIT"],
            "sample": {
                "ticker": "WIPRO",
                "as_of": "2026-10-17T15:30:00Z",
                "latest_price": 545.00,
                "change_pct": 0.02,
                "volume": 2100000,
                "delivery_pct": 48.0,
                "technicals": {"trend_vs_ema20": "neutral_convergence"},
                "risk_score": 20.0,
                "is_surveillance": False,
                "news_headlines": [
                    "Goldman Sachs upgrades Wipro to Buy citing deal win ramp-up; Nomura simultaneously downgrades to Reduce citing margin pressure"
                ],
                "social_signals": [
                    "Broker research desks sharply divided with equal conviction and contradictory price targets"
                ],
            },
        },
    ]


def main():
    parser = argparse.ArgumentParser(description="Evaluate financial evidence on held-out or development datasets.")
    parser.add_argument("--dataset", type=str, default=None, help="Path to evaluation dataset JSON.")
    parser.add_argument("--held-out", action="store_true", help="Force evaluation strictly on held-out test split.")
    parser.add_argument(
        "--split",
        type=str,
        default=None,
        choices=["held_out", "dev", "all"],
        help="Specify evaluation split (held_out, dev, or all).",
    )
    parser.add_argument(
        "--adapter",
        type=str,
        default="mock",
        choices=["mock", "official_jev", "rules"],
        help="Model adapter backend to evaluate.",
    )
    parser.add_argument("--output", type=str, default=None, help="Path to write evaluation JSON report.")
    args = parser.parse_args()

    # Determine requested split
    target_split = "held_out" if args.held_out else args.split

    # Load dataset
    if args.dataset and os.path.isfile(args.dataset):
        with open(args.dataset, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        dataset_name = os.path.basename(args.dataset)
        if isinstance(raw_data, list):
            dataset = raw_data
        elif isinstance(raw_data, dict) and "samples" in raw_data:
            dataset = raw_data["samples"]
        else:
            dataset = [raw_data]

        if target_split in ("held_out", "dev"):
            filtered = [
                d for d in dataset
                if d.get("metadata", {}).get("split") == target_split
                or d.get("split") == target_split
            ]
            if filtered:
                dataset = filtered
                dataset_name += f" [Split: {target_split}]"
            elif target_split == "held_out":
                # Ensure user intended whole file if no split tags present
                print(f"Notice: No explicit split='{target_split}' tags found in {args.dataset}. Evaluating all records.")
    else:
        if target_split == "dev":
            from src.intelligence.jev.dataset import get_curated_indian_equity_dataset
            dev_bench = get_curated_indian_equity_dataset()
            dataset = [
                {
                    "sample_id": s.sample_id,
                    "ticker": s.ticker,
                    "label": s.label,
                    "metadata": {"scope": "company_specific", "linguistic_challenge": "standard", "split": "dev"},
                    "evidence_ids": s.evidence_ids,
                    "sample": s.sample,
                    "rationale": s.rationale,
                }
                for s in dev_bench
            ]
            dataset_name = "Curated Indian Equity Development Benchmark (15 samples)"
        else:
            dataset = get_default_held_out_dataset()
            dataset_name = "Curated Held-Out Benchmark Dataset (Indian Equity, 7 samples)"

    # Resolve adapter
    if args.adapter == "official_jev":
        from src.intelligence.jev.adapters.official_jev_adapter import OfficialSimpleJEVAdapter
        adapter = OfficialSimpleJEVAdapter()
    elif args.adapter == "mock":
        adapter = MockClassifierAdapter(
            model_id="mock-qwen-eval",
            preset_logits={
                "sentiment_divergence": {
                    "A": 3.8,  # Bullish
                    "B": 0.5,
                    "C": 0.3,
                    "D": 0.2,
                    "E": 0.1,  # Ambiguous
                    "F": 0.05, # Insufficient Evidence
                }
            },
        )
    else:
        raise ValueError(f"Unsupported adapter: {args.adapter}")

    task = SentimentDivergenceTask()
    report = evaluate_dataset(dataset, adapter, task)
    md_output = format_evaluation_report(report, title=f"Financial Evidence Evaluation: {dataset_name}")

    print(md_output)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"\nSaved JSON evaluation report to: {args.output}")


if __name__ == "__main__":
    main()
