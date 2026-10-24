"""Comprehensive Evaluation Metrics & Diagnostic Calibration Engine (Phase 7).

Computes:
- Confusion matrix (TP, FP, TN, FN)
- Precision, Recall, Macro-F1, Balanced Accuracy
- ROC-AUC and PR-AUC (Precision-Recall AUC for imbalanced distributions)
- False Positive Rate (FPR) and False Negative Rate (FNR)
- Brier Score & Expected Calibration Error (ECE) across 10 confidence bins
- Wilson 95% Confidence Intervals
- Multi-threshold decision performance (0.30, 0.50, 0.70)
- Business risk consequences analysis.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Tuple
import numpy as np
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

logger = logging.getLogger(__name__)


def wilson_score_interval(p: float, n: int, z: float = 1.96) -> Tuple[float, float]:
    """Compute Wilson score 95% confidence interval for a proportion."""
    if n <= 0:
        return 0.0, 0.0
    denom = 1.0 + (z**2) / n
    center = (p + (z**2) / (2 * n)) / denom
    spread = (z * np.sqrt((p * (1 - p) / n) + (z**2) / (4 * n**2))) / denom
    lower = max(0.0, float(center - spread))
    upper = min(1.0, float(center + spread))
    return lower, upper


def compute_expected_calibration_error(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    n_bins: int = 10,
) -> float:
    """Compute Expected Calibration Error (ECE) using equal-width probability bins."""
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n = len(y_true)
    if n == 0:
        return 0.0

    for i in range(n_bins):
        low, high = bin_edges[i], bin_edges[i + 1]
        mask = (y_prob >= low) & (y_prob < high if i < n_bins - 1 else y_prob <= high)
        bin_count = np.sum(mask)
        if bin_count > 0:
            bin_acc = float(np.mean(y_true[mask]))
            bin_conf = float(np.mean(y_prob[mask]))
            ece += (bin_count / n) * abs(bin_acc - bin_conf)
    return float(ece)


@dataclass
class EvaluationReport:
    split_name: str
    total_samples: int
    positive_count: int
    negative_count: int
    accuracy: float
    accuracy_ci_95: Tuple[float, float]
    balanced_accuracy: float
    precision: float
    recall: float
    macro_f1: float
    roc_auc: float
    pr_auc: float
    brier_score: float
    expected_calibration_error: float
    false_positive_rate: float
    false_negative_rate: float
    confusion_matrix: Dict[str, int]
    threshold_metrics: Dict[str, Dict[str, float]]
    business_impact: Dict[str, str]
    operating_threshold: float = 0.50
    operating_metrics: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["accuracy_ci_95"] = list(self.accuracy_ci_95)
        return d


def evaluate_predictions(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    split_name: str = "test",
    default_threshold: float = 0.50,
    operating_threshold: Optional[float] = None,
) -> EvaluationReport:
    """Compute full evaluation suite on predictions with dual baseline and operating thresholds."""
    y_true = np.asarray(y_true).astype(int)
    y_prob = np.asarray(y_prob).astype(float)
    y_pred = (y_prob >= default_threshold).astype(int)
    n = len(y_true)

    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = int(cm[0, 0]), int(cm[0, 1]), int(cm[1, 0]), int(cm[1, 1])

    acc = float((tp + tn) / n) if n > 0 else 0.0
    ci_low, ci_high = wilson_score_interval(acc, n)
    bal_acc = float(balanced_accuracy_score(y_true, y_pred)) if len(np.unique(y_true)) > 1 else acc
    prec = float(precision_score(y_true, y_pred, zero_division=0))
    rec = float(recall_score(y_true, y_pred, zero_division=0))
    f1 = float(f1_score(y_true, y_pred, zero_division=0))

    try:
        roc_auc = float(roc_auc_score(y_true, y_prob)) if len(np.unique(y_true)) > 1 else 0.5
    except Exception:
        roc_auc = 0.5

    try:
        pr_auc = float(average_precision_score(y_true, y_prob)) if len(np.unique(y_true)) > 1 else 0.0
    except Exception:
        pr_auc = 0.0

    brier = float(brier_score_loss(y_true, y_prob))
    ece = compute_expected_calibration_error(y_true, y_prob, n_bins=10)

    fpr = float(fp / (fp + tn)) if (fp + tn) > 0 else 0.0
    fnr = float(fn / (fn + tp)) if (fn + tp) > 0 else 0.0

    # Decision thresholds evaluation (encompassing base-rate scaled multipliers and absolute cutoffs)
    threshold_metrics = {}
    candidate_thresholds = [0.005, 0.008, 0.010, 0.012, 0.015, 0.020, 0.050, 0.10, 0.20, 0.30, 0.40, 0.50]
    for th in candidate_thresholds:
        th_pred = (y_prob >= th).astype(int)
        th_prec = float(precision_score(y_true, th_pred, zero_division=0))
        th_rec = float(recall_score(y_true, th_pred, zero_division=0))
        th_f1 = float(f1_score(y_true, th_pred, zero_division=0))
        th_cm = confusion_matrix(y_true, th_pred, labels=[0, 1])
        th_fp = int(th_cm[0, 1])
        th_fn = int(th_cm[1, 0])
        th_tp = int(th_cm[1, 1])
        th_tn = int(th_cm[0, 0])
        threshold_metrics[f"{th:.3f}"] = {
            "precision": round(th_prec, 4),
            "recall": round(th_rec, 4),
            "f1": round(th_f1, 4),
            "true_positives": th_tp,
            "false_positives": th_fp,
            "false_negatives": th_fn,
            "true_negatives": th_tn,
        }

    # Evaluate operating threshold if provided
    op_th = operating_threshold if operating_threshold is not None else default_threshold
    op_pred = (y_prob >= op_th).astype(int)
    op_cm = confusion_matrix(y_true, op_pred, labels=[0, 1])
    op_metrics = {
        "operating_threshold": round(op_th, 4),
        "precision": round(float(precision_score(y_true, op_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, op_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, op_pred, zero_division=0)), 4),
        "balanced_accuracy": round(float(balanced_accuracy_score(y_true, op_pred)) if len(np.unique(y_true)) > 1 else float(np.mean(y_true == op_pred)), 4),
        "confusion_matrix": {
            "tn": int(op_cm[0, 0]),
            "fp": int(op_cm[0, 1]),
            "fn": int(op_cm[1, 0]),
            "tp": int(op_cm[1, 1]),
        },
    }

    business_impact = {
        "false_positive_risk": (
            f"FPR = {fpr*100:.2f}% ({fp} false alarms). Flagging legitimate Indian listed companies creates severe "
            "reputational harm, unwarranted panic among retail shareholders, and potential regulatory liability."
        ),
        "false_negative_risk": (
            f"FNR = {fnr*100:.2f}% ({fn} missed events). Failing to detect a syndicate pump-and-dump or circuit-locking ramp "
            "allows operator cartels to offload illiquid shares onto uninformed retail investors prior to regulatory action."
        ),
        "surveillance_recommendation": (
            f"At operating threshold {op_th:.2f}, the model achieves "
            f"{op_metrics['recall']*100:.1f}% recall and {op_metrics['precision']*100:.1f}% precision, "
            "optimizing surveillance analyst queue triage."
        ),
    }

    return EvaluationReport(
        split_name=split_name,
        total_samples=n,
        positive_count=int(np.sum(y_true)),
        negative_count=int(np.sum(y_true == 0)),
        accuracy=round(acc, 4),
        accuracy_ci_95=(round(ci_low, 4), round(ci_high, 4)),
        balanced_accuracy=round(bal_acc, 4),
        precision=round(prec, 4),
        recall=round(rec, 4),
        macro_f1=round(f1, 4),
        roc_auc=round(roc_auc, 4),
        pr_auc=round(pr_auc, 4),
        brier_score=round(brier, 4),
        expected_calibration_error=round(ece, 4),
        false_positive_rate=round(fpr, 4),
        false_negative_rate=round(fnr, 4),
        confusion_matrix={"tn": tn, "fp": fp, "fn": fn, "tp": tp},
        threshold_metrics=threshold_metrics,
        business_impact=business_impact,
        operating_threshold=op_th,
        operating_metrics=op_metrics,
    )
