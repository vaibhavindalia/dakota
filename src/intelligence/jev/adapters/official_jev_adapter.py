"""Official Simple JEV Adapter for Qwen3.5-9B (4-bit NF4) in Project Dakota.

Integrates the official Featherless AI Simple JEV specification with the local
Qwen3.5-9B 4-bit NF4 causal LM backbone.

Strict safety invariants:
1. Reuses official simple-jev-reference modules directly (prompt_builder, response_scoring, hf_server).
2. Prevents multiple model instances from exhausting VRAM via a thread-safe singleton manager.
3. Separates model initialization from per-request inference.
4. Distinguishes raw label probabilities from calibrated confidence (is_calibrated=False).
5. Explicitly handles insufficient evidence, ambiguous classifications, unsupported inputs, and GPU OOM.
6. Preserves evidence provenance, citation IDs, and audit timestamps.
"""
from __future__ import annotations

import hashlib
import logging
import math
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from .base import BaseClassifierAdapter
from ..schemas import (
    ClassifierOption,
    ClassifierQuestion,
    ClassifierRequest,
    PredictionResult,
    QuestionType,
    compute_prompt_hash,
)

logger = logging.getLogger(__name__)


def _resolve_simple_jev_path() -> Optional[str]:
    """Find the official simple-jev-reference directory across environments."""
    candidates = [
        os.environ.get("SIMPLE_JEV_DIR"),
        os.path.expanduser("~/dakota-jev/simple-jev-reference"),
        "/home/vdish/dakota-jev/simple-jev-reference",
        r"\\wsl.localhost\Ubuntu-22.04\home\vdish\dakota-jev\simple-jev-reference",
        os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../../../../simple-jev-reference")
        ),
    ]
    for p in candidates:
        if p and os.path.isdir(p) and os.path.isfile(os.path.join(p, "common", "prompt_builder.py")):
            return p
    return None


def _ensure_simple_jev_imported():
    """Dynamically register simple-jev-reference on sys.path without modifying reference checkout."""
    ref_path = _resolve_simple_jev_path()
    if ref_path and ref_path not in sys.path:
        sys.path.insert(0, ref_path)
        hf_dir = os.path.join(ref_path, "hf-server")
        if os.path.isdir(hf_dir) and hf_dir not in sys.path:
            sys.path.insert(0, hf_dir)


def _resolve_qwen_model_dir() -> str:
    """Resolve local path to the Qwen3.5-9B checkpoint."""
    candidates = [
        os.environ.get("QWEN_MODEL_DIR"),
        r"C:\Users\vdish\.cache\huggingface\hub\models--Qwen--Qwen3.5-9B\snapshots\c202236235762e1c871ad0ccb60c8ee5ba337b9a",
        "/mnt/c/Users/vdish/.cache/huggingface/hub/models--Qwen--Qwen3.5-9B/snapshots/c202236235762e1c871ad0ccb60c8ee5ba337b9a",
    ]
    for p in candidates:
        if p and os.path.isdir(p):
            return p
    # Default fallback to WSL mount path
    return candidates[2]


class OfficialSimpleJEVAdapter(BaseClassifierAdapter):
    """Adapter bridging Dakota's BaseClassifierAdapter to official Simple JEV + Qwen3.5-9B."""

    # Thread-safe class-level singleton to strictly prevent duplicate model loads
    _shared_model = None
    _shared_tokenizer = None
    _shared_compiler = None
    _shared_policy: str = "baseline"
    _shared_lock = threading.Lock()
    _is_loaded: bool = False
    _load_error: Optional[str] = None
    _last_load_attempt_time: float = 0.0
    _load_cooldown_seconds: float = 30.0

    def __init__(
        self,
        model_id: str = "Qwen/Qwen3.5-9B",
        model_revision: str = "main",
        model_dir: Optional[str] = None,
        max_context_length: int = 4096,
        ambiguity_margin_threshold: float = 0.05,
    ):
        super().__init__(model_id=model_id, model_revision=model_revision)
        self.model_dir = model_dir or _resolve_qwen_model_dir()
        self.max_context_length = max_context_length
        self.ambiguity_threshold = ambiguity_margin_threshold
        _ensure_simple_jev_imported()

    @classmethod
    def is_loaded(cls) -> bool:
        """Check if model weights are currently resident in GPU memory."""
        return cls._is_loaded and cls._shared_model is not None

    def load_model(self) -> None:
        """Initialize tokenizer and model weights once. Idempotent and thread-safe."""
        if OfficialSimpleJEVAdapter.is_loaded():
            return

        now = time.time()
        with OfficialSimpleJEVAdapter._shared_lock:
            if OfficialSimpleJEVAdapter.is_loaded():
                return

            if (
                OfficialSimpleJEVAdapter._load_error is not None
                and (now - OfficialSimpleJEVAdapter._last_load_attempt_time) < OfficialSimpleJEVAdapter._load_cooldown_seconds
            ):
                remaining = int(OfficialSimpleJEVAdapter._load_cooldown_seconds - (now - OfficialSimpleJEVAdapter._last_load_attempt_time))
                raise RuntimeError(
                    f"Model loading suppressed due to recent failure ({remaining}s cooldown remaining): "
                    f"{OfficialSimpleJEVAdapter._load_error}"
                )

            OfficialSimpleJEVAdapter._last_load_attempt_time = now
            logger.info("Initializing Official Simple JEV Adapter for Qwen3.5-9B in 4-bit NF4...")
            start_load = time.perf_counter()

            try:
                import torch
                from transformers import (
                    AutoConfig,
                    AutoTokenizer,
                    BitsAndBytesConfig,
                    Qwen3_5ForCausalLM,
                )
            except ImportError as exc:
                err_msg = f"Required ML dependencies missing: {exc}. Install torch, transformers, bitsandbytes."
                OfficialSimpleJEVAdapter._load_error = err_msg
                logger.error(err_msg)
                raise RuntimeError(err_msg) from exc

            if not torch.cuda.is_available():
                err_msg = "CUDA is not available. Qwen3.5-9B 4-bit NF4 requires an NVIDIA GPU (RTX 4060)."
                OfficialSimpleJEVAdapter._load_error = err_msg
                logger.error(err_msg)
                raise RuntimeError(err_msg)

            if not os.path.isdir(self.model_dir):
                err_msg = f"Model checkpoint directory not found: {self.model_dir}"
                OfficialSimpleJEVAdapter._load_error = err_msg
                logger.error(err_msg)
                raise FileNotFoundError(err_msg)

            try:
                # 1. Load tokenizer offline
                tokenizer = AutoTokenizer.from_pretrained(
                    self.model_dir, local_files_only=True
                )

                # 2. Configure 4-bit NF4 quantization
                quant_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_compute_dtype=torch.float16,
                )

                # 3. Load text causal LM backbone
                model = Qwen3_5ForCausalLM.from_pretrained(
                    self.model_dir,
                    local_files_only=True,
                    quantization_config=quant_config,
                    device_map={"": 0},
                    dtype=torch.float16,
                    low_cpu_mem_usage=True,
                )
                model.eval()

                # 4. Resolve official prompt policy and compiler
                _ensure_simple_jev_imported()
                try:
                    from hf_prompt_policies import resolve_prompt_policy
                    from hf_server import PromptCompiler
                    config = AutoConfig.from_pretrained(self.model_dir, local_files_only=True)
                    policy, _ = resolve_prompt_policy(config, requested=None)
                    compiler = PromptCompiler(
                        tokenizer,
                        max_tokens=self.max_context_length,
                        prompt_policy=policy,
                        processor=None,
                    )
                except Exception as comp_err:
                    logger.warning("Could not initialize official PromptCompiler (%s), using fallback.", comp_err)
                    policy = "baseline"
                    compiler = None

                OfficialSimpleJEVAdapter._shared_model = model
                OfficialSimpleJEVAdapter._shared_tokenizer = tokenizer
                OfficialSimpleJEVAdapter._shared_compiler = compiler
                OfficialSimpleJEVAdapter._shared_policy = policy
                OfficialSimpleJEVAdapter._is_loaded = True
                OfficialSimpleJEVAdapter._load_error = None

                elapsed = time.perf_counter() - start_load
                mem_gib = torch.cuda.memory_allocated() / (1024**3)
                logger.info("Qwen3.5-9B 4-bit NF4 loaded in %.2fs. VRAM allocated: %.2f GiB", elapsed, mem_gib)

            except Exception as load_exc:
                OfficialSimpleJEVAdapter._is_loaded = False
                OfficialSimpleJEVAdapter._shared_model = None
                OfficialSimpleJEVAdapter._load_error = str(load_exc)
                logger.error("Failed to load Qwen3.5-9B in 4-bit NF4: %s", load_exc)
                raise RuntimeError(f"JEV Model Initialization Failed: {load_exc}") from load_exc

    def get_model_info(self) -> Dict[str, Any]:
        """Return operational metadata describing model, precision, device, and memory status."""
        vram_allocated_gib = 0.0
        vram_peak_gib = 0.0
        device_name = "unavailable"
        try:
            import torch
            if torch.cuda.is_available():
                device_name = torch.cuda.get_device_name(0)
                vram_allocated_gib = round(torch.cuda.memory_allocated() / (1024**3), 2)
                vram_peak_gib = round(torch.cuda.max_memory_allocated() / (1024**3), 2)
        except Exception:
            pass

        return {
            "model_id": self.model_id,
            "model_revision": self.model_revision,
            "model_dir": self.model_dir,
            "backend": "official_simple_jev_transformers",
            "quantization": "4-bit_nf4",
            "compute_dtype": "float16",
            "device": device_name,
            "vram_allocated_gib": vram_allocated_gib,
            "vram_peak_gib": vram_peak_gib,
            "is_loaded": OfficialSimpleJEVAdapter.is_loaded(),
            "prompt_policy": OfficialSimpleJEVAdapter._shared_policy,
            "max_context_length": self.max_context_length,
            "last_load_error": OfficialSimpleJEVAdapter._load_error,
        }

    def _validate_input_payload(
        self,
        instructions: str,
        criteria: Dict[str, Optional[str]],
        state: Optional[Union[str, Dict[str, Any]]],
    ) -> None:
        """Validate input payload and reject unsupported multimodal/tool structures."""
        if not instructions or not instructions.strip():
            raise ValueError("JEV instructions string must not be empty.")
        if not criteria or len(criteria) < 2:
            raise ValueError("JEV choice classification requires at least 2 distinct criteria options.")

        # Reject multimodal media or tool structures
        if isinstance(state, dict):
            if any(k in state for k in ("image", "image_url", "images", "audio", "video", "tools", "tool_calls")):
                raise ValueError("Official Simple JEV Qwen 4-bit adapter supports text-only requests. Images/tools are unsupported.")

    def _check_insufficient_evidence(self, state: Optional[Union[str, Dict[str, Any]]]) -> bool:
        """Determine if context provides inadequate factual evidence for reliable classification."""
        if state is None:
            return True
        if isinstance(state, str):
            clean = state.strip()
            return len(clean) == 0 or clean.lower() in ("none", "null", "n/a", "no data")
        if isinstance(state, dict):
            if state.get("insufficient_evidence") is True:
                return True
            # Check if all content values are empty
            non_empty_values = [
                v for k, v in state.items()
                if v not in (None, "", [], {}, 0) and k not in ("ticker", "as_of_date")
            ]
            return len(non_empty_values) == 0
        return False

    def extract_branch_logits(
        self,
        prompt_prefix: str,
        question_text: str,
        answer_prefix: str,
        output_labels: tuple[str, ...],
    ) -> Dict[str, float]:
        """Run single forward pass and extract raw logits for output labels."""
        if not OfficialSimpleJEVAdapter.is_loaded():
            self.load_model()

        import torch

        model = OfficialSimpleJEVAdapter._shared_model
        tokenizer = OfficialSimpleJEVAdapter._shared_tokenizer
        device = model.get_input_embeddings().weight.device

        # Format prompt with chat template
        messages = [
            {"role": "system", "content": prompt_prefix},
            {"role": "user", "content": question_text},
        ]
        try:
            rendered = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
            full_text = rendered + answer_prefix
        except Exception:
            full_text = f"{prompt_prefix}\n\n{question_text}\n\n{answer_prefix}"

        input_ids = tokenizer.encode(full_text, add_special_tokens=False)
        input_tensor = torch.tensor([input_ids], dtype=torch.long, device=device)
        attention_mask = torch.ones_like(input_tensor)

        try:
            with OfficialSimpleJEVAdapter._shared_lock:
                with torch.inference_mode():
                    out = model(
                        input_ids=input_tensor,
                        attention_mask=attention_mask,
                        logits_to_keep=1,
                        use_cache=False,
                    )
                    last_logits = out.logits[0, -1]  # shape: (vocab_size,)


            # Verify BPE boundary and resolve token IDs
            results: Dict[str, float] = {}
            for lbl in output_labels:
                extended = tokenizer.encode(full_text + lbl, add_special_tokens=False)
                if len(extended) == len(input_ids) + 1 and extended[:-1] == input_ids:
                    t_id = extended[-1]
                else:
                    # Isolated encoding fallback
                    t_id = tokenizer.encode(lbl, add_special_tokens=False)[-1]
                results[lbl] = float(last_logits[t_id].detach().cpu().item())

            del out, input_tensor, attention_mask, last_logits
            return results

        except torch.cuda.OutOfMemoryError as oom_err:
            logger.error("GPU Out-of-Memory during JEV logit extraction: %s", oom_err)
            torch.cuda.empty_cache()
            raise RuntimeError(f"GPU OOM during JEV inference: {oom_err}") from oom_err

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
        """Execute single choice classification with strict error and diagnostic handling."""
        t0 = time.perf_counter()
        evidence_list = evidence_ids or []

        # 1. Validate input schema and reject unsupported inputs
        self._validate_input_payload(instructions, criteria, state)

        # 2. Check for insufficient evidence
        if self._check_insufficient_evidence(state):
            latency = (time.perf_counter() - t0) * 1000.0
            uniform_prob = round(1.0 / len(criteria), 4)
            scores = {label: uniform_prob for label in criteria}
            return PredictionResult(
                task_name=task_name,
                predicted_label="Insufficient Evidence" if "Insufficient Evidence" in criteria else list(criteria.keys())[0],
                class_scores=scores,
                confidence=0.0,
                is_calibrated=False,
                margin=0.0,
                entropy=round(math.log(len(criteria)), 4),
                raw_logits=None,
                evidence_ids=evidence_list,
                model_id=self.model_id,
                model_revision=self.model_revision,
                classifier_version="jev-v1.0",
                prompt_hash="0" * 64,
                dataset_version=dataset_version,
                latency_ms=round(latency, 2),
                error_status="Insufficient Evidence: context lacks verifiable market disclosures or telemetry.",
                explanation="No actionable financial telemetry was supplied. Classification aborted to prevent hallucination.",
            )

        # 3. Ensure model is loaded
        if not OfficialSimpleJEVAdapter.is_loaded():
            self.load_model()

        # 4. Prepare prompt using official JEV compiler if available
        _ensure_simple_jev_imported()
        compiler = OfficialSimpleJEVAdapter._shared_compiler
        labels = tuple(criteria.keys())

        try:
            if compiler is not None:
                from common import ClassifierRequest as JEVRequest
                jev_req = JEVRequest.model_validate({
                    "model": self.model_id,
                    "state": state,
                    "questions": {
                        task_name: {
                            "type": "choice",
                            "instructions": instructions,
                            "criteria": criteria,
                        }
                    },
                })
                compiled = compiler.compile(jev_req)
                branch = compiled.branches[0]
                plan_question = compiled.plan.questions[0]
                output_labels = plan_question.output_labels
                answer_labels = plan_question.answer_labels

                # Forward pass
                import torch
                model = OfficialSimpleJEVAdapter._shared_model
                device = model.get_input_embeddings().weight.device
                input_tensor = torch.tensor([branch.token_ids], dtype=torch.long, device=device)
                mask = torch.ones_like(input_tensor)

                try:
                    with OfficialSimpleJEVAdapter._shared_lock:
                        with torch.inference_mode():
                            out = model(input_ids=input_tensor, attention_mask=mask, logits_to_keep=1, use_cache=False)
                            last_logits = out.logits[0, -1]
                            raw_selected = last_logits[branch.output_ids].float().cpu()

                    del out, input_tensor, mask, last_logits

                except torch.cuda.OutOfMemoryError as oom:
                    logger.error("CUDA OOM in JEV predict_choice: %s", oom)
                    torch.cuda.empty_cache()
                    latency = (time.perf_counter() - t0) * 1000.0
                    return PredictionResult(
                        task_name=task_name,
                        predicted_label="GPU OOM Error",
                        class_scores={lbl: 0.0 for lbl in criteria},
                        confidence=0.0,
                        is_calibrated=False,
                        evidence_ids=evidence_list,
                        model_id=self.model_id,
                        classifier_version="jev-v1.0",
                        prompt_hash="error_oom",
                        latency_ms=round(latency, 2),
                        error_status=f"GPU Out-of-Memory error: {oom}",
                    )

                # Numerically stable softmax
                z = raw_selected.numpy()
                z_shifted = z - z.max()
                exp_z = [math.exp(val) for val in z_shifted]
                sum_exp = sum(exp_z)
                probs = [ez / sum_exp for ez in exp_z]

                # Map back to public answer labels
                label_prob_map = {lbl: float(p) for lbl, p in zip(answer_labels, probs)}
                raw_logit_map = {lbl: float(val) for lbl, val in zip(answer_labels, z)} if raw_logits else None

                winner_idx = int(raw_selected.argmax().item())
                winner_label = answer_labels[winner_idx]
                confidence = float(probs[winner_idx])

                sorted_probs = sorted(probs, reverse=True)
                margin = float(sorted_probs[0] - sorted_probs[1]) if len(sorted_probs) > 1 else 1.0
                entropy = float(-sum(p * math.log(p) for p in probs if p > 0))

                prompt_hash = hashlib.sha256(
                    OfficialSimpleJEVAdapter._shared_tokenizer.decode(branch.token_ids).encode("utf-8")
                ).hexdigest()

            else:
                # Standalone fallback path
                res = super().predict_choice(
                    task_name=task_name,
                    instructions=instructions,
                    criteria=criteria,
                    state=state,
                    evidence_ids=evidence_ids,
                    dataset_version=dataset_version,
                    raw_logits=raw_logits,
                )
                if res.margin is not None and res.margin < self.ambiguity_threshold:
                    res.explanation = (
                        f"Ambiguous classification: Top margin is {res.margin:.4f} "
                        f"(below {self.ambiguity_threshold} certainty threshold). Predictions are near-tie."
                    )
                return res

        except Exception as inf_err:
            logger.error("JEV prediction failed: %s", inf_err)
            latency = (time.perf_counter() - t0) * 1000.0
            return PredictionResult(
                task_name=task_name,
                predicted_label="Inference Error",
                class_scores={lbl: 0.0 for lbl in criteria},
                confidence=0.0,
                is_calibrated=False,
                evidence_ids=evidence_list,
                model_id=self.model_id,
                classifier_version="jev-v1.0",
                prompt_hash="error",
                latency_ms=round(latency, 2),
                error_status=f"Inference Failure: {inf_err}",
            )

        latency = (time.perf_counter() - t0) * 1000.0

        # Ambiguity check
        explanation = None
        if margin < self.ambiguity_threshold:
            explanation = (
                f"Ambiguous classification: Top margin is {margin:.4f} "
                f"(below {self.ambiguity_threshold} certainty threshold). Predictions are near-tie."
            )

        return PredictionResult(
            task_name=task_name,
            predicted_label=winner_label,
            class_scores=label_prob_map,
            confidence=round(confidence, 4),
            is_calibrated=False,  # Raw label probability, NOT calibrated confidence
            margin=round(margin, 4),
            entropy=round(entropy, 4),
            raw_logits=raw_logit_map,
            evidence_ids=evidence_list,
            model_id=self.model_id,
            model_revision=self.model_revision,
            classifier_version="jev-v1.0",
            prompt_hash=prompt_hash,
            dataset_version=dataset_version,
            latency_ms=round(latency, 2),
            explanation=explanation,
        )
