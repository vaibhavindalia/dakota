"""
Phase C: Qwen Model & JEV Inference Profiling Script
Tests logit-based classification without token generation.
Supports both real Hugging Face causal LMs (Qwen2.5) and deterministic Mock adapters.
"""

import argparse
import json
import logging
import os
import sys
import time
from typing import Dict, Any

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.intelligence.jev.schemas import (
    ClassifierRequest,
    ClassifierQuestion,
    QuestionType,
    PredictionResult,
)
from src.intelligence.jev.adapters.mock_adapter import MockClassifierAdapter
from src.intelligence.jev.adapters.hf_adapter import HuggingFaceQwenAdapter
from src.intelligence.jev.tasks.sentiment import SentimentDivergenceTask

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("QwenInferenceProfile")


def profile_hardware() -> Dict[str, Any]:
    """Inspect and profile system compute hardware and PyTorch backend."""
    info: Dict[str, Any] = {
        "python_version": sys.version.split()[0],
        "torch_version": "unavailable",
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
        import psutil
        vm = psutil.virtual_memory()
        info["ram_total_gb"] = round(vm.total / (1024**3), 2)
        info["ram_available_gb"] = round(vm.available / (1024**3), 2)
    except ImportError:
        info["ram_total_gb"] = "unknown"

    return info


def run_profiling(args: argparse.Namespace) -> None:
    logger.info("=== Project Dakota: JEV + Qwen Inference Profiling ===")
    hw = profile_hardware()
    logger.info("Hardware Profile: %s", json.dumps(hw, indent=2))

    # Sample Indian Market Claim & Evidence
    claim = (
        "CDSL target ₹1,500 by Friday! Massive institutional buying and volume breakout. "
        "Guaranteed 25% return. Join VIP channel now!"
    )
    evidence = [
        {
            "evidence_id": "MKT-1",
            "source": "NSE",
            "timestamp": "2026-10-08T15:30:00Z",
            "content": "CDSL closing price: ₹1,263.40. Volume: 896,613 (normal vs 20-day avg). Delivery %: 41.2%."
        },
        {
            "evidence_id": "FILING-1",
            "source": "BSE",
            "timestamp": "2026-10-08T17:54:00Z",
            "content": "Routine Regulation 74(5) demat compliance certificate filed. No material disclosures."
        },
        {
            "evidence_id": "SOCIAL-1",
            "source": "Telegram/Reddit",
            "timestamp": "2026-10-08T08:23:00Z",
            "content": "Coordinated tip spread across 17 unverified channels with identical target ₹1,500."
        }
    ]

    sample = {
        "ticker": "CDSL",
        "as_of": "2026-10-08T18:00:00Z",
        "latest_price": 1263.40,
        "change_pct": 1.07,
        "volume": 896613,
        "delivery_pct": 41.2,
        "technicals": {"trend_vs_ema20": "flat", "rsi_status": "unavailable"},
        "risk_score": 10.0,
        "risk_band": "Low",
        "is_surveillance": False,
        "news_headlines": ["Routine Regulation 74(5) demat compliance certificate filed"],
        "social_signals": [
            "CDSL target ₹1,500 by Friday! Guaranteed 25% return. Join VIP channel now!",
            "Coordinated tip spread across 17 unverified channels with identical target ₹1,500.",
        ],
        "evidence_ids": ["E_MKT_CDSL", "E_FILING_BSE", "E_SOC_TG"],
    }

    task = SentimentDivergenceTask()
    logger.info("Sample Formatted: Ticker=%s, Evidence IDs=%s", sample["ticker"], sample["evidence_ids"])
    logger.info("Candidate Classes: %s", list(task.candidate_classes.keys()))

    # Initialize Adapter
    if args.mock:
        logger.info("Using Deterministic MockClassifierAdapter (0 weight downloads, simulated logits).")
        # Preset logits where Mixed / Insufficient Evidence dominate due to uncorroborated social hype
        preset_logits = {
            "sentiment_divergence": {
                "A": 0.5,   # Bullish
                "B": 1.2,   # Bearish
                "C": 1.8,   # Neutral
                "D": 4.6,   # Mixed (unverified hype vs calm market)
                "E": 2.1,   # Insufficient Evidence
            }
        }
        adapter = MockClassifierAdapter(preset_logits=preset_logits)
    else:
        logger.info("Initializing HuggingFaceQwenAdapter with model: %s", args.model)
        try:
            adapter = HuggingFaceQwenAdapter(
                model_id=args.model,
                device=args.device,
                load_in_4bit=args.load_in_4bit,
            )
        except Exception as e:
            logger.error("Failed to load Hugging Face model '%s': %s", args.model, e)
            logger.info("Falling back to MockClassifierAdapter for zero-weight profiling...")
            adapter = MockClassifierAdapter()

    # Benchmark Latency over Iterations
    latencies = []
    result: PredictionResult = None
    for i in range(args.iterations):
        t0 = time.perf_counter()
        result = task.classify(adapter, sample)
        t1 = time.perf_counter()
        latencies.append((t1 - t0) * 1000.0)

    logger.info("=== Inference Profile Results ===")
    logger.info("Model: %s", result.model_id)
    logger.info("Predicted Label: %s", result.predicted_label)
    logger.info("Class Probabilities: %s", json.dumps({k: round(v, 4) for k, v in result.class_scores.items()}, indent=2))
    logger.info("Top Confidence: %.4f", result.confidence)
    logger.info("Margin (p1 - p2): %.4f", result.margin)
    logger.info("Shannon Entropy: %.4f nats", result.entropy)
    logger.info("Output Tokens Generated: 0 (JEV logit-evaluated single token position)")
    logger.info("Latency (N=%d): Mean=%.2f ms | Min=%.2f ms | Max=%.2f ms",
                args.iterations,
                sum(latencies) / len(latencies),
                min(latencies),
                max(latencies))

    if hw.get("cuda_available") and len(hw["devices"]) > 0:
        import torch
        vram_used = torch.cuda.memory_allocated(0) / (1024 * 1024)
        logger.info("Peak GPU VRAM Allocated: %.2f MB", vram_used)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JEV + Qwen Local Inference Profiler")
    parser.add_argument("--model", type=str, default="Qwen/Qwen2.5-3B-Instruct",
                        help="Hugging Face model ID (e.g. Qwen/Qwen2.5-3B-Instruct or Qwen/Qwen2.5-7B-Instruct)")
    parser.add_argument("--mock", action="store_true", default=True,
                        help="Use deterministic mock adapter (default: True to avoid accidental weight downloads)")
    parser.add_argument("--device", type=str, default="auto", choices=["auto", "cuda", "cpu"],
                        help="Device target")
    parser.add_argument("--load-in-4bit", action="store_true", default=False,
                        help="Load model in 4-bit quantization")
    parser.add_argument("--iterations", type=int, default=5,
                        help="Number of profiling passes")
    args = parser.parse_args()

    run_profiling(args)
