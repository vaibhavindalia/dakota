"""
Phase 2B: Qwen Model & JEV Real GPU Inference Profiling Script
Tests real logit-based classification (N=0 token generation) on RTX 4060 GPU.
Profiles cold-load latency, warm forward pass latency, peak VRAM, and predictions
across curated Indian Equity financial benchmark samples.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from typing import Any, Dict, List

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.intelligence.jev.schemas import PredictionResult
from src.intelligence.jev.adapters.mock_adapter import MockClassifierAdapter
from src.intelligence.jev.adapters.hf_adapter import HuggingFaceQwenAdapter
from src.intelligence.jev.tasks.sentiment import SentimentDivergenceTask
from src.intelligence.jev.dataset import get_curated_indian_equity_dataset

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("QwenInferenceProfile")


def profile_hardware() -> Dict[str, Any]:
    """Inspect and profile system compute hardware and PyTorch backend."""
    info: Dict[str, Any] = {
        "python_version": sys.version.split()[0],
        "torch_version": "unavailable",
        "transformers_version": "unavailable",
        "bitsandbytes_version": "unavailable",
        "cuda_available": False,
        "device_count": 0,
        "devices": [],
    }

    try:
        import torch
        info["torch_version"] = torch.__version__
        info["cuda_available"] = torch.cuda.is_available()
        if info["cuda_available"]:
            info["device_count"] = torch.cuda.device_count()
            for i in range(info["device_count"]):
                props = torch.cuda.get_device_properties(i)
                total_mb = props.total_memory / (1024 * 1024)
                allocated_mb = torch.cuda.memory_allocated(i) / (1024 * 1024)
                reserved_mb = torch.cuda.memory_reserved(i) / (1024 * 1024)
                info["devices"].append({
                    "id": i,
                    "name": props.name,
                    "total_vram_mb": round(total_mb, 2),
                    "allocated_vram_mb": round(allocated_mb, 2),
                    "reserved_vram_mb": round(reserved_mb, 2),
                })
    except ImportError:
        pass

    try:
        import transformers
        info["transformers_version"] = transformers.__version__
    except ImportError:
        pass

    try:
        import bitsandbytes as bnb
        info["bitsandbytes_version"] = bnb.__version__
    except ImportError:
        pass

    try:
        import psutil
        vm = psutil.virtual_memory()
        info["ram_total_gb"] = round(vm.total / (1024**3), 2)
        info["ram_available_gb"] = round(vm.available / (1024**3), 2)
    except ImportError:
        info["ram_total_gb"] = "unknown"

    return info


def run_profiling(args: argparse.Namespace) -> None:
    logger.info("=== Project Dakota: JEV + Qwen Real GPU Inference Profiling ===")
    hw = profile_hardware()
    logger.info("Hardware Profile: %s", json.dumps(hw, indent=2))

    # Strict enforcement rules
    if args.no_mock and args.mock:
        logger.error("Conflict: both --mock and --no-mock were passed.")
        sys.exit(1)

    use_mock = args.mock and not args.no_mock

    if args.require_gpu:
        if use_mock:
            logger.error("Conflict: --require-gpu was set, but mock mode was enabled.")
            sys.exit(1)
        if not hw["cuda_available"]:
            logger.error("STRICT VERIFICATION FAILED: --require-gpu was set, but torch.cuda.is_available() is False!")
            sys.exit(1)

    quant_desc = "4-bit NF4 (BitsAndBytes)" if args.load_in_4bit else "bfloat16 (Native Half Precision)"
    logger.info("Target Model: %s | Quantization: %s | Device: %s", args.model, quant_desc, args.device)

    import torch

    mem_before_load_mb = 0.0
    mem_reserved_before_load_mb = 0.0
    if hw["cuda_available"]:
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        mem_before_load_mb = torch.cuda.memory_allocated(0) / (1024 * 1024)
        mem_reserved_before_load_mb = torch.cuda.memory_reserved(0) / (1024 * 1024)

    # Initialize Adapter
    if use_mock:
        logger.info("Using Deterministic MockClassifierAdapter (offline unit testing mode only).")
        adapter = MockClassifierAdapter()
        cold_load_time_sec = 0.0
        model_class_name = type(adapter).__name__
        model_revision = "simulated"
        device_map_info = "mock"
    else:
        logger.info("Initializing HuggingFaceQwenAdapter with model: %s", args.model)
        try:
            adapter = HuggingFaceQwenAdapter(
                model_id=args.model,
                device=args.device,
                load_in_4bit=args.load_in_4bit,
            )
            # Cold load timing with CUDA synchronization
            if hw["cuda_available"]:
                torch.cuda.synchronize()
            t_load_0 = time.perf_counter()
            adapter.load_model()
            if hw["cuda_available"]:
                torch.cuda.synchronize()
            t_load_1 = time.perf_counter()
            cold_load_time_sec = t_load_1 - t_load_0
            logger.info("Cold-Load Time: %.3f seconds", cold_load_time_sec)

            model_class_name = type(adapter._model).__name__ if adapter._model else "unknown"
            model_revision = getattr(adapter._model, "_commit_hash", adapter.model_revision)
            device_map_info = getattr(adapter._model, "hf_device_map", str(getattr(adapter._model, "device", "unknown")))
        except Exception as exc:
            logger.exception("FATAL: Failed to load model %s: %s", args.model, exc)
            sys.exit(1)

    # Curated financial dataset
    all_samples = get_curated_indian_equity_dataset()
    test_samples = all_samples[:args.num_samples]
    task = SentimentDivergenceTask()

    logger.info("Running inference on %d curated financial samples...", len(test_samples))

    sample_results = []
    latencies = []
    predicted_labels = []
    mem_after_warmup_mb = 0.0
    mem_reserved_after_warmup_mb = 0.0

    for idx, bench_sample in enumerate(test_samples, 1):
        sample_dict = dict(bench_sample.sample)
        sample_dict["evidence_ids"] = bench_sample.evidence_ids

        # Synchronize before and after timing
        if hw["cuda_available"]:
            torch.cuda.synchronize()
        t0 = time.perf_counter()
        try:
            res: PredictionResult = task.classify(adapter, sample_dict)
        except Exception as exc:
            logger.exception("FATAL: Inference failure on sample %s (%s): %s", bench_sample.sample_id, bench_sample.ticker, exc)
            sys.exit(1)
        if hw["cuda_available"]:
            torch.cuda.synchronize()
        t1 = time.perf_counter()
        lat_ms = (t1 - t0) * 1000.0
        latencies.append(lat_ms)
        predicted_labels.append(res.predicted_label)

        if idx == 1 and hw["cuda_available"]:
            mem_after_warmup_mb = torch.cuda.memory_allocated(0) / (1024 * 1024)
            mem_reserved_after_warmup_mb = torch.cuda.memory_reserved(0) / (1024 * 1024)

        sample_snippet = (bench_sample.sample.get("headline") or bench_sample.sample.get("text") or "")[:120]

        sample_results.append({
            "sample_index": idx,
            "sample_id": bench_sample.sample_id,
            "ticker": bench_sample.ticker,
            "snippet": sample_snippet,
            "ground_truth": bench_sample.label,
            "predicted_label": res.predicted_label,
            "confidence": round(res.confidence, 4),
            "margin": round(res.margin, 4),
            "entropy": round(res.entropy, 4),
            "latency_ms": round(lat_ms, 2),
            "raw_logits": {k: round(v, 4) for k, v in (res.raw_logits or {}).items()},
            "probabilities": {k: round(v, 4) for k, v in res.class_scores.items()},
        })

    # Telemetry and VRAM profiling
    peak_vram_alloc_mib = 0.0
    peak_vram_reserved_mib = 0.0
    device_name = "CPU"
    if hw["cuda_available"]:
        device_name = torch.cuda.get_device_name(0)
        peak_vram_alloc_mib = torch.cuda.max_memory_allocated(0) / (1024 * 1024)
        peak_vram_reserved_mib = torch.cuda.max_memory_reserved(0) / (1024 * 1024)

    # Check for mode collapse
    unique_predictions = set(predicted_labels)
    mode_collapse = len(unique_predictions) == 1 and len(test_samples) > 1

    first_latency = latencies[0] if latencies else 0.0
    warm_latencies = latencies[1:] if len(latencies) > 1 else latencies
    warm_mean = sum(warm_latencies) / len(warm_latencies) if warm_latencies else 0.0
    warm_median = sorted(warm_latencies)[len(warm_latencies) // 2] if warm_latencies else 0.0

    print("\n" + "=" * 80)
    print("           DAKOTA JEV — REAL GPU SMOKE TEST TELEMETRY REPORT")
    print("=" * 80)
    print(f"Model ID:              {args.model}")
    print(f"Model Class:           {model_class_name}")
    print(f"Model Revision:        {model_revision}")
    print(f"Device Map:            {device_map_info}")
    print(f"Execution Device:      {device_name}")
    print(f"Quantization:          {quant_desc}")
    print(f"PyTorch Version:       {hw['torch_version']}")
    print(f"Transformers Version:  {hw['transformers_version']}")
    print(f"BitsAndBytes Version:  {hw['bitsandbytes_version']}")
    print("-" * 80)
    print(f"CUDA VRAM Before Load: Allocated: {mem_before_load_mb:.2f} MiB | Reserved: {mem_reserved_before_load_mb:.2f} MiB")
    print(f"CUDA VRAM After Warmup:Allocated: {mem_after_warmup_mb:.2f} MiB | Reserved: {mem_reserved_after_warmup_mb:.2f} MiB")
    print(f"Peak VRAM Allocated:   {peak_vram_alloc_mib:.2f} MiB")
    print(f"Peak VRAM Reserved:    {peak_vram_reserved_mib:.2f} MiB")
    print(f"Cold-Load Latency:     {cold_load_time_sec:.3f} s")
    print(f"First-Inference Lat:   {first_latency:.2f} ms")
    print(f"Warm Inference Median: {warm_median:.2f} ms (Mean: {warm_mean:.2f} ms, Min: {min(warm_latencies):.2f} ms, Max: {max(warm_latencies):.2f} ms)")
    print(f"Output Tokens Gen:     0 (JEV prefix KV-cache logit extraction)")
    print(f"Unique Predictions:    {list(unique_predictions)} (Mode Collapse: {mode_collapse})")
    print("-" * 80)
    print(f"{'Idx':<4} {'Ticker':<8} {'Ground Truth':<12} {'Predicted':<12} {'Conf':<8} {'Entropy':<8} {'Margin':<8} {'Latency':<10}")
    print("-" * 80)
    for sr in sample_results:
        print(f"{sr['sample_index']:<4} {sr['ticker']:<8} {sr['ground_truth']:<12} {sr['predicted_label']:<12} {sr['confidence']:<8.4f} {sr['entropy']:<8.4f} {sr['margin']:<8.4f} {sr['latency_ms']:<8.2f} ms")
    print("-" * 80)

    print("\nDetailed Per-Sample Logits and Softmax Distribution:")
    for sr in sample_results:
        print(f"\n[{sr['sample_index']}] {sr['ticker']} (Truth: {sr['ground_truth']} | Pred: {sr['predicted_label']})")
        print(f"  Snippet:       {sr['snippet']}...")
        print(f"  Raw Logits:    {sr['raw_logits']}")
        print(f"  Probabilities: {sr['probabilities']}")
        print(f"  Entropy:       {sr['entropy']:.4f} nats | Margin: {sr['margin']:.4f}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JEV + Qwen Real GPU Inference Profiler")
    parser.add_argument("--model", type=str, default="Qwen/Qwen3.5-9B",
                        help="Hugging Face model ID")
    parser.add_argument("--mock", action="store_true", default=False,
                        help="Use deterministic mock adapter (offline unit test mode only)")
    parser.add_argument("--no-mock", action="store_true", default=True,
                        help="Strictly disable mock adapter")
    parser.add_argument("--require-gpu", action="store_true", default=True,
                        help="Strictly enforce real CUDA GPU execution")
    parser.add_argument("--device", type=str, default="cuda",
                        help="Device target ('cuda' or 'auto')")
    parser.add_argument("--load-in-4bit", action="store_true", default=True,
                        help="Load model in 4-bit NF4 quantization via BitsAndBytes")
    parser.add_argument("--num-samples", type=int, default=5,
                        help="Number of distinct curated financial samples to evaluate (min 5)")
    args = parser.parse_args()

    run_profiling(args)
