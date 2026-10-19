"""JEV-backed message classifier for Dakota with feature flag and safe fallback.

Integrates the official Simple JEV + Qwen3.5-9B 4-bit adapter into Dakota's
market classification pipeline.

Feature Flag:
    DAKOTA_USE_JEV=1 (or 'true', 'yes') -> Routes message through JEV.
    Default: DAKOTA_USE_JEV=0 -> Retains 100% existing local rule/ML classification.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

FEATURE_FLAG_ENV_VAR = "DAKOTA_USE_JEV"


def is_jev_enabled() -> bool:
    """Return True if JEV is enabled (default: True, disabled via DAKOTA_USE_JEV=0 or DAKOTA_USE_MOCK=1)."""
    if os.environ.get("DAKOTA_USE_MOCK", "0").strip().lower() in ("1", "true", "yes", "on"):
        return False
    val = os.environ.get(FEATURE_FLAG_ENV_VAR, "1").strip().lower()
    return val not in ("0", "false", "no", "off")


# Global singleton adapter for Dakota pipeline classification
_CLASSIFICATION_ADAPTER = None


def get_pipeline_jev_adapter():
    """Retrieve or initialize the singleton JEV adapter for pipeline classification."""
    global _CLASSIFICATION_ADAPTER
    if _CLASSIFICATION_ADAPTER is None:
        try:
            from src.intelligence.jev.adapters.official_jev_adapter import OfficialSimpleJEVAdapter
            _CLASSIFICATION_ADAPTER = OfficialSimpleJEVAdapter(
                model_id="Qwen/Qwen3.5-9B",
            )
        except Exception as exc:
            logger.warning("Could not initialize OfficialSimpleJEVAdapter: %s. Using MockClassifierAdapter.", exc)
            from src.intelligence.jev.adapters.mock_adapter import MockClassifierAdapter
            _CLASSIFICATION_ADAPTER = MockClassifierAdapter(model_id="mock-qwen-classifier")
    return _CLASSIFICATION_ADAPTER


def classify_message_jev(text: str) -> Dict[str, Any]:
    """Execute JEV structured classification on market text.
    
    Produces output schema strictly compatible with Dakota's impact_mapper.py contracts:
        message_type, market_domain, topic, tickers, confidence, trading_intent, method, status.
    """
    from src.classification.local_classifier import _known_tickers, TRADING_ACTION_PATTERNS

    clean = " ".join(text.lower().split())
    tickers = _known_tickers(text)
    has_trading_action = any(term in clean for term in TRADING_ACTION_PATTERNS)

    adapter = get_pipeline_jev_adapter()

    # Define standard market domain classification question
    domain_criteria = {
        "equity": "Equities, stocks, shares, NSE/BSE listed companies, earnings, or company valuations.",
        "commodity": "Commodities: crude oil, gold, silver, natural gas, copper, metals, or agriculture.",
        "macro": "Macroeconomics, RBI policy, repo rates, inflation (CPI/WPI), GDP, or fiscal budget.",
        "sector": "Broad industry sectors: defence, banking, IT, pharma, energy, auto, or chemicals.",
        "none": "Non-financial chit-chat, spam, promotional group ads, greetings, or general noise.",
    }

    instructions = (
        "Classify the financial domain of the following market message. "
        "Select strictly one best-fitting domain from the options."
    )

    pred = adapter.predict_choice(
        task_name="market_domain_classification",
        instructions=instructions,
        criteria=domain_criteria,
        state=text,
        evidence_ids=[f"E_MSG_{hash(text) & 0xFFFFFFFF:08x}"],
        raw_logits=True,
    )

    evidence_tags = pred.evidence_ids if pred.evidence_ids else [f"E_MSG_{hash(text) & 0xFFFFFFFF:08x}"]

    # Determine if result represents insufficient evidence or ungrounded classification
    is_insufficient = (
        pred.confidence == 0.0
        or pred.predicted_label.lower() in ("insufficient evidence", "gpu oom error", "inference error")
        or (pred.error_status and "insufficient evidence" in pred.error_status.lower())
    )

    domain = pred.predicted_label.lower()
    if is_insufficient:
        domain = "none"
        msg_type = "insufficient_evidence"
    elif domain not in domain_criteria:
        domain = "none"
        msg_type = "a non-financial message"
    elif domain == "equity":
        msg_type = "a specific stock trading tip" if tickers else "an equity market observation"
    elif domain == "commodity":
        msg_type = "a commodity trading tip" if has_trading_action else "commodity market news"
    elif domain == "sector":
        msg_type = "a sector trading tip" if has_trading_action else "sector analysis"
    elif domain == "macro":
        msg_type = "a macro economic news update"
    else:
        msg_type = "a non-financial message"

    return {
        "message_type": msg_type,
        "type": msg_type,
        "market_domain": domain,
        "domain": domain,
        "topic": tickers[0] if tickers else None,
        "tickers": tickers,
        "confidence": 0.0 if is_insufficient else pred.confidence,
        "trading_intent": False if is_insufficient else has_trading_action,
        "is_actionable": False if is_insufficient else (domain != "none"),
        "insufficient_evidence": is_insufficient,
        "method": "jev_qwen3.5_4bit",
        "status": "unactionable_insufficient_evidence" if is_insufficient else "classified",
        "fallback_used": False,
        "evidence_ids": evidence_tags,
        "jev_metadata": {
            "model_id": pred.model_id,
            "classifier_version": pred.classifier_version,
            "is_calibrated": pred.is_calibrated,
            "margin": pred.margin,
            "entropy": pred.entropy,
            "class_scores": pred.class_scores,
            "raw_logits": pred.raw_logits,
            "prompt_hash": pred.prompt_hash,
            "latency_ms": pred.latency_ms,
            "error_status": pred.error_status,
            "evidence_ids": evidence_tags,
        },
    }


def classify_message_with_feature_flag(text: str) -> Dict[str, Any]:
    """Route classification through JEV if enabled, with safe fallback to rule/ML classifier."""
    from src.classification.local_classifier import rule_classify, ml_classify

    if is_jev_enabled():
        try:
            return classify_message_jev(text)
        except Exception as exc:
            logger.warning(
                "JEV classification encountered an error (%s). Falling back gracefully to local rule/ML classifier.",
                exc,
            )
            rules = rule_classify(text)
            fallback_res = dict(rules if rules else ml_classify(text))
            fallback_res["fallback_used"] = True
            fallback_res["fallback_reason"] = str(exc)
            fallback_res["original_classifier"] = "jev_qwen3.5_4bit"
            fallback_res.setdefault("evidence_ids", [f"E_MSG_{hash(text) & 0xFFFFFFFF:08x}"])
            return fallback_res

    # Default path: 100% existing Dakota rule-based and local ML behavior
    rules = rule_classify(text)
    return rules if rules else ml_classify(text)
