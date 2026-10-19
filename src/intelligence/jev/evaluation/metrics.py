"""Evaluation metrics for financial classification models.

Computes Accuracy, Macro-F1, per-class Precision/Recall, Brier score,
Expected Calibration Error (ECE), Negative Log-Likelihood (NLL), and latency.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple
import numpy as np
from pydantic import BaseModel, Field


class PerClassMetric(BaseModel):
    precision: float
    recall: float
    f1: float
    support: int


class ClassificationMetrics(BaseModel):
    """Structured report of classification accuracy and calibration quality."""
    accuracy: float = Field(..., description="Fraction of correct classifications")
    macro_f1: float = Field(..., description="Unweighted average of F1 scores across all classes")
    weighted_f1: float = Field(..., description="Support-weighted average of F1 scores")
    brier_score: float = Field(..., description="Multi-class quadratic error (lower is better, range [0, 2])")
    ece: float = Field(..., description="Expected Calibration Error across confidence bins (lower is better)")
    nll: float = Field(..., description="Negative log-likelihood / cross-entropy loss (lower is better)")
    per_class: Dict[str, PerClassMetric] = Field(default_factory=dict)
    sample_count: int = Field(..., description="Total evaluated test samples")
    mean_latency_ms: float = Field(default=0.0, description="Average forward pass latency in ms")
    p95_latency_ms: float = Field(default=0.0, description="95th percentile latency in ms")
    tokens_generated_per_sample: float = Field(default=0.0, description="Average output tokens generated")


def compute_brier_score(y_true: Sequence[str], y_probs: Sequence[Dict[str, float]], classes: Sequence[str]) -> float:
    """Compute multi-class Brier score: (1/N) * sum_i sum_c (p_ic - y_ic)^2."""
    if not y_true:
        return 0.0
    
    total_sq_err = 0.0
    for true_lbl, prob_map in zip(y_true, y_probs):
        for c in classes:
            p_ic = prob_map.get(c, 0.0)
            y_ic = 1.0 if true_lbl == c else 0.0
            total_sq_err += (p_ic - y_ic) ** 2

    return float(total_sq_err / len(y_true))


def compute_ece(
    y_true: Sequence[str],
    y_preds: Sequence[str],
    y_confs: Sequence[float],
    n_bins: int = 10,
) -> float:
    """Compute Expected Calibration Error (ECE) partitioned into equal-width confidence bins."""
    if not y_true:
        return 0.0

    bins = np.linspace(0.0, 1.0, n_bins + 1)
    confs = np.array(y_confs, dtype=np.float32)
    corrects = np.array([1.0 if t == p else 0.0 for t, p in zip(y_true, y_preds)], dtype=np.float32)

    total_samples = len(y_true)
    ece = 0.0

    for i in range(n_bins):
        low, high = bins[i], bins[i + 1]
        mask = (confs > low) & (confs <= high) if i > 0 else (confs >= low) & (confs <= high)
        bin_count = np.sum(mask)

        if bin_count > 0:
            bin_acc = np.mean(corrects[mask])
            bin_conf = np.mean(confs[mask])
            ece += (bin_count / total_samples) * abs(bin_acc - bin_conf)

    return float(ece)


def compute_nll(y_true: Sequence[str], y_probs: Sequence[Dict[str, float]], eps: float = 1e-12) -> float:
    """Compute Negative Log-Likelihood (cross entropy) over true class probabilities."""
    if not y_true:
        return 0.0

    losses = []
    for true_lbl, prob_map in zip(y_true, y_probs):
        p_true = max(prob_map.get(true_lbl, 0.0), eps)
        losses.append(-math.log(p_true))

    return float(np.mean(losses))


def compute_all_metrics(
    y_true: Sequence[str],
    y_pred: Sequence[str],
    y_probs: Sequence[Dict[str, float]],
    y_confs: Sequence[float],
    classes: Sequence[str],
    latencies_ms: Optional[Sequence[float]] = None,
    tokens_generated: Optional[Sequence[int]] = None,
) -> ClassificationMetrics:
    """Evaluate predictions against ground truth labels across all standard statistical dimensions."""
    n = len(y_true)
    if n == 0:
        raise ValueError("Cannot compute metrics on empty prediction list")

    classes_list = list(classes)
    class_to_idx = {c: i for i, c in enumerate(classes_list)}

    # Accuracy
    correct = sum(1 for yt, yp in zip(y_true, y_pred) if yt == yp)
    accuracy = correct / n

    # Confusion matrix and per-class precision/recall
    tp = {c: 0 for c in classes_list}
    fp = {c: 0 for c in classes_list}
    fn = {c: 0 for c in classes_list}
    support = {c: 0 for c in classes_list}

    for yt, yp in zip(y_true, y_pred):
        if yt in support:
            support[yt] += 1
        if yt == yp:
            if yt in tp:
                tp[yt] += 1
        else:
            if yp in fp:
                fp[yp] += 1
            if yt in fn:
                fn[yt] += 1

    per_class = {}
    f1_list = []
    weighted_f1_sum = 0.0

    for c in classes_list:
        prec = tp[c] / (tp[c] + fp[c]) if (tp[c] + fp[c]) > 0 else 0.0
        rec = tp[c] / (tp[c] + fn[c]) if (tp[c] + fn[c]) > 0 else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
        supp = support[c]

        per_class[c] = PerClassMetric(
            precision=round(prec, 4),
            recall=round(rec, 4),
            f1=round(f1, 4),
            support=supp,
        )
        f1_list.append(f1)
        weighted_f1_sum += f1 * supp

    macro_f1 = float(np.mean(f1_list)) if f1_list else 0.0
    weighted_f1 = float(weighted_f1_sum / n) if n > 0 else 0.0

    # Calibration & Probability Loss
    brier = compute_brier_score(y_true, y_probs, classes_list)
    ece = compute_ece(y_true, y_pred, y_confs)
    nll = compute_nll(y_true, y_probs)

    # Latency
    mean_lat = float(np.mean(latencies_ms)) if latencies_ms else 0.0
    p95_lat = float(np.percentile(latencies_ms, 95)) if latencies_ms else 0.0
    tok_gen = float(np.mean(tokens_generated)) if tokens_generated else 0.0

    return ClassificationMetrics(
        accuracy=round(accuracy, 4),
        macro_f1=round(macro_f1, 4),
        weighted_f1=round(weighted_f1, 4),
        brier_score=round(brier, 4),
        ece=round(ece, 4),
        nll=round(nll, 4),
        per_class=per_class,
        sample_count=n,
        mean_latency_ms=round(mean_lat, 2),
        p95_latency_ms=round(p95_lat, 2),
        tokens_generated_per_sample=round(tok_gen, 2),
    )
