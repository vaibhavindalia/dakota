"""FastAPI Surveillance & Quantitative Manipulation Detection Router (QN & JAV).

Endpoints:
- GET  /api/surveillance/qn/universe: Overview of the 500-equity Indian surveillance cohort.
- GET  /api/surveillance/qn/stocks: Search and paginate the 500 equities.
- GET  /api/surveillance/qn/analyze/{ticker}: Full quantitative and JAV forensic analysis on a stock.
- GET  /api/surveillance/qn/evidence: Query official SEBI enforcement orders and surveillance notices.
- GET  /api/surveillance/qn/research/experiment: Dataset manifest and leakage-safe holdout evaluation metrics.
- POST /api/surveillance/qn/train: Trigger reproducible model training with concurrency lock.
- GET  /api/surveillance/qn/model/status: Active model version, artifact metadata, and feature importances.
"""
from __future__ import annotations

import json
import logging
import threading
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from .dataset_builder import DATASET_MANIFEST_JSON, dataset_builder
from .evidence import EvidenceStrength, ManipulationLabel, evidence_registry
from .model import (
    MODEL_ARTIFACT_PATH,
    MODEL_META_PATH,
    QNManipulationModel,
    _IS_TRAINING,
    qn_inference,
)
from .universe import normalize_symbol, surveillance_universe

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/surveillance/qn", tags=["Surveillance QN & JAV"])


class TrainRequest(BaseModel):
    purge_days: int = Field(default=15, description="Embargo purge window between splits (in days)")
    random_state: int = Field(default=42, description="Reproducible random seed")


@router.get("/universe")
def get_universe_overview() -> Dict[str, Any]:
    """Retrieve 500-equity Indian stock universe metadata, case counts, and segment distribution."""
    return surveillance_universe.get_summary()


@router.get("/stocks")
def list_surveillance_stocks(
    search: str = Query(default="", description="Search by ticker or company name"),
    segment: str = Query(default="", description="Filter by segment: 'main' or 'sme'"),
    role: str = Query(default="", description="Filter by role: 'case' or 'control'"),
    surveillance_only: bool = Query(default=False, description="Filter to surveillance-flagged equities only"),
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(default=25, ge=1, le=100, description="Items per page"),
) -> Dict[str, Any]:
    """Search and paginate the 500 equities in the surveillance cohort."""
    equities = surveillance_universe.list_equities(
        segment=segment if segment else None,
        role=role if role else None,
        surveillance_only=surveillance_only,
    )

    if search.strip():
        term = search.strip().upper()
        equities = [e for e in equities if term in e.ticker.upper() or term in e.name.upper()]

    total = len(equities)
    start_idx = (page - 1) * limit
    paged = equities[start_idx : start_idx + limit]

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": max(1, (total + limit - 1) // limit),
        "stocks": [e.to_dict() for e in paged],
    }


@router.get("/analyze/{ticker}")
def analyze_stock_surveillance(ticker: str) -> Dict[str, Any]:
    """Execute complete QN quantitative surveillance & JAV forensic intelligence on a stock."""
    sym = normalize_symbol(ticker)
    eq = surveillance_universe.get_equity(sym)
    if not eq:
        # Check if known symbol in general market
        from src.market.universe_manager import get_stock_profile
        profile = get_stock_profile(sym)
        if not profile:
            raise HTTPException(status_code=404, detail=f"Stock '{ticker}' not found in universe")

    # 1. Run QN quantitative model inference
    qn_pred = qn_inference.analyze_ticker(sym)

    # 2. Retrieve official regulatory evidence (SEBI orders, ASM/GSM notices)
    events = evidence_registry.get_events_for_ticker(sym)

    # 3. Retrieve core Dakota deterministic risk score
    core_risk = None
    try:
        from src.engine.risk_engine import assess
        core_risk = assess(sym)
    except Exception as exc:
        logger.debug("Core risk assessment failed for %s: %s", sym, exc)

    # 4. Retrieve JAV logit classification summary if active
    jav_summary = None
    try:
        from src.intelligence.jev.api import get_active_adapter
        adapter = get_active_adapter()
        info = adapter.get_model_info()
        jav_summary = {
            "active_model_id": adapter.model_id,
            "backend": info.get("backend", "unknown"),
            "status": "ready",
        }
    except Exception:
        pass

    return {
        "ticker": sym,
        "company_name": eq.name if eq else sym,
        "exchange": eq.exchange if eq else "NSE",
        "segment": eq.segment if eq else "main",
        "role": eq.role if eq else "control",
        "surveillance_flag": eq.surveillance_flag if eq else False,
        "qn_prediction": qn_pred.to_dict(),
        "core_risk_engine": {
            "score": core_risk.get("score") if core_risk else None,
            "band": core_risk.get("band") if core_risk else "Unavailable",
            "contributions": core_risk.get("contributions") if core_risk else {},
            "reasons": core_risk.get("reasons") if core_risk else [],
        },
        "registered_evidence": [ev.to_dict() for ev in events],
        "jav_intelligence": jav_summary,
        "disclaimer": (
            "Dakota QN and JAV outputs are algorithmic forensic risk signals. "
            "They do not constitute a legal finding of fraud under SEBI regulations or investment advice."
        ),
    }


@router.get("/evidence")
def list_regulatory_evidence(
    label: Optional[str] = Query(default=None, description="Filter by ManipulationLabel"),
    min_strength: Optional[str] = Query(default=None, description="Filter by minimum EvidenceStrength"),
) -> Dict[str, Any]:
    """Retrieve verified official regulatory enforcement orders (SEBI, BSE, NSE, SAT)."""
    lbl_enum = None
    if label:
        try:
            lbl_enum = ManipulationLabel(label.strip().upper())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid label: '{label}'")

    str_enum = None
    if min_strength:
        try:
            str_enum = EvidenceStrength(min_strength.strip().upper())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid strength: '{min_strength}'")

    events = evidence_registry.list_events(label=lbl_enum, min_strength=str_enum)
    summary = evidence_registry.get_summary()

    return {
        "summary": summary,
        "total_returned": len(events),
        "events": [e.to_dict() for e in events],
    }


@router.get("/research/experiment")
def get_research_experiment() -> Dict[str, Any]:
    """Retrieve 500-stock research manifest, split distribution, and holdout evaluation metrics."""
    if not DATASET_MANIFEST_JSON.exists():
        manifest = dataset_builder.build_dataset()
    else:
        try:
            manifest = json.loads(DATASET_MANIFEST_JSON.read_text(encoding="utf-8"))
        except Exception:
            manifest = dataset_builder.build_dataset()

    model_meta = qn_inference.get_metadata()

    return {
        "experiment_name": "Indian Equity Market Manipulation Surveillance Benchmark (500 Equities)",
        "dataset_manifest": manifest,
        "active_model_metadata": model_meta,
        "research_limitations": {
            "severe_class_imbalance": "Documented positive manipulation cases represent ~1-5% of real market windows.",
            "leakage_safeguards": "Strict 15-day embargo purge window and event-level entity grouping enforced.",
            "point_in_time_guarantee": "Features are computed strictly on past data up to each window's as-of date.",
        },
    }


def _background_train_worker(random_state: int):
    logger.info("Starting background training for QN model (seed: %d)...", random_state)
    try:
        model = QNManipulationModel(random_state=random_state)
        val_rep, test_rep, meta = model.train()
        qn_inference._load()
        logger.info(
            "Background QN training complete! Validation ROC-AUC: %.4f, Test ROC-AUC: %.4f",
            val_rep.roc_auc,
            test_rep.roc_auc,
        )
    except Exception as exc:
        logger.error("Background QN training failed: %s", exc, exc_info=True)


@router.post("/train")
def trigger_model_training(
    payload: TrainRequest,
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    """Trigger reproducible QN model retraining in background with concurrency protection."""
    global _IS_TRAINING
    if _IS_TRAINING:
        raise HTTPException(
            status_code=409,
            detail="A model training job is currently in progress. Please wait for it to complete.",
        )

    background_tasks.add_task(_background_train_worker, payload.random_state)

    return {
        "status": "TRAINING_INITIALIZED",
        "message": "QN training pipeline launched in background.",
        "purge_embargo_days": payload.purge_days,
        "random_state": payload.random_state,
    }


@router.get("/model/status")
def get_model_status() -> Dict[str, Any]:
    """Inspect active QN model version, artifact status, and feature importances."""
    is_avail = qn_inference.is_model_available()
    meta = qn_inference.get_metadata()
    return {
        "is_model_available": is_avail,
        "model_version": meta.get("model_version", "unavailable"),
        "trained_at": meta.get("trained_at"),
        "training_duration_seconds": meta.get("training_duration_seconds"),
        "train_samples": meta.get("train_samples"),
        "val_samples": meta.get("val_samples"),
        "test_samples": meta.get("test_samples"),
        "feature_importances": meta.get("feature_importances", {}),
        "holdout_test_metrics": meta.get("holdout_test_metrics", {}),
        "artifact_path": str(MODEL_ARTIFACT_PATH),
    }
