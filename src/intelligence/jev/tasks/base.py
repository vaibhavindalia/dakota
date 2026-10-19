"""Base abstraction for versioned financial classification tasks."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from ..adapters.base import BaseClassifierAdapter
from ..schemas import PredictionResult


class BaseFinancialTask(ABC):
    """Encapsulates label taxonomy, prompt instructions, and evaluation rules for a specific financial task."""

    def __init__(self, task_name: str, task_version: str = "v1.0"):
        self.task_name = task_name
        self.task_version = task_version

    @property
    @abstractmethod
    def candidate_classes(self) -> Dict[str, str]:
        """Dictionary of candidate label names and their operational descriptions."""
        pass

    @property
    @abstractmethod
    def task_instructions(self) -> str:
        """Core instruction prompt describing the classification criteria."""
        pass

    @abstractmethod
    def build_evidence_state(self, sample: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        """Construct normalized point-in-time evidence state and list of citation IDs.
        
        Must prevent future-information leakage by asserting timestamps.
        """
        pass

    def classify(
        self,
        adapter: BaseClassifierAdapter,
        sample: Dict[str, Any],
        raw_logits: bool = True,
    ) -> PredictionResult:
        """Execute task classification using the provided adapter."""
        state, evidence_ids = self.build_evidence_state(sample)
        return adapter.predict_choice(
            task_name=self.task_name,
            instructions=self.task_instructions,
            criteria=self.candidate_classes,
            state=state,
            evidence_ids=evidence_ids,
            dataset_version=self.task_version,
            raw_logits=raw_logits,
        )
