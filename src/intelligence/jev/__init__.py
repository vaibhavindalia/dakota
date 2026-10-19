"""JEV Financial Intelligence Subsystem for Project Dakota.

Provides logit-based structured classification, expectation scoring, and Noul continuous calibration
for open language models (Qwen family), eliminating generative formatting errors and hallucination.
"""
from __future__ import annotations

from .adapters.base import BaseClassifierAdapter
from .adapters.mock_adapter import MockClassifierAdapter
from .adapters.hf_adapter import HuggingFaceQwenAdapter
from .adapters.official_jev_adapter import OfficialSimpleJEVAdapter
from .prompt_builder import PromptPlan, prepare_prompt
from .response_scoring import score_branch_logits, score_plan_responses
from .schemas import (
    ClassifierOption,
    ClassifierQuestion,
    ClassifierRequest,
    PredictionResult,
    QuestionType,
    compute_prompt_hash,
)
from .tasks.base import BaseFinancialTask
from .tasks.sentiment import SentimentDivergenceTask
from .analysis_layer import EvidenceGroundedAnalyzer, FactualAnalysisReport, EvidenceCitation
from .dataset import FinancialBenchmarkSample, get_curated_indian_equity_dataset

__all__ = [
    "BaseClassifierAdapter",
    "MockClassifierAdapter",
    "HuggingFaceQwenAdapter",
    "OfficialSimpleJEVAdapter",
    "PromptPlan",
    "prepare_prompt",
    "score_branch_logits",
    "score_plan_responses",
    "ClassifierOption",
    "ClassifierQuestion",
    "ClassifierRequest",
    "PredictionResult",
    "QuestionType",
    "compute_prompt_hash",
    "BaseFinancialTask",
    "SentimentDivergenceTask",
    "EvidenceGroundedAnalyzer",
    "FactualAnalysisReport",
    "EvidenceCitation",
    "FinancialBenchmarkSample",
    "get_curated_indian_equity_dataset",
]
