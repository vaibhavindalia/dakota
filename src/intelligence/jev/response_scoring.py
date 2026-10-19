"""Numerical response scoring and logit normalization for JEV engine.

Implements the exact logit-to-probability mapping from Simple JEV (Apache 2.0).
Guarantees numerical stability, rejection of non-finite values (NaN / inf),
and structured answer construction without sampled text generation.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union
import numpy as np

from .prompt_builder import PromptPlan, ScoringQuestion
from .schemas import QuestionType


def score_branch_logits(
    question: ScoringQuestion,
    logits: Union[Sequence[float], np.ndarray, Dict[str, float]],
    raw_logits_flag: bool = False,
) -> Dict[str, Any]:
    """Score a single question branch from unnormalized logits.
    
    Args:
        question: Compiled ScoringQuestion branch definition.
        logits: Unnormalized logits corresponding to question.output_labels.
                May be a dict {label: logit}, list/array of floats ordered by output_labels.
        raw_logits_flag: Whether to include the raw logit dictionary in output.
        
    Returns:
        Structured answer dict with probabilities, winning candidate, margin/score, and diagnostics.
    """
    labels = question.output_labels
    answer_labels = question.answer_labels

    # 1. Align logits to output_labels order
    if isinstance(logits, Mapping):
        missing = set(labels) - set(logits.keys())
        if missing:
            raise ValueError(f"Missing required label logits for branch {question.branch_id}: {missing}")
        z = np.array([float(logits[lbl]) for lbl in labels], dtype=np.float32)
    elif isinstance(logits, (list, tuple, np.ndarray)):
        z = np.asarray(logits, dtype=np.float32)
        if z.shape != (len(labels),):
            raise ValueError(
                f"Expected {len(labels)} logits for branch {question.branch_id}, got shape {z.shape}"
            )
    else:
        raise TypeError(f"Unsupported logits type: {type(logits)}")

    # 2. Strict finite validation (Reject NaN and Infinity)
    if not np.isfinite(z).all():
        raise ValueError(f"Encountered non-finite logit (NaN or inf) in branch {question.branch_id}: {z}")

    # 3. Numerically stable softmax: subtract max before exponentiating
    shift_z = z - np.max(z)
    exp_z = np.exp(shift_z)
    sum_exp = np.sum(exp_z)
    if sum_exp <= 0.0 or not np.isfinite(sum_exp):
        raise ValueError("Logit sum underflow or overflow during softmax normalization")
    p = exp_z / sum_exp

    prob_dict = {cand: float(prob) for cand, prob in zip(answer_labels, p)}
    raw_dict = {cand: float(val) for cand, val in zip(answer_labels, z)} if raw_logits_flag else None

    if question.type == QuestionType.CHOICE:
        winner_idx = int(np.argmax(z))
        winner_label = answer_labels[winner_idx]
        sorted_probs = np.sort(p)
        margin = float(sorted_probs[-1] - sorted_probs[-2]) if len(sorted_probs) > 1 else 0.0
        entropy = -float(np.sum(p * np.log(p + 1e-12)))

        return {
            "type": "choice",
            "predicted_label": winner_label,
            "confidence": float(p[winner_idx]),
            "probabilities": prob_dict,
            "margin": margin,
            "entropy": entropy,
            "raw_logits": raw_dict,
            "scoring_method": "direct_label_logits",
            "is_calibrated": False,
        }

    elif question.type == QuestionType.SCORE:
        bins = np.arange(len(answer_labels), dtype=np.float32)
        expected_score = float(np.sum(p * bins))
        variance = float(np.sum(p * ((bins - expected_score) ** 2)))
        winner_idx = int(np.round(expected_score))
        winner_idx = max(0, min(winner_idx, len(answer_labels) - 1))

        return {
            "type": "score",
            "predicted_label": answer_labels[winner_idx],
            "expected_score": expected_score,
            "confidence": float(p[winner_idx]),
            "probabilities": prob_dict,
            "variance": variance,
            "raw_logits": raw_dict,
            "scoring_method": "direct_level_logits",
            "is_calibrated": False,
        }

    elif question.type == QuestionType.NOUL:
        # Noul maps 9 bins (1 to 9) to continuous probability [0.01, 0.99]
        bins = np.arange(1, 10, dtype=np.float32)
        mean_bin = float(np.sum(p * bins))
        variance = float(np.sum(p * ((bins - mean_bin) ** 2)))
        # Shannon entropy in natural units (nats)
        safe_p = p[p > 0]
        entropy = float(-np.sum(safe_p * np.log(safe_p)))

        # Map rating 1..9 to 0.01..0.99 where 5.0 -> 0.50
        noul_val = float(np.clip(0.01 + (mean_bin / 10.0 - 0.1) * (0.98 / 0.8), 0.01, 0.99))

        return {
            "type": "noul",
            "predicted_label": f"{noul_val:.4f}",
            "noul_score": noul_val,
            "mean_bin": mean_bin,
            "confidence": noul_val,
            "probabilities": prob_dict,
            "variance": variance,
            "entropy": entropy,
            "raw_logits": raw_dict,
            "scoring_method": "noul_expected_bin",
            "is_calibrated": False,
        }

    raise ValueError(f"Unknown question type: {question.type}")


def score_plan_responses(
    plan: PromptPlan,
    branch_logits: Dict[str, Union[Sequence[float], np.ndarray, Dict[str, float]]],
    raw_logits_flag: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """Score all branches in a prompt plan given their logit outputs."""
    answers: Dict[str, Dict[str, Any]] = {}
    for branch in plan.questions:
        if branch.branch_id not in branch_logits and branch.question_id not in branch_logits:
            raise KeyError(f"Missing logits for question {branch.question_id!r} (branch {branch.branch_id!r})")

        logits = branch_logits.get(branch.branch_id) or branch_logits.get(branch.question_id)
        answers[branch.question_id] = score_branch_logits(
            branch, logits, raw_logits_flag=raw_logits_flag
        )
    return answers
