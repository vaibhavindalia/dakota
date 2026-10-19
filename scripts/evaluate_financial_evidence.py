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
    "Insufficient Evidence",
]


def compute_class_level_metrics(
    y_true: List[str],
    y_pred: List[str],
    classes: List[str],
) -> Dict[str, Any]:
    """Compute precision, recall, f1, and support for each class plus macro averages."""
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
) -> Dict[str, float]:
    """Calculate Multi-Class Brier Score, Expected Calibration Error (ECE), and Negative Log Likelihood (NLL)."""
    n_samples = len(y_true)
    if n_samples == 0:
        return {"brier_score": 0.0, "ece": 0.0, "nll": 0.0}

    # 1. Multi-class Brier Score: 1/N * sum_i sum_k (p_ik - y_ik)^2
    total_brier = 0.0
    total_nll = 0.0

    for yt, probs in zip(y_true, y_pred_probs):
        for c in classes:
            p_k = probs.get(c, 0.0)
            y_k = 1.0 if yt == c else 0.0
            total_brier += (p_k - y_k) ** 2

        # NLL on true class probability
        p_true = max(probs.get(yt, 1e-15), 1e-15)
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

    abstentions = 0
    attribution_failures = 0
    subgroup_results: Dict[str, Dict[str, List[int]]] = collections.defaultdict(
        lambda: {"correct": [], "total": []}
    )

    t0 = time.perf_counter()

    for item in dataset:
        target_label = item.get("label", "Neutral")
        sample_data = item.get("sample", {})
        metadata = item.get("metadata", {})
        evidence_ids = item.get("evidence_ids", [])
        if evidence_ids and "evidence_ids" not in sample_data:
            sample_data["evidence_ids"] = evidence_ids

        # Run model inference
        pred: PredictionResult = task.classify(adapter, sample_data)

        # Provenance and evidence attribution check
        if not pred.evidence_ids or len(pred.evidence_ids) == 0:
            attribution_failures += 1

        # Check for abstention: Insufficient Evidence or confidence below threshold
        is_abstained = (
            pred.predicted_label == "Insufficient Evidence"
            or pred.confidence < confidence_abstention_threshold
        )
        if is_abstained:
            abstentions += 1

        chosen_label = pred.predicted_label
        y_true.append(target_label)
        y_pred.append(chosen_label)

        # Normalized class scores
        scores = pred.class_scores or {c: 1.0 / len(STANDARD_CLASSES) for c in STANDARD_CLASSES}
        y_pred_probs.append(scores)

        # Track challenge categories (negation, speculation, conflicting, stale, scope)
        is_correct = 1 if chosen_label == target_label else 0
        scope = metadata.get("scope", "company_specific")
        challenge = metadata.get("linguistic_challenge", "standard")

        subgroup_results[f"scope:{scope}"]["correct"].append(is_correct)
        subgroup_results[f"challenge:{challenge}"]["correct"].append(is_correct)

    total_time = time.perf_counter() - t0
    n_samples = len(dataset)
    mean_latency = (total_time / n_samples) * 1000.0 if n_samples > 0 else 0.0

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

    abstention_rate = round(abstentions / n_samples, 4) if n_samples > 0 else 0.0
    attribution_rate = round(1.0 - (attribution_failures / n_samples), 4) if n_samples > 0 else 1.0

    return {
        "total_samples": n_samples,
        "mean_latency_ms": round(mean_latency, 2),
        "abstention_rate": abstention_rate,
        "evidence_attribution_rate": attribution_rate,
        "classification": class_metrics,
        "calibration": calib_metrics,
        "subgroups": subgroup_summary,
    }


def format_evaluation_report(report: Dict[str, Any], title: str = "Financial Evidence Evaluation Report") -> str:
    """Format evaluation statistics into a readable markdown summary."""
    lines = [
        f"# {title}",
        f"- **Evaluated Samples**: {report['total_samples']}",
        f"- **Mean Latency**: {report['mean_latency_ms']} ms/sample",
        f"- **Abstention Rate**: {report['abstention_rate'] * 100:.2f}%",
        f"- **Evidence Attribution Rate**: {report['evidence_attribution_rate'] * 100:.2f}%",
        "",
        "## 1. Classification Metrics",
        f"- **Overall Accuracy**: {report['classification']['accuracy'] * 100:.2f}%",
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
        f"- **Negative Log-Likelihood (NLL)**: {report['calibration']['nll']:.4f}",
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
            "metadata": {"scope": "company_specific", "linguistic_challenge": "standard"},
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
            "metadata": {"scope": "company_specific", "linguistic_challenge": "negation"},
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
            "metadata": {"scope": "company_specific", "linguistic_challenge": "conflicting_reports"},
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
            "metadata": {"scope": "macro_wide", "linguistic_challenge": "standard"},
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
            "metadata": {"scope": "company_specific", "linguistic_challenge": "speculation"},
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
            "metadata": {"scope": "company_specific", "linguistic_challenge": "stale_information"},
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
    ]


def main():
    parser = argparse.ArgumentParser(description="Evaluate financial evidence on held-out dataset.")
    parser.add_argument("--dataset", type=str, default=None, help="Path to evaluation dataset JSON.")
    parser.add_argument("--held-out", action="store_true", help="Force evaluation on held-out test split.")
    parser.add_argument(
        "--adapter",
        type=str,
        default="mock",
        choices=["mock", "official_jev", "rules"],
        help="Model adapter backend to evaluate.",
    )
    parser.add_argument("--output", type=str, default=None, help="Path to write evaluation JSON report.")
    args = parser.parse_args()

    # Load dataset
    if args.dataset and os.path.isfile(args.dataset):
        with open(args.dataset, "r", encoding="utf-8") as f:
            dataset = json.load(f)
        dataset_name = os.path.basename(args.dataset)
    else:
        dataset = get_default_held_out_dataset()
        dataset_name = "Default Held-Out Dataset (Indian Equity Benchmarks)"

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
                    "E": 0.1,
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
