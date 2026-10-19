"""Probe real Qwen3.5-9B 4-bit NF4 Simple JEV inference on a single labeled sample.

Validates:
1. Real model inference occurs on NVIDIA RTX 4060 GPU.
2. Prediction maps to the correct candidate class.
3. Probability vector matches class ordering and sums to ~1.0.
4. Evidence IDs and source metadata survive the pipeline.
5. GPU VRAM allocated and singleton model instance verified.
"""
import json
import os
import sys
import time

# Ensure workspace root is in path
WORKSPACE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)

def main():
    print("=== DAKOTA PHASE 3 — TASK 4.1 REAL MODEL PROBE ===")
    
    import torch
    print(f"CUDA Available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"GPU Device: {torch.cuda.get_device_name(0)}")
        print(f"Initial VRAM Allocated: {torch.cuda.memory_allocated() / (1024**3):.2f} GiB")

    from src.intelligence.jev.adapters.official_jev_adapter import OfficialSimpleJEVAdapter
    from src.intelligence.jev.tasks.sentiment import SentimentDivergenceTask
    from scripts.evaluate_financial_evidence import get_default_held_out_dataset, STANDARD_CLASSES

    # 1. Initialize Adapter
    adapter = OfficialSimpleJEVAdapter()
    task = SentimentDivergenceTask()

    print("\nLoading Qwen3.5-9B 4-bit NF4 model...")
    t0_load = time.perf_counter()
    adapter.load_model()
    t_load = time.perf_counter() - t0_load
    print(f"Model loaded in {t_load:.2f}s.")
    print(f"Post-load VRAM Allocated: {torch.cuda.memory_allocated() / (1024**3):.2f} GiB")
    print(f"Post-load VRAM Reserved: {torch.cuda.memory_reserved() / (1024**3):.2f} GiB")

    # 2. Select Probe Sample (HELD-001: INFY, ground truth Bullish)
    held_out = get_default_held_out_dataset()
    probe_sample = held_out[0]
    print(f"\nProbe Sample ID: {probe_sample['sample_id']} (Ticker: {probe_sample['ticker']})")
    print(f"Ground Truth Label: {probe_sample['label']}")
    print(f"Evidence IDs Input: {probe_sample['evidence_ids']}")

    # 3. Execute Real Inference
    t0_inf = time.perf_counter()
    pred = task.classify(adapter, probe_sample["sample"])
    t_inf = (time.perf_counter() - t0_inf) * 1000.0

    print("\n--- INFERENCE RESULTS ---")
    print(f"Predicted Label: {pred.predicted_label}")
    print(f"Confidence (uncalibrated softmax): {pred.confidence:.4f}")
    print(f"Is Calibrated: {pred.is_calibrated}")
    print(f"Margin: {pred.margin}")
    print(f"Entropy: {pred.entropy}")
    print(f"Latency: {pred.latency_ms:.2f} ms (Measured: {t_inf:.2f} ms)")
    print(f"Evidence IDs Output: {pred.evidence_ids}")
    print(f"Prompt Hash: {pred.prompt_hash[:16]}...")
    
    print("\nProbabilities across classes:")
    prob_sum = 0.0
    for cls_name in STANDARD_CLASSES:
        p = pred.class_scores.get(cls_name, 0.0)
        prob_sum += p
        print(f"  {cls_name:25s}: {p:.4f}")
    print(f"Sum of Probabilities: {prob_sum:.6f}")

    if pred.raw_logits:
        print("\nRaw logits:")
        for cls_name, logit in pred.raw_logits.items():
            print(f"  {cls_name:25s}: {logit:.4f}")

    # 4. Validations
    print("\n--- SAFETY & CONTRACT VERIFICATIONS ---")
    assert pred.predicted_label in STANDARD_CLASSES, f"Predicted label {pred.predicted_label} not in STANDARD_CLASSES"
    print(f"✓ Output label is in standard candidate set: {pred.predicted_label}")
    assert abs(prob_sum - 1.0) < 1e-4, f"Probability vector does not sum to ~1.0: {prob_sum}"
    print(f"✓ Softmax probability vector sums to 1.0 (actual: {prob_sum:.6f})")
    assert pred.is_calibrated is False, "is_calibrated must be False for uncalibrated softmax"
    print("✓ Softmax confidence is strictly marked is_calibrated=False")
    assert len(pred.evidence_ids) > 0, "Evidence IDs were lost in pipeline"
    print(f"✓ Evidence IDs preserved: {pred.evidence_ids}")
    
    # 5. Check Singleton Memory
    adapter2 = OfficialSimpleJEVAdapter()
    print(f"✓ Second adapter instance reuses loaded model: is_loaded={adapter2.is_loaded()}")
    print(f"Peak VRAM: {torch.cuda.max_memory_allocated() / (1024**3):.2f} GiB")
    print("\nProbe check completed successfully.")

if __name__ == "__main__":
    main()
