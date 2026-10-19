"""Base adapter interface for JEV structured classification engines."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union

from ..prompt_builder import prepare_prompt
from ..response_scoring import score_branch_logits
from ..schemas import (
    ClassifierOption,
    ClassifierQuestion,
    ClassifierRequest,
    PredictionResult,
    QuestionType,
    compute_prompt_hash,
)


class BaseClassifierAdapter(ABC):
    """Abstract interface for JEV model execution backends."""

    def __init__(self, model_id: str, model_revision: str = "main"):
        self.model_id = model_id
        self.model_revision = model_revision

    @abstractmethod
    def extract_branch_logits(
        self,
        prompt_prefix: str,
        question_text: str,
        answer_prefix: str,
        output_labels: tuple[str, ...],
    ) -> Dict[str, float]:
        """Run single forward pass and extract logits for the specified output labels.
        
        Args:
            prompt_prefix: System + context/state text.
            question_text: Formatted candidates and question instruction.
            answer_prefix: Assistant prefix (e.g. 'Answer: (').
            output_labels: Explicit tokens to extract (e.g. ('A', 'B', 'C')).
            
        Returns:
            Dict mapping output_label (e.g. 'A') to raw logit float.
        """
        pass

    @abstractmethod
    def get_model_info(self) -> Dict[str, Any]:
        """Return metadata describing backend, precision, device, and memory usage."""
        pass

    def predict_choice(
        self,
        task_name: str,
        instructions: str,
        criteria: Dict[str, Optional[str]],
        state: Optional[Union[str, Dict[str, Any]]] = None,
        evidence_ids: Optional[List[str]] = None,
        dataset_version: str = "dakota-v1.0",
        raw_logits: bool = True,
    ) -> PredictionResult:
        """High-level convenience method to classify a single categorical choice task."""
        t0 = time.perf_counter()
        
        q = ClassifierQuestion(
            type=QuestionType.CHOICE,
            instructions=instructions,
            criteria=criteria,
        )
        req = ClassifierRequest(
            model=self.model_id,
            state=state,
            questions={"main": q},
            options=ClassifierOption(raw_logits=raw_logits),
        )
        
        plan = prepare_prompt(req, version="v1")
        branch = plan.questions[0]
        
        full_prefix = (
            f"{plan.system_prompt_prefix}\n\n"
            f"{plan.prefix_instruction}{plan.state_text or 'None'}\n\n"
            f"{plan.suffix_instruction}"
        )
        
        logits_dict = self.extract_branch_logits(
            prompt_prefix=full_prefix,
            question_text=branch.instruction,
            answer_prefix=branch.answer_prefix,
            output_labels=branch.output_labels,
        )
        
        scored = score_branch_logits(branch, logits_dict, raw_logits_flag=raw_logits)
        latency = (time.perf_counter() - t0) * 1000.0
        prompt_hash = compute_prompt_hash(f"{full_prefix}\n{branch.instruction}\n{branch.answer_prefix}")

        return PredictionResult(
            task_name=task_name,
            predicted_label=scored["predicted_label"],
            class_scores=scored["probabilities"],
            confidence=scored["confidence"],
            is_calibrated=scored["is_calibrated"],
            margin=scored["margin"],
            raw_logits=scored.get("raw_logits"),
            evidence_ids=evidence_ids or [],
            model_id=self.model_id,
            model_revision=self.model_revision,
            classifier_version="jev-v1.0",
            prompt_hash=prompt_hash,
            dataset_version=dataset_version,
            latency_ms=round(latency, 2),
        )
