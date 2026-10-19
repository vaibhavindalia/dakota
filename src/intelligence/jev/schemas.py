"""Structured Data Schemas for JEV Financial Intelligence Engine.

Complies with Simple JEV specification and Dakota's provenance contracts.
Enforces strict input validation, non-finite score rejection, and explicit confidence definitions.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator


class QuestionType(str, Enum):
    CHOICE = "choice"
    SCORE = "score"
    NOUL = "noul"


class ClassifierOption(BaseModel):
    """Configuration options for a classification request."""
    model_config = ConfigDict(extra="forbid")
    raw_logits: bool = Field(default=False, description="Whether to include raw unnormalized logits")


class ClassifierQuestion(BaseModel):
    """Single classification question or scoring branch."""
    model_config = ConfigDict(extra="forbid")
    type: QuestionType = Field(default=QuestionType.CHOICE, description="Type of question: choice, score, or noul")
    instructions: str = Field(..., min_length=1, description="Question instruction text")
    criteria: Optional[Dict[str, Optional[str]]] = Field(
        default=None,
        description="For choice/score: candidate options or rubric levels (keys are options, values are descriptions)"
    )

    @field_validator("criteria")
    @classmethod
    def validate_criteria(cls, v: Optional[Dict[str, Optional[str]]], info: Any) -> Optional[Dict[str, Optional[str]]]:
        # If type is choice, criteria must have at least 2 candidates
        return v


class ClassifierRequest(BaseModel):
    """Full classification request passed to JEV engine."""
    model_config = ConfigDict(extra="ignore")
    model: str = Field(..., description="Target model ID or alias")
    state: Optional[Union[str, Dict[str, Any], List[Any]]] = Field(
        default=None,
        description="Contextual state (plain text, JSON object, or list)"
    )
    messages: Optional[List[Dict[str, str]]] = Field(
        default=None,
        description="Optional conversation turns: [{'role': 'user', 'content': ...}]"
    )
    questions: Dict[str, ClassifierQuestion] = Field(
        ...,
        min_length=1,
        description="Map of question_id to ClassifierQuestion"
    )
    options: ClassifierOption = Field(
        default_factory=ClassifierOption,
        description="Execution options"
    )


class PredictionResult(BaseModel):
    """Stable, standardized output schema for all JEV + Qwen financial tasks.
    
    Distinguishes:
    - raw_logits: Direct unnormalized output from causal LM head z_i
    - class_scores: Normalized probabilities p_i = softmax(z_i)
    - confidence: p_max (highest probability), marked calibrated=False unless an explicit calibration map was applied
    - margin: p_1 - p_2 (separation between winner and runner-up)
    """
    model_config = ConfigDict(extra="ignore")

    task_name: str = Field(..., description="Unique task identifier, e.g. sentiment_divergence")
    predicted_label: str = Field(..., description="Winner class label or continuous rating value")
    class_scores: Dict[str, float] = Field(
        ...,
        description="Normalized class probability distribution summing to 1.0"
    )
    confidence: float = Field(
        ...,
        description="Top class probability or certainty metric (0.0 to 1.0)"
    )
    is_calibrated: bool = Field(
        default=False,
        description="Whether confidence is post-hoc calibrated (e.g. Platt scaling, isotonic regression)"
    )
    margin: Optional[float] = Field(
        default=None,
        description="Probability margin between the winning class and runner-up (p_1 - p_2)"
    )
    raw_logits: Optional[Dict[str, float]] = Field(
        default=None,
        description="Raw, unnormalized logits directly from the model vocabulary head"
    )
    variance: Optional[float] = Field(
        default=None,
        description="Distribution variance across levels or bins (applicable to score and noul)"
    )
    entropy: Optional[float] = Field(
        default=None,
        description="Shannon entropy (nats) measuring distribution uncertainty"
    )
    evidence_ids: List[str] = Field(
        default_factory=list,
        description="List of verified Dakota evidence IDs supporting this assessment (e.g. ['E1', 'E2'])"
    )
    model_id: str = Field(..., description="Underlying model name, e.g. Qwen/Qwen2.5-7B-Instruct")
    model_revision: str = Field(default="main", description="Model checkpoint revision or commit hash")
    classifier_version: str = Field(default="jev-v1.0", description="JEV adapter and prompt contract version")
    prompt_hash: str = Field(..., description="SHA-256 hash of the compiled prompt instruction")
    dataset_version: str = Field(default="dakota-v1.0", description="Dataset or evidence snapshot version")
    prediction_timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 UTC timestamp when prediction was computed"
    )
    latency_ms: float = Field(..., description="End-to-end forward pass latency in milliseconds")
    error_status: Optional[str] = Field(default=None, description="Error message if inference encountered an issue")
    explanation: Optional[str] = Field(default=None, description="Optional verbalized factual analysis")


def compute_prompt_hash(prompt_text: str) -> str:
    """Compute deterministic SHA-256 hash for a prompt string."""
    return hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()
