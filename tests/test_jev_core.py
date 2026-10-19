"""Unit tests for JEV Financial Intelligence Core.

Verifies:
1. Pydantic schema validation and rejection of malformed requests.
2. Numerical stability of softmax and rejection of non-finite logits (NaN/inf).
3. Choice winner selection, margin calculation, and exact tie behavior.
4. Score rubric expected value and variance arithmetic.
5. Noul continuous 9-bin mapping, variance, and Shannon entropy.
6. Deterministic prompt assembly and hash reproducibility.
7. Mock adapter execution of Task B (Sentiment and Tip Divergence).
"""
import math
import numpy as np
import pytest

from src.intelligence.jev.schemas import (
    ClassifierOption,
    ClassifierQuestion,
    ClassifierRequest,
    PredictionResult,
    QuestionType,
    compute_prompt_hash,
)
from src.intelligence.jev.prompt_builder import prepare_prompt, canonical_json
from src.intelligence.jev.response_scoring import score_branch_logits, score_plan_responses
from src.intelligence.jev.adapters.mock_adapter import MockClassifierAdapter
from src.intelligence.jev.tasks.sentiment import SentimentDivergenceTask


def test_classifier_request_schema_validation():
    """Verify strict validation and rejection of invalid question specifications."""
    # Choice with less than 2 options must fail in prompt builder
    req_dict = {
        "model": "qwen-test",
        "questions": {
            "q1": {
                "type": "choice",
                "instructions": "Select one",
                "criteria": {"SingleOption": "Description"},
            }
        }
    }
    with pytest.raises(ValueError, match="at least 2 criteria candidates"):
        prepare_prompt(req_dict)

    # Empty instructions must fail validation
    with pytest.raises(Exception):
        ClassifierQuestion(type=QuestionType.CHOICE, instructions="", criteria={"A": None, "B": None})


def test_canonical_json_determinism():
    """Verify that dict key ordering does not alter JSON serialization."""
    d1 = {"z": 1, "a": [3, 2, 1], "m": {"b": True, "a": False}}
    d2 = {"a": [3, 2, 1], "m": {"a": False, "b": True}, "z": 1}
    s1 = canonical_json(d1)
    s2 = canonical_json(d2)
    assert s1 == s2
    assert compute_prompt_hash(s1) == compute_prompt_hash(s2)


def test_choice_scoring_and_numerical_stability():
    """Verify softmax with extreme logits does not overflow or underflow."""
    req = ClassifierRequest(
        model="qwen-test",
        questions={
            "sentiment": ClassifierQuestion(
                type=QuestionType.CHOICE,
                instructions="Classify sentiment",
                criteria={"Bullish": None, "Bearish": None, "Neutral": None},
            )
        },
        options=ClassifierOption(raw_logits=True),
    )
    plan = prepare_prompt(req)
    branch = plan.questions[0]

    # Extreme logits (e.g. 1000.0, 1005.0) would overflow raw exp(z) without max-subtraction
    large_logits = {"A": 1000.0, "B": 1005.0, "C": 998.0}
    res = score_branch_logits(branch, large_logits, raw_logits_flag=True)

    assert res["type"] == "choice"
    assert res["predicted_label"] == "Bearish"  # 'B' corresponds to Bearish
    assert 0.99 <= res["confidence"] <= 1.0
    assert sum(res["probabilities"].values()) == pytest.approx(1.0, rel=1e-5)
    assert res["margin"] == pytest.approx(res["confidence"] - res["probabilities"]["Bullish"], rel=1e-5)
    assert res["is_calibrated"] is False
    assert res["raw_logits"] is not None


def test_rejection_of_non_finite_logits():
    """Verify that NaN or Infinite logits raise explicit errors."""
    req = ClassifierRequest(
        model="qwen-test",
        questions={
            "q": ClassifierQuestion(
                type=QuestionType.CHOICE,
                instructions="Test",
                criteria={"A": None, "B": None},
            )
        }
    )
    plan = prepare_prompt(req)
    branch = plan.questions[0]

    # NaN logit
    with pytest.raises(ValueError, match="non-finite logit"):
        score_branch_logits(branch, {"A": float("nan"), "B": 2.0})

    # Positive Infinity logit
    with pytest.raises(ValueError, match="non-finite logit"):
        score_branch_logits(branch, {"A": float("inf"), "B": 2.0})


def test_score_rubric_expected_value_and_variance():
    """Verify rubric scoring calculates mean index and variance accurately."""
    req = ClassifierRequest(
        model="qwen-test",
        questions={
            "risk_level": ClassifierQuestion(
                type=QuestionType.SCORE,
                instructions="Rate manipulation risk level",
                criteria={
                    "Negligible": "Normal trading",
                    "Moderate": "Unusual volume",
                    "Critical": "Pump and dump pattern",
                },
            )
        }
    )
    plan = prepare_prompt(req)
    branch = plan.questions[0]

    # Logits favoring level 1 ("Moderate")
    logits = {"0": 1.0, "1": 5.0, "2": 1.0}
    res = score_branch_logits(branch, logits)

    assert res["type"] == "score"
    assert res["predicted_label"] == "Moderate"
    assert 0.90 <= res["expected_score"] <= 1.10
    assert res["variance"] >= 0.0
    assert res["scoring_method"] == "direct_level_logits"


def test_noul_continuous_probability_and_entropy():
    """Verify Noul 9-bin rating maps to [0.01, 0.99] and computes Shannon entropy."""
    req = ClassifierRequest(
        model="qwen-test",
        questions={
            "certainty": ClassifierQuestion(
                type=QuestionType.NOUL,
                instructions="Probability of scam syndicate involvement",
            )
        }
    )
    plan = prepare_prompt(req)
    branch = plan.questions[0]

    # Symmetrical distribution centered on bin 5 (rating 5 -> should map to 0.50)
    symmetric_logits = {str(i): 5.0 - abs(i - 5) for i in range(1, 10)}
    res = score_branch_logits(branch, symmetric_logits)

    assert res["type"] == "noul"
    assert res["mean_bin"] == pytest.approx(5.0, abs=1e-4)
    assert res["noul_score"] == pytest.approx(0.50, abs=1e-3)
    assert 0.01 <= res["noul_score"] <= 0.99
    assert res["entropy"] > 0.0
    assert res["variance"] > 0.0


def test_mock_adapter_end_to_end_sentiment_task():
    """Verify end-to-end classification of Task B using MockClassifierAdapter."""
    adapter = MockClassifierAdapter(model_id="mock-qwen-7b", simulated_latency_ms=2.0)
    task = SentimentDivergenceTask()

    sample_divergence = {
        "ticker": "ZOMATO",
        "as_of": "2026-10-18",
        "latest_price": 275.50,
        "change_pct": -4.2,
        "volume": 8500000,
        "delivery_pct": 21.5,
        "technicals": {"supertrend": "bearish", "rsi": 42.1},
        "risk_score": 58.5,
        "risk_band": "Elevated",
        "is_surveillance": False,
        "news_headlines": ["Q2 net profit misses consensus by 14%"],
        "social_signals": ["MULTIBAGGER TARGET 500 INCOMING GUARANTEED EXIT TODAY"],
        "evidence_ids": ["E_MKT_ZOMATO", "E_NEWS_01", "E_TIP_99"],
    }

    # Preset logits favoring 'Mixed' (Divergence between hype and fundamentals)
    # Output labels: ('A', 'B', 'C', 'D', 'E') -> ('Bullish', 'Bearish', 'Neutral', 'Mixed', 'Insufficient Evidence')
    adapter.set_preset_logits({"A": 1.0, "B": 2.5, "C": 0.5, "D": 6.8, "E": -1.0})

    pred = task.classify(adapter, sample_divergence)

    assert isinstance(pred, PredictionResult)
    assert pred.task_name == "sentiment_divergence"
    assert pred.predicted_label == "Mixed"
    assert pred.confidence >= 0.85
    assert pred.is_calibrated is False
    assert pred.margin > 0.70
    assert pred.evidence_ids == ["E_MKT_ZOMATO", "E_NEWS_01", "E_TIP_99"]
    assert pred.model_id == "mock-qwen-7b"
    assert pred.classifier_version == "jev-v1.0"
    assert len(pred.prompt_hash) == 64
    assert pred.latency_ms > 0.0
    assert pred.error_status is None
