"""Risk Bridge: Connects QN Quantitative Surveillance to Dakota's Risk Engine (Phase 8).

Preserves the existing deterministic 0-100 forensic score and its 5 weighted groups,
attaching QN manipulation risk as an orthogonal, distinct model-derived signal.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .model import QNPrediction, qn_inference

logger = logging.getLogger(__name__)


def attach_qn_intelligence(
    risk_dict: Dict[str, Any],
    ticker: str,
    as_of: Optional[str] = None,
) -> Dict[str, Any]:
    """Augment a Dakota risk assessment with distinct QN surveillance signals.

    Invariant:
    - Never mutates or overwrites risk_dict['score'], ['band'], or ['groups'].
    - Enforces graceful fallback if QN model inference fails or model is absent.
    """
    try:
        pred: QNPrediction = qn_inference.analyze_ticker(ticker, as_of_date=as_of)
        risk_dict["qn_surveillance"] = {
            "model_score": pred.model_score,
            "manipulation_probability": pred.manipulation_probability,
            "risk_band": pred.risk_band,
            "confidence": pred.confidence,
            "margin": pred.margin,
            "contributing_factors": pred.contributing_factors,
            "top_factor_reasons": pred.top_factor_reasons,
            "model_version": pred.model_version,
            "is_real_model": pred.is_real_model,
            "data_freshness": pred.data_freshness,
            "latency_ms": pred.latency_ms,
            "prediction_timestamp": datetime.now(timezone.utc).isoformat(),
            "relation_to_risk_engine": (
                "QN provides an orthogonal, calibrated machine-learning surveillance signal that "
                "evaluates anomalous volume, price-volume divergence, and volatility expansion. "
                "The core 5-pillar forensic score remains 100% deterministic and mathematically unmutated."
            ),
            "disclaimer": pred.disclaimer,
        }
    except Exception as exc:
        logger.warning("Failed attaching QN intelligence for %s: %s", ticker, exc)
        risk_dict["qn_surveillance"] = {
            "model_score": None,
            "manipulation_probability": None,
            "risk_band": "Unavailable",
            "model_version": "unavailable",
            "is_real_model": False,
            "data_freshness": "UNAVAILABLE",
            "error": str(exc),
            "disclaimer": "Surveillance intelligence temporarily unavailable.",
        }

    return risk_dict
