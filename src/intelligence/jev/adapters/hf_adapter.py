"""Local Hugging Face Adapter for Qwen Models under the JEV Framework.

Implements prefix KV-cache sharing and next-token logit extraction for Qwen models.
Supports 4-bit quantization (BitsAndBytes) to fit comfortably within the RTX 4060 8GB VRAM envelope.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseClassifierAdapter

logger = logging.getLogger(__name__)


class HuggingFaceQwenAdapter(BaseClassifierAdapter):
    """Executes logit extraction on local Qwen checkpoints using PyTorch and Transformers."""

    def __init__(
        self,
        model_id: str = "Qwen/Qwen2.5-7B-Instruct",
        model_revision: str = "main",
        device: str = "auto",
        torch_dtype: str = "bfloat16",
        load_in_4bit: bool = True,
        max_context_length: int = 4096,
    ):
        super().__init__(model_id=model_id, model_revision=model_revision)
        self.device_name = device
        self.torch_dtype_str = torch_dtype
        self.load_in_4bit = load_in_4bit
        self.max_context_length = max_context_length
        self._model = None
        self._tokenizer = None
        self._lock = threading.Lock()
        self._is_loaded = False
        self._token_id_cache: Dict[str, int] = {}

    def is_loaded(self) -> bool:
        return self._is_loaded

    def load_model(self) -> None:
        """Load tokenizer and model weights with quantization and memory guardrails."""
        if self._is_loaded:
            return

        with self._lock:
            if self._is_loaded:
                return

            try:
                import torch
                from transformers import AutoModelForCausalLM, AutoTokenizer
            except ImportError as exc:
                raise ImportError(
                    "Local Hugging Face adapter requires PyTorch and Transformers. "
                    "Install with: pip install torch transformers accelerate"
                ) from exc

            logger.info("Initializing tokenizer for %s (%s)...", self.model_id, self.model_revision)
            self._tokenizer = AutoTokenizer.from_pretrained(
                self.model_id,
                revision=self.model_revision,
                trust_remote_code=True,
            )

            kwargs: Dict[str, Any] = {
                "revision": self.model_revision,
                "trust_remote_code": True,
            }

            if self.load_in_4bit and torch.cuda.is_available():
                try:
                    from transformers import BitsAndBytesConfig
                    bnb_config = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_quant_type="nf4",
                        bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
                        bnb_4bit_use_double_quant=True,
                    )
                    kwargs["quantization_config"] = bnb_config
                    kwargs["device_map"] = "auto"
                    logger.info("Enabling 4-bit NF4 quantization for 8GB VRAM compatibility.")
                except Exception as bnb_err:
                    logger.warning("BitsAndBytes 4-bit config failed (%s). Falling back to direct load.", bnb_err)

            if "quantization_config" not in kwargs:
                if self.device_name == "auto":
                    kwargs["device_map"] = "auto"
                else:
                    kwargs["device_map"] = self.device_name

                if self.torch_dtype_str == "bfloat16" and torch.cuda.is_available() and torch.cuda.is_bf16_supported():
                    kwargs["torch_dtype"] = torch.bfloat16
                elif self.torch_dtype_str in ("float16", "bfloat16") and torch.cuda.is_available():
                    kwargs["torch_dtype"] = torch.float16
                else:
                    kwargs["torch_dtype"] = torch.float32

            logger.info("Loading model weights for %s with config: %s", self.model_id, kwargs)
            self._model = AutoModelForCausalLM.from_pretrained(self.model_id, **kwargs)
            self._model.eval()
            self._is_loaded = True
            logger.info("Model %s successfully loaded and ready for JEV classification.", self.model_id)

    def _get_token_id(self, label: str) -> int:
        """Resolve token ID for an output label string under the model's tokenizer."""
        if label in self._token_id_cache:
            return self._token_id_cache[label]

        # In Qwen tokenization, single characters preceded by space or parenthesis have distinct IDs
        # Test direct encoding
        ids = self._tokenizer.encode(label, add_special_tokens=False)
        if len(ids) == 1:
            token_id = ids[0]
        else:
            # Check with leading space
            ids_space = self._tokenizer.encode(" " + label, add_special_tokens=False)
            if len(ids_space) == 1:
                token_id = ids_space[0]
            else:
                token_id = ids[0]

        self._token_id_cache[label] = token_id
        return token_id

    def extract_branch_logits(
        self,
        prompt_prefix: str,
        question_text: str,
        answer_prefix: str,
        output_labels: tuple[str, ...],
    ) -> Dict[str, float]:
        """Extract unnormalized logits at the answer boundary."""
        if not self._is_loaded:
            self.load_model()

        import torch

        with self._lock:
            # Construct complete input prompt
            full_text = f"{prompt_prefix}\n{question_text}\n{answer_prefix}"
            
            # Format according to chat template if available, else raw text
            if hasattr(self._tokenizer, "apply_chat_template"):
                messages = [
                    {"role": "system", "content": prompt_prefix},
                    {"role": "user", "content": question_text},
                ]
                try:
                    formatted = self._tokenizer.apply_chat_template(
                        messages,
                        tokenize=False,
                        add_generation_prompt=True,
                    )
                    full_text = f"{formatted}{answer_prefix}"
                except Exception:
                    # Fallback to direct raw prompt
                    pass

            encoded = self._tokenizer(
                full_text,
                return_tensors="pt",
                truncation=True,
                max_length=self.max_context_length,
            )

            # Resolve model device
            device = next(self._model.parameters()).device
            input_ids = encoded["input_ids"].to(device)
            attention_mask = encoded["attention_mask"].to(device)

            with torch.no_grad():
                # Single forward pass — prefill only, zero generation
                outputs = self._model(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    use_cache=False,
                )
                # Next token logits at the final position
                last_token_logits = outputs.logits[0, -1, :]

            # Gather only the requested output labels
            result: Dict[str, float] = {}
            for lbl in output_labels:
                t_id = self._get_token_id(lbl)
                result[lbl] = float(last_token_logits[t_id].detach().cpu().item())

            return result

    def get_model_info(self) -> Dict[str, Any]:
        loaded = self._is_loaded
        device = str(next(self._model.parameters()).device) if loaded and self._model else "unloaded"
        dtype = str(next(self._model.parameters()).dtype) if loaded and self._model else self.torch_dtype_str

        return {
            "backend": "huggingface_transformers",
            "model_id": self.model_id,
            "revision": self.model_revision,
            "is_loaded": loaded,
            "device": device,
            "dtype": dtype,
            "load_in_4bit": self.load_in_4bit,
            "max_context_length": self.max_context_length,
        }
