"""FastAPI Router for JEV Financial Intelligence Subsystem.

Exposes endpoints for:
1. POST /api/intelligence/jev/classify — Logit-based structured classification
2. POST /api/intelligence/jev/analyze — Citation-grounded factual analysis
3. GET /api/intelligence/jev/benchmark — Walk-forward comparative benchmark results
4. GET /api/intelligence/jev/models — Model hardware profile and adapter status
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .adapters.base import BaseClassifierAdapter
from .adapters.mock_adapter import MockClassifierAdapter
from .tasks.sentiment import SentimentDivergenceTask
from .analysis_layer import EvidenceGroundedAnalyzer, FactualAnalysisReport
from .schemas import PredictionResult
from .evaluation.benchmark import BenchmarkRunner, BenchmarkReport
from .dataset import get_curated_indian_equity_dataset

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/intelligence/jev", tags=["JEV Intelligence"])

# Global adapter instance (defaults to deterministic Mock adapter for zero-weight safety)
_ACTIVE_ADAPTER: BaseClassifierAdapter = MockClassifierAdapter(
    model_id="mock-qwen2.5-7b-instruct",
    preset_logits={
        "sentiment_divergence": {
            "A": 0.5,
            "B": 1.2,
            "C": 1.8,
            "D": 4.6,
            "E": 2.1,
            "F": 0.1,
        }
    }
)
_TASK = SentimentDivergenceTask()
_ANALYZER = EvidenceGroundedAnalyzer()
_CACHED_BENCHMARK: Optional[BenchmarkReport] = None


def get_active_adapter() -> BaseClassifierAdapter:
    global _ACTIVE_ADAPTER
    # Use mock ONLY when explicitly requested via DAKOTA_USE_MOCK=1 or DAKOTA_USE_JEV=0
    use_mock = (
        os.environ.get("DAKOTA_USE_MOCK", "0").strip().lower() in ("1", "true", "yes", "on")
        or os.environ.get("DAKOTA_USE_JEV", "1").strip().lower() in ("0", "false", "no", "off")
    )
    if not use_mock:
        if isinstance(_ACTIVE_ADAPTER, MockClassifierAdapter):
            try:
                from .adapters.official_jev_adapter import OfficialSimpleJEVAdapter
                _ACTIVE_ADAPTER = OfficialSimpleJEVAdapter()
            except Exception as e:
                logger.warning("Could not activate OfficialSimpleJEVAdapter: %s", e)
    else:
        if not isinstance(_ACTIVE_ADAPTER, MockClassifierAdapter):
            _ACTIVE_ADAPTER = MockClassifierAdapter(model_id="mock-qwen2.5-7b-instruct")
    return _ACTIVE_ADAPTER



def set_active_adapter(adapter: BaseClassifierAdapter) -> None:
    global _ACTIVE_ADAPTER
    _ACTIVE_ADAPTER = adapter


class ClassifyRequest(BaseModel):
    ticker: Optional[str] = Field(default="CDSL", description="NSE/BSE scrip symbol")
    claim: Optional[str] = Field(
        default="CDSL target ₹1,500 by Friday! Guaranteed returns, join VIP channel.",
        description="Market tip, promotional message, or claim to evaluate"
    )
    sample: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional full market evidence state (price, volume, delivery, technicals, news, social)"
    )


class ModelProfileResponse(BaseModel):
    active_model_id: str
    backend: str
    device: str
    cuda_available: bool
    torch_version: str
    ram_total_gb: Optional[float] = None
    devices: List[Dict[str, Any]] = Field(default_factory=list)
    supported_tasks: List[str] = Field(default_factory=list)


@router.get("/models", response_model=ModelProfileResponse)
def get_model_profile() -> ModelProfileResponse:
    """Return compute profile, active adapter, and supported financial intelligence tasks."""
    adapter = get_active_adapter()
    info = adapter.get_model_info()

    cuda_avail = False
    torch_ver = "unavailable"
    devices = []
    try:
        import torch
        torch_ver = torch.__version__
        cuda_avail = torch.cuda.is_available()
        if cuda_avail:
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                devices.append({
                    "id": i,
                    "name": props.name,
                    "total_vram_mb": round(props.total_memory / (1024 * 1024), 2),
                })
    except ImportError:
        pass

    ram_gb = None
    try:
        import psutil
        ram_gb = round(psutil.virtual_memory().total / (1024**3), 2)
    except ImportError:
        pass

    return ModelProfileResponse(
        active_model_id=adapter.model_id,
        backend=info.get("backend", "unknown"),
        device=info.get("device", "cpu"),
        cuda_available=cuda_avail,
        torch_version=torch_ver,
        ram_total_gb=ram_gb,
        devices=devices,
        supported_tasks=["sentiment_divergence", "manipulation_risk", "market_events"],
    )


@router.post("/classify", response_model=Dict[str, Any])
def classify_financial_context(payload: ClassifyRequest) -> Dict[str, Any]:
    """Execute logit-based JEV classification on financial claim and telemetry."""
    adapter = get_active_adapter()

    # Build or use provided sample
    sample_data = payload.sample or {
        "ticker": payload.ticker,
        "as_of": "2026-10-08T18:00:00Z",
        "latest_price": 1263.40,
        "change_pct": 1.07,
        "volume": 896613,
        "delivery_pct": 41.2,
        "technicals": {"trend_vs_ema20": "flat"},
        "risk_score": 10.0,
        "risk_band": "Low",
        "is_surveillance": False,
        "news_headlines": ["Routine Regulation 74(5) compliance certificate filed on BSE"],
        "social_signals": [payload.claim],
        "evidence_ids": [f"E_MKT_{payload.ticker}", "E_FILING_BSE", "E_SOC_TG"],
    }

    try:
        result: PredictionResult = _TASK.classify(adapter, sample_data)
        return result.model_dump()
    except Exception as e:
        logger.error("JEV classification failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze", response_model=Dict[str, Any])
def analyze_financial_context(payload: ClassifyRequest) -> Dict[str, Any]:
    """Run JEV classification and synthesize evidence-grounded factual analysis with citations."""
    adapter = get_active_adapter()

    sample_data = payload.sample or {
        "ticker": payload.ticker,
        "as_of": "2026-10-08T18:00:00Z",
        "latest_price": 1263.40,
        "change_pct": 1.07,
        "volume": 896613,
        "delivery_pct": 41.2,
        "technicals": {"trend_vs_ema20": "flat"},
        "risk_score": 10.0,
        "risk_band": "Low",
        "is_surveillance": False,
        "news_headlines": ["Routine Regulation 74(5) compliance certificate filed on BSE"],
        "social_signals": [payload.claim],
        "evidence_ids": [f"E_MKT_{payload.ticker}", "E_FILING_BSE", "E_SOC_TG"],
    }

    try:
        prediction = _TASK.classify(adapter, sample_data)
        report: FactualAnalysisReport = _ANALYZER.analyze(prediction, sample_data)
        return {
            "prediction": prediction.model_dump(),
            "analysis": report.model_dump(),
        }
    except Exception as e:
        logger.error("Evidence-grounded analysis failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/benchmark", response_model=Dict[str, Any])
def get_benchmark_results(
    refresh: bool = Query(default=False, description="Force re-computation of walk-forward benchmark"),
    n_splits: int = Query(default=2, ge=1, le=5),
    purge_hours: float = Query(default=24.0, ge=0.0),
) -> Dict[str, Any]:
    """Retrieve or execute walk-forward benchmark comparing JEV against baselines and frontier reference."""
    global _CACHED_BENCHMARK
    adapter = get_active_adapter()

    if _CACHED_BENCHMARK is None or refresh:
        dataset = get_curated_indian_equity_dataset()
        runner = BenchmarkRunner(
            samples=dataset,
            n_splits=n_splits,
            purge_window_hours=purge_hours,
        )
        _CACHED_BENCHMARK = runner.run(adapter)

    return {
        "report": _CACHED_BENCHMARK.model_dump(),
        "markdown_table": _CACHED_BENCHMARK.to_markdown_table(),
    }
