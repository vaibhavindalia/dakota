"""Deterministic Mock Adapter for JEV classification engine.

Allows offline unit testing, mathematical verification, and edge-case simulation
without downloading multi-gigabyte weights or requiring GPU availability.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from .base import BaseClassifierAdapter


class MockClassifierAdapter(BaseClassifierAdapter):
    """Mock adapter producing controllable or deterministic pseudo-logits."""

    def __init__(
        self,
        model_id: str = "mock-qwen-classifier",
        model_revision: str = "test-rev-1",
        preset_logits: Optional[Dict[str, float]] = None,
        simulated_latency_ms: float = 5.0,
    ):
        super().__init__(model_id=model_id, model_revision=model_revision)
        self.preset_logits = preset_logits
        self.simulated_latency_ms = simulated_latency_ms
        self.call_history: List[Dict[str, Any]] = []

    def set_preset_logits(self, logits: Dict[str, float]) -> None:
        """Inject specific logits for testing assertions or edge-cases."""
        self.preset_logits = logits

    def extract_branch_logits(
        self,
        prompt_prefix: str,
        question_text: str,
        answer_prefix: str,
        output_labels: tuple[str, ...],
    ) -> Dict[str, float]:
        if self.simulated_latency_ms > 0:
            time.sleep(self.simulated_latency_ms / 1000.0)

        self.call_history.append({
            "prompt_prefix": prompt_prefix,
            "question_text": question_text,
            "answer_prefix": answer_prefix,
            "output_labels": output_labels,
        })

        if self.preset_logits is not None:
            # Return configured logits or slice matching output_labels
            result = {}
            for idx, lbl in enumerate(output_labels):
                if lbl in self.preset_logits:
                    result[lbl] = float(self.preset_logits[lbl])
                elif str(idx) in self.preset_logits:
                    result[lbl] = float(self.preset_logits[str(idx)])
                else:
                    result[lbl] = 0.0
            return result

        # Deterministic default: assign decaying logits across candidate labels (A > B > C...)
        return {
            lbl: round(5.0 - (idx * 1.5), 2)
            for idx, lbl in enumerate(output_labels)
        }

    def get_model_info(self) -> Dict[str, Any]:
        return {
            "backend": "mock_deterministic",
            "model_id": self.model_id,
            "revision": self.model_revision,
            "device": "cpu",
            "precision": "synthetic_float32",
            "calls_recorded": len(self.call_history),
        }
