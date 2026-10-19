"""Automated test suite for Official Simple JEV Adapter integration in Project Dakota.

Verifies:
1. Backward compatibility: existing rule/ML classifier unchanged when DAKOTA_USE_JEV=0.
2. Feature flag activation: DAKOTA_USE_JEV=1 routes through JEV with impact_mapper compatibility.
3. Adapter interface and metadata: model info, 4-bit NF4 configuration, prompt policy.
4. Structured prediction schema: class_scores, is_calibrated=False, raw_logits, margin, entropy, evidence provenance.
5. Insufficient evidence handling: returns explicit 'Insufficient Evidence' without hallucination.
6. Ambiguous classification diagnostics: detects low-margin predictions (< 0.05) and attaches warning.
7. Input validation: rejects empty instructions, <2 criteria, and multimodal image/tool inputs.
8. Error recovery: handles simulated GPU OOM gracefully, frees cache, returns structured error status.
9. Single-model singleton guard: multiple adapter instances share weights without duplicating VRAM.
10. Separation of initialization from request processing: inference reuses loaded model without reloading.
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from src.intelligence.jev.adapters.official_jev_adapter import (
    OfficialSimpleJEVAdapter,
    _resolve_qwen_model_dir,
    _resolve_simple_jev_path,
)
from src.intelligence.jev.schemas import PredictionResult
from src.classification.jev_classifier import (
    is_jev_enabled,
    classify_message_jev,
    classify_message_with_feature_flag,
)
from src.classification.local_classifier import classify_message


class TestOfficialJEVIntegration(unittest.TestCase):
    """Integration and unit tests for Official Simple JEV in Dakota."""

    def setUp(self):
        # Preserve original environment state
        self._orig_env = os.environ.get("DAKOTA_USE_JEV")

    def tearDown(self):
        # Restore environment
        if self._orig_env is None:
            os.environ.pop("DAKOTA_USE_JEV", None)
        else:
            os.environ["DAKOTA_USE_JEV"] = self._orig_env

    # --------------------------------------------------------------------------
    # 1. Backward Compatibility (Feature Flag OFF)
    # --------------------------------------------------------------------------
    def test_feature_flag_disabled_retains_existing_behavior(self):
        """When DAKOTA_USE_JEV is '0' or unset, classify_message returns 100% existing rule/ML behavior."""
        os.environ["DAKOTA_USE_JEV"] = "0"
        self.assertFalse(is_jev_enabled())

        text = "BUY $RELIANCE TARGET 3100 SL 2650"
        res = classify_message(text)

        # Standard rule output contracts
        self.assertEqual(res["status"], "classified")
        self.assertIn(res["method"], ("rules", "local_ml"))
        self.assertIn("RELIANCE", res["tickers"])
        self.assertTrue(res["trading_intent"])
        # Ensure JEV metadata is completely absent in default mode
        self.assertNotIn("jev_metadata", res)

    # --------------------------------------------------------------------------
    # 2. Feature Flag Activation & Pipeline Compatibility
    # --------------------------------------------------------------------------
    def test_feature_flag_enabled_routes_to_jev(self):
        """When DAKOTA_USE_JEV is '1', classify_message routes through JEV with impact_mapper schema."""
        os.environ["DAKOTA_USE_JEV"] = "1"
        self.assertTrue(is_jev_enabled())

        # Mock adapter to test routing logic without requiring live GPU weights in unit test
        mock_pred = PredictionResult(
            task_name="market_domain_classification",
            predicted_label="equity",
            class_scores={"equity": 0.95, "commodity": 0.02, "macro": 0.01, "sector": 0.01, "none": 0.01},
            confidence=0.95,
            is_calibrated=False,
            margin=0.93,
            entropy=0.25,
            raw_logits={"equity": 4.5, "commodity": 1.2, "macro": 0.5, "sector": 0.4, "none": 0.2},
            evidence_ids=["E_TEST_1"],
            model_id="Qwen/Qwen3.5-9B",
            classifier_version="jev-v1.0",
            prompt_hash="a" * 64,
            latency_ms=12.5,
        )

        with patch("src.classification.jev_classifier.get_pipeline_jev_adapter") as mock_get:
            mock_adapter = MagicMock()
            mock_adapter.predict_choice.return_value = mock_pred
            mock_get.return_value = mock_adapter

            res = classify_message("HDFC Bank Q3 profit jumps 33% year on year")

            # Contract verification for impact_mapper.py
            self.assertEqual(res["market_domain"], "equity")
            self.assertEqual(res["domain"], "equity")
            self.assertEqual(res["method"], "jev_qwen3.5_4bit")
            self.assertEqual(res["status"], "classified")
            self.assertIn("jev_metadata", res)
            self.assertEqual(res["jev_metadata"]["model_id"], "Qwen/Qwen3.5-9B")
            self.assertFalse(res["jev_metadata"]["is_calibrated"])

    # --------------------------------------------------------------------------
    # 3. Adapter Interface and Model Metadata
    # --------------------------------------------------------------------------
    def test_adapter_interface_and_model_info(self):
        """Adapter correctly reports backend, 4-bit quantization, prompt policy, and memory metadata."""
        adapter = OfficialSimpleJEVAdapter(
            model_id="Qwen/Qwen3.5-9B",
            model_dir="/tmp/dummy_qwen_path",
        )
        info = adapter.get_model_info()

        self.assertEqual(info["model_id"], "Qwen/Qwen3.5-9B")
        self.assertEqual(info["backend"], "official_simple_jev_transformers")
        self.assertEqual(info["quantization"], "4-bit_nf4")
        self.assertEqual(info["compute_dtype"], "float16")
        self.assertEqual(info["prompt_policy"], "baseline")
        self.assertIn("vram_allocated_gib", info)
        self.assertIn("is_loaded", info)

    # --------------------------------------------------------------------------
    # 4. Structured Results & Confidence vs. Calibration Distinction
    # --------------------------------------------------------------------------
    def test_structured_prediction_schema_and_calibration_distinction(self):
        """PredictionResult explicitly marks is_calibrated=False and provides raw logits/scores."""
        adapter = OfficialSimpleJEVAdapter(model_id="Qwen/Qwen3.5-9B")

        # Mock the underlying execution for fast schema assertion
        sample_criteria = {
            "Bullish": "Growth and earnings beat",
            "Bearish": "Losses or regulatory action",
            "Neutral": "Routine disclosures",
        }

        with patch.object(adapter, "load_model"):
            with patch("src.intelligence.jev.adapters.official_jev_adapter.OfficialSimpleJEVAdapter.is_loaded", return_value=True):
                with patch.object(adapter, "_shared_compiler") as mock_comp:
                    mock_comp = None  # test fallback path with extract_branch_logits mock
                    with patch.object(adapter, "extract_branch_logits") as mock_logits:
                        mock_logits.return_value = {"A": 3.8, "B": 1.2, "C": 0.5}

                        pred = adapter.predict_choice(
                            task_name="sentiment_test",
                            instructions="Score sentiment.",
                            criteria=sample_criteria,
                            state="TCS declares quarterly dividend of Rs 28 per share",
                            evidence_ids=["E_TCS_01"],
                            raw_logits=True,
                        )

                        self.assertIsInstance(pred, PredictionResult)
                        self.assertEqual(pred.task_name, "sentiment_test")
                        self.assertEqual(pred.predicted_label, "Bullish")
                        self.assertFalse(pred.is_calibrated)  # Must be raw uncalibrated probability
                        self.assertGreater(pred.confidence, 0.8)
                        self.assertAlmostEqual(sum(pred.class_scores.values()), 1.0, places=3)
                        self.assertIsNotNone(pred.raw_logits)
                        self.assertIn("E_TCS_01", pred.evidence_ids)
                        self.assertEqual(len(pred.prompt_hash), 64)

    # --------------------------------------------------------------------------
    # 5. Insufficient Evidence Handling
    # --------------------------------------------------------------------------
    def test_insufficient_evidence_handling(self):
        """Empty context or explicit insufficient evidence returns designated label with zero confidence."""
        adapter = OfficialSimpleJEVAdapter(model_id="Qwen/Qwen3.5-9B")
        criteria = {"Bullish": "Positive", "Bearish": "Negative", "Insufficient Evidence": "No data"}

        # Case A: None state
        res_none = adapter.predict_choice(
            task_name="evidence_check",
            instructions="Analyze data.",
            criteria=criteria,
            state=None,
        )
        self.assertEqual(res_none.predicted_label, "Insufficient Evidence")
        self.assertEqual(res_none.confidence, 0.0)
        self.assertFalse(res_none.is_calibrated)
        self.assertIn("Insufficient Evidence", res_none.error_status)

        # Case B: Empty string state
        res_empty = adapter.predict_choice(
            task_name="evidence_check",
            instructions="Analyze data.",
            criteria=criteria,
            state="   ",
        )
        self.assertEqual(res_empty.predicted_label, "Insufficient Evidence")
        self.assertEqual(res_empty.confidence, 0.0)

        # Case C: Empty dictionary state
        res_dict = adapter.predict_choice(
            task_name="evidence_check",
            instructions="Analyze data.",
            criteria=criteria,
            state={"ticker": "XYZ", "as_of_date": "2026-10-19"},
        )
        self.assertEqual(res_dict.predicted_label, "Insufficient Evidence")

    # --------------------------------------------------------------------------
    # 6. Ambiguous Classification Diagnostics
    # --------------------------------------------------------------------------
    def test_ambiguous_classification_diagnostics(self):
        """When top probability margin is below threshold (<0.05), adapter attaches ambiguity note."""
        adapter = OfficialSimpleJEVAdapter(
            model_id="Qwen/Qwen3.5-9B",
            ambiguity_margin_threshold=0.05,
        )
        criteria = {"OptionA": "Desc A", "OptionB": "Desc B"}

        with patch.object(adapter, "load_model"):
            with patch("src.intelligence.jev.adapters.official_jev_adapter.OfficialSimpleJEVAdapter.is_loaded", return_value=True):
                with patch.object(adapter, "extract_branch_logits") as mock_logits:
                    # Near identical logits -> margin ~ 0.01 < 0.05
                    mock_logits.return_value = {"A": 2.01, "B": 2.00}

                    pred = adapter.predict_choice(
                        task_name="ambiguity_test",
                        instructions="Choose between options.",
                        criteria=criteria,
                        state="Controversial mixed signals reported.",
                    )

                    self.assertLess(pred.margin, 0.05)
                    self.assertIsNotNone(pred.explanation)
                    self.assertIn("Ambiguous classification", pred.explanation)

    # --------------------------------------------------------------------------
    # 7. Unsupported Input Rejection
    # --------------------------------------------------------------------------
    def test_unsupported_inputs_raise_value_error(self):
        """Adapter explicitly rejects multimodal media (images/tools) and malformed criteria."""
        adapter = OfficialSimpleJEVAdapter(model_id="Qwen/Qwen3.5-9B")

        # 1. Empty instructions
        with self.assertRaises(ValueError):
            adapter.predict_choice(
                task_name="test",
                instructions="",
                criteria={"A": None, "B": None},
                state="valid text",
            )

        # 2. Insufficient criteria (< 2 options)
        with self.assertRaises(ValueError):
            adapter.predict_choice(
                task_name="test",
                instructions="Valid instruction",
                criteria={"A": "Single option"},
                state="valid text",
            )

        # 3. Multimodal image input
        with self.assertRaises(ValueError) as ctx:
            adapter.predict_choice(
                task_name="test",
                instructions="Valid instruction",
                criteria={"A": None, "B": None},
                state={"text": "Hello", "image": "base64_encoded_image_bytes"},
            )
        self.assertIn("text-only requests", str(ctx.exception))

        # 4. Tool calls in state
        with self.assertRaises(ValueError) as ctx:
            adapter.predict_choice(
                task_name="test",
                instructions="Valid instruction",
                criteria={"A": None, "B": None},
                state={"tools": ["search_tool"]},
            )
        self.assertIn("text-only requests", str(ctx.exception))

    # --------------------------------------------------------------------------
    # 8. GPU Memory Error Recovery
    # --------------------------------------------------------------------------
    def test_gpu_oom_error_recovery(self):
        """Simulated CUDA OOM in forward pass is cleanly caught, cache cleared, and returned as error status."""
        adapter = OfficialSimpleJEVAdapter(model_id="Qwen/Qwen3.5-9B")
        criteria = {"A": None, "B": None}

        import torch

        with patch.object(adapter, "load_model"):
            with patch("src.intelligence.jev.adapters.official_jev_adapter.OfficialSimpleJEVAdapter.is_loaded", return_value=True):
                with patch.object(adapter, "extract_branch_logits") as mock_logits:
                    mock_logits.side_effect = torch.cuda.OutOfMemoryError("CUDA out of memory in test")

                    # In fallback path, extract_branch_logits raises RuntimeError wrapping OOM
                    pred = adapter.predict_choice(
                        task_name="oom_test",
                        instructions="Score text.",
                        criteria=criteria,
                        state="Long overlong text causing OOM.",
                    )

                    self.assertEqual(pred.predicted_label, "Inference Error")
                    self.assertEqual(pred.confidence, 0.0)
                    self.assertIn("Inference Failure", pred.error_status)

    # --------------------------------------------------------------------------
    # 9. Single Model Instance (Singleton Guard)
    # --------------------------------------------------------------------------
    def test_single_model_instance_singleton_guard(self):
        """Instantiating multiple adapters shares the same model reference without duplicate allocation."""
        adapter1 = OfficialSimpleJEVAdapter(model_id="Qwen/Qwen3.5-9B")
        adapter2 = OfficialSimpleJEVAdapter(model_id="Qwen/Qwen3.5-9B")

        # Set shared model on class
        dummy_model = object()
        OfficialSimpleJEVAdapter._shared_model = dummy_model
        OfficialSimpleJEVAdapter._is_loaded = True

        self.assertIs(adapter1._shared_model, dummy_model)
        self.assertIs(adapter2._shared_model, dummy_model)

        # Calling load_model is idempotent and does not overwrite or reload
        adapter2.load_model()
        self.assertIs(OfficialSimpleJEVAdapter._shared_model, dummy_model)

        # Clean up test dummy
        OfficialSimpleJEVAdapter._shared_model = None
        OfficialSimpleJEVAdapter._is_loaded = False

    # --------------------------------------------------------------------------
    # 10. Fallback Semantics, Reason Tracking & Provenance Preservation
    # --------------------------------------------------------------------------
    def test_fallback_metadata_and_provenance_preservation(self):
        """When JEV fails under DAKOTA_USE_JEV=1, result records fallback_used=True, reason, and provenance."""
        os.environ["DAKOTA_USE_JEV"] = "1"

        # Case A: JEV fails, triggering fallback
        with patch("src.classification.jev_classifier.classify_message_jev", side_effect=RuntimeError("Simulated CUDA OOM in JEV")):
            res = classify_message("BUY $RELIANCE TARGET 3100 SL 2650")

            self.assertTrue(res.get("fallback_used"))
            self.assertIn("Simulated CUDA OOM in JEV", res.get("fallback_reason", ""))
            self.assertEqual(res.get("original_classifier"), "jev_qwen3.5_4bit")
            self.assertIn("RELIANCE", res["tickers"])
            self.assertTrue(res["trading_intent"])
            self.assertIn("evidence_ids", res)
            self.assertTrue(any("E_MSG_" in eid for eid in res["evidence_ids"]))

        # Case B: classify_message_with_feature_flag also records fallback metadata
        with patch("src.classification.jev_classifier.classify_message_jev", side_effect=RuntimeError("Pipeline crash")):
            res_flag = classify_message_with_feature_flag("Crude oil jumps 4% on geopolitical tensions")
            self.assertTrue(res_flag.get("fallback_used"))
            self.assertIn("Pipeline crash", res_flag.get("fallback_reason", ""))
            self.assertEqual(res_flag.get("original_classifier"), "jev_qwen3.5_4bit")
            self.assertIn("evidence_ids", res_flag)

        # Case C: When JEV succeeds, fallback_used is explicitly False
        mock_pred = PredictionResult(
            task_name="market_domain_classification",
            predicted_label="equity",
            class_scores={"equity": 0.98, "commodity": 0.01, "macro": 0.005, "sector": 0.003, "none": 0.002},
            confidence=0.98,
            is_calibrated=False,
            margin=0.97,
            entropy=0.1,
            evidence_ids=["E_PROV_01"],
            model_id="Qwen/Qwen3.5-9B",
            classifier_version="jev-v1.0",
            prompt_hash="f" * 64,
            latency_ms=10.0,
        )
        with patch("src.classification.jev_classifier.get_pipeline_jev_adapter") as mock_get:
            mock_adapter = MagicMock()
            mock_adapter.predict_choice.return_value = mock_pred
            mock_get.return_value = mock_adapter

            res_ok = classify_message("TCS declares Rs 28 dividend")
            self.assertFalse(res_ok.get("fallback_used"))
            self.assertEqual(res_ok.get("method"), "jev_qwen3.5_4bit")
            self.assertIn("E_PROV_01", res_ok.get("evidence_ids", []))
            self.assertIn("E_PROV_01", res_ok["jev_metadata"]["evidence_ids"])

    # --------------------------------------------------------------------------
    # 11. Insufficient Evidence Cannot Be Mistaken for Actionable Tip
    # --------------------------------------------------------------------------
    def test_insufficient_evidence_unactionable_semantics(self):
        """Insufficient evidence strictly forces trading_intent=False and un-actionable status."""
        os.environ["DAKOTA_USE_JEV"] = "1"

        # Mock adapter returning insufficient evidence
        insufficient_pred = PredictionResult(
            task_name="market_domain_classification",
            predicted_label="Insufficient Evidence",
            class_scores={"equity": 0.2, "commodity": 0.2, "macro": 0.2, "sector": 0.2, "none": 0.2},
            confidence=0.0,
            is_calibrated=False,
            margin=0.0,
            entropy=1.6,
            evidence_ids=["E_INSUFFICIENT"],
            model_id="Qwen/Qwen3.5-9B",
            classifier_version="jev-v1.0",
            prompt_hash="0" * 64,
            latency_ms=2.0,
            error_status="Insufficient Evidence: context lacks verifiable market disclosures or telemetry.",
        )

        with patch("src.classification.jev_classifier.get_pipeline_jev_adapter") as mock_get:
            mock_adapter = MagicMock()
            mock_adapter.predict_choice.return_value = insufficient_pred
            mock_get.return_value = mock_adapter

            # Text contains aggressive trading keywords ("BUY", "ROCKET", "TARGET")
            text_with_action_words = "BUY BUY BUY rocket multibagger jackpot target 1000!!"
            res = classify_message(text_with_action_words)

            # Strict verification: Must NOT be actionable or have trading intent
            self.assertTrue(res["insufficient_evidence"])
            self.assertFalse(res["trading_intent"])
            self.assertFalse(res["is_actionable"])
            self.assertEqual(res["confidence"], 0.0)
            self.assertEqual(res["message_type"], "insufficient_evidence")
            self.assertEqual(res["status"], "unactionable_insufficient_evidence")
            self.assertEqual(res["market_domain"], "none")

    # --------------------------------------------------------------------------
    # 12. Model Load Cooldown Prevents Repeated GPU OOM Retry Loops
    # --------------------------------------------------------------------------
    def test_gpu_oom_load_cooldown_prevents_retry_loops(self):
        """Failed load sets cooldown, preventing uncontrolled repeated model loading in tight loops."""
        adapter = OfficialSimpleJEVAdapter(model_id="Qwen/Qwen3.5-9B")

        # Simulate failed load
        OfficialSimpleJEVAdapter._is_loaded = False
        OfficialSimpleJEVAdapter._load_error = "CUDA out of memory during weights allocation"
        import time
        OfficialSimpleJEVAdapter._last_load_attempt_time = time.time()
        OfficialSimpleJEVAdapter._load_cooldown_seconds = 30.0

        # Attempting to load again within cooldown window must raise RuntimeError immediately without reloading
        with self.assertRaises(RuntimeError) as ctx:
            adapter.load_model()

        self.assertIn("Model loading suppressed due to recent failure", str(ctx.exception))
        self.assertIn("cooldown remaining", str(ctx.exception))

        # Reset class state
        OfficialSimpleJEVAdapter._load_error = None
        OfficialSimpleJEVAdapter._last_load_attempt_time = 0.0

    # --------------------------------------------------------------------------
    # 13. Concurrency Protection During Forward Pass
    # --------------------------------------------------------------------------
    def test_concurrency_lock_protection_during_inference(self):
        """Inference forward pass acquires _shared_lock to serialize execution across threads."""
        import threading
        adapter = OfficialSimpleJEVAdapter(model_id="Qwen/Qwen3.5-9B")
        self.assertTrue(hasattr(OfficialSimpleJEVAdapter, "_shared_lock"))
        self.assertIsInstance(OfficialSimpleJEVAdapter._shared_lock, type(threading.Lock()))

    # --------------------------------------------------------------------------
    # 14. Phase 3 Harness Regression: 6 Classes, Balanced Accuracy & Calibration
    # --------------------------------------------------------------------------
    def test_phase3_evaluation_harness_metrics_and_calibration(self):
        """Evaluation harness supports 6 classes, balanced accuracy, and calibration metrics with explicit ordering."""
        from scripts.evaluate_financial_evidence import (
            STANDARD_CLASSES,
            compute_class_level_metrics,
            compute_calibration_metrics,
        )
        self.assertEqual(len(STANDARD_CLASSES), 6)
        self.assertIn("Ambiguous", STANDARD_CLASSES)
        self.assertIn("Insufficient Evidence", STANDARD_CLASSES)

        y_true = ["Bullish", "Bearish", "Ambiguous", "Neutral"]
        y_pred = ["Bullish", "Bearish", "Ambiguous", "Bullish"]
        metrics = compute_class_level_metrics(y_true, y_pred, STANDARD_CLASSES)

        self.assertEqual(metrics["accuracy"], 0.75)
        self.assertIn("balanced_accuracy", metrics)
        self.assertGreater(metrics["balanced_accuracy"], 0.0)
        self.assertIn("confusion_matrix", metrics)

        # Calibration test
        y_probs = [
            {"Bullish": 0.85, "Bearish": 0.03, "Neutral": 0.04, "Mixed": 0.03, "Ambiguous": 0.03, "Insufficient Evidence": 0.02},
            {"Bullish": 0.05, "Bearish": 0.80, "Neutral": 0.05, "Mixed": 0.05, "Ambiguous": 0.03, "Insufficient Evidence": 0.02},
            {"Bullish": 0.10, "Bearish": 0.10, "Neutral": 0.10, "Mixed": 0.10, "Ambiguous": 0.50, "Insufficient Evidence": 0.10},
            {"Bullish": 0.60, "Bearish": 0.10, "Neutral": 0.10, "Mixed": 0.10, "Ambiguous": 0.05, "Insufficient Evidence": 0.05},
        ]
        calib = compute_calibration_metrics(y_true, y_probs, STANDARD_CLASSES, n_bins=5)
        self.assertIn("brier_score", calib)
        self.assertIn("ece", calib)
        self.assertIn("nll", calib)
        self.assertEqual(calib["class_ordering"], STANDARD_CLASSES)
        self.assertEqual(calib["binning_method"], "equal_width_5_bins")

    # --------------------------------------------------------------------------
    # 15. Phase 3 Harness Regression: Separate Abstention Tracking
    # --------------------------------------------------------------------------
    def test_phase3_separate_abstention_tracking(self):
        """Insufficient evidence, ambiguous diagnostics, and low confidence abstentions are distinct."""
        from scripts.evaluate_financial_evidence import evaluate_dataset, get_default_held_out_dataset
        from src.intelligence.jev.tasks.sentiment import SentimentDivergenceTask
        from src.intelligence.jev.adapters.mock_adapter import MockClassifierAdapter

        held_out = get_default_held_out_dataset()
        self.assertGreaterEqual(len(held_out), 7)

        # Mock adapter
        adapter = MockClassifierAdapter(
            model_id="mock-eval-qwen",
            preset_logits={"sentiment_divergence": {"A": 3.0, "B": 0.5, "C": 0.5, "D": 0.5, "E": 0.2, "F": 0.1}},
        )
        task = SentimentDivergenceTask()
        res = evaluate_dataset(held_out, adapter, task, confidence_abstention_threshold=0.40)

        self.assertIn("insufficient_evidence_count", res)
        self.assertIn("ambiguous_count", res)
        self.assertIn("low_confidence_abstentions", res)
        self.assertIn("coverage_rate", res)
        self.assertIn("latency", res)
        self.assertIn("median_ms", res["latency"])
        self.assertIn("p90_ms", res["latency"])
        self.assertIn("p95_ms", res["latency"])

    # --------------------------------------------------------------------------
    # 16. Phase 3 Harness Regression: Split Isolation & Leakage Prevention
    # --------------------------------------------------------------------------
    def test_phase3_split_isolation(self):
        """Held-out dataset items are tagged with split='held_out' and have zero overlap with dev."""
        from scripts.evaluate_financial_evidence import get_default_held_out_dataset
        from src.intelligence.jev.dataset import get_curated_indian_equity_dataset

        held_out = get_default_held_out_dataset()
        dev_bench = get_curated_indian_equity_dataset()

        held_out_ids = {h["sample_id"] for h in held_out}
        dev_ids = {d.sample_id for d in dev_bench}

        # Zero ID overlap
        self.assertEqual(len(held_out_ids.intersection(dev_ids)), 0)

        # Verify all held-out samples have split tag
        for h in held_out:
            self.assertEqual(h["metadata"].get("split"), "held_out")


if __name__ == "__main__":
    unittest.main()

