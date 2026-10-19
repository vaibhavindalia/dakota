"""CLI script to execute the empirical walk-forward benchmark and generate research artifacts."""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.intelligence.jev.dataset import get_curated_indian_equity_dataset
from src.intelligence.jev.adapters.mock_adapter import MockClassifierAdapter
from src.intelligence.jev.adapters.hf_adapter import HuggingFaceQwenAdapter
from src.intelligence.jev.evaluation.benchmark import BenchmarkRunner

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("BenchmarkCLI")


def main():
    parser = argparse.ArgumentParser(description="JEV Walk-Forward Benchmark CLI")
    parser.add_argument("--model", type=str, default="Qwen/Qwen3.5-9B", help="Target Hugging Face model ID")
    parser.add_argument("--device", type=str, default="cuda", help="Execution device target ('cuda' or 'cpu')")
    parser.add_argument("--load-in-4bit", action="store_true", default=True, help="Enable 4-bit NF4 quantization")
    parser.add_argument("--mock", action="store_true", default=False, help="Use mock adapter for offline test passes")
    parser.add_argument("--no-mock", action="store_true", default=True, help="Strictly disable mock adapter")
    parser.add_argument("--splits", type=int, default=3, help="Number of walk-forward folds")
    parser.add_argument("--purge-hours", type=float, default=24.0, help="Embargo purge window in hours")
    parser.add_argument("--output-dir", type=str, default="research/results", help="Directory to save artifacts")
    parser.add_argument("--output-prefix", type=str, default="phase2c", help="Prefix for benchmark artifacts")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    use_mock = args.mock and not args.no_mock

    # Preserve historical Phase 2B artifacts before running Phase 2C
    hist_json = out_dir / "walk_forward_benchmark.json"
    phase2b_json = out_dir / "walk_forward_benchmark_phase2b_30tok.json"
    if hist_json.exists() and not phase2b_json.exists():
        import shutil
        shutil.copy(hist_json, phase2b_json)
        logger.info("Preserved historical Phase 2B benchmark to: %s", phase2b_json)

    logger.info("Loading Indian Equity benchmark dataset...")
    dataset = get_curated_indian_equity_dataset()
    logger.info("Loaded %d curated samples across Indian equity events", len(dataset))

    runner = BenchmarkRunner(
        samples=dataset,
        n_splits=args.splits,
        purge_window_hours=args.purge_hours,
    )

    peak_vram_allocated_mb = 0.0
    peak_vram_reserved_mb = 0.0

    if use_mock:
        logger.info("Using deterministic MockClassifierAdapter (offline unit testing mode).")
        adapter = MockClassifierAdapter(model_id="Mock-Qwen")
    else:
        import torch
        if args.device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA is requested for benchmark execution, but torch.cuda.is_available() is False!")

        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()

        logger.info("Initializing real HuggingFaceQwenAdapter on %s with model: %s...", args.device, args.model)
        adapter = HuggingFaceQwenAdapter(
            model_id=args.model,
            device=args.device,
            load_in_4bit=args.load_in_4bit,
        )
        adapter.load_model()

    logger.info("Executing walk-forward validation across models...")
    report = runner.run(adapter)

    if not use_mock:
        import torch
        if torch.cuda.is_available():
            peak_vram_allocated_mb = torch.cuda.max_memory_allocated() / (1024 ** 2)
            peak_vram_reserved_mb = torch.cuda.max_memory_reserved() / (1024 ** 2)
            logger.info("Peak VRAM during benchmark: Allocated: %.2f MiB, Reserved: %.2f MiB", peak_vram_allocated_mb, peak_vram_reserved_mb)

    # Output artifact filepaths
    prefix_str = f"_{args.output_prefix}" if args.output_prefix else ""
    json_path = out_dir / f"walk_forward_benchmark{prefix_str}.json"
    md_path = out_dir / f"benchmark_summary{prefix_str}.md"

    # Save JSON report
    report_dict = report.model_dump()
    report_dict["peak_vram_allocated_mb"] = peak_vram_allocated_mb
    report_dict["peak_vram_reserved_mb"] = peak_vram_reserved_mb

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_dict, f, indent=2)
    logger.info("Saved JSON benchmark results to: %s", json_path)

    # Build comprehensive Markdown summary
    md_content = (
        f"# Project Dakota: JEV + Qwen Empirical Benchmark Results ({args.output_prefix.upper()})\n\n"
        f"- **Dataset Size**: {report.total_samples} samples across Indian equity events\n"
        f"- **Walk-Forward Splits**: {report.n_folds} chronological folds\n"
        f"- **Embargo Purge Window**: {report.purge_window_hours} hours\n"
        f"- **Candidate Classes**: {', '.join(report.classes)}\n"
        f"- **Peak VRAM**: Allocated: {peak_vram_allocated_mb:.1f} MiB | Reserved: {peak_vram_reserved_mb:.1f} MiB\n\n"
        f"## Comparative Performance\n\n"
        f"{report.to_markdown_table()}\n\n"
        f"> **Statistical Limitation Note**: The evaluation set contains {report.total_samples} events with 9 walk-forward test predictions. "
        f"Differences in ECE, Brier score, and accuracy on this sample size cannot establish statistical significance or broad generalization.\n\n"
        f"## Per-Model Diagnostic Details\n\n"
    )

    for model_name, m in report.model_summaries.items():
        md_content += f"### {model_name}\n\n"
        md_content += f"- **Accuracy**: {m.accuracy * 100:.2f}%\n"
        md_content += f"- **Macro-F1**: {m.macro_f1:.4f} (Weighted-F1: {m.weighted_f1:.4f})\n"
        md_content += f"- **Brier Score**: {m.brier_score:.4f}\n"
        md_content += f"- **ECE**: {m.ece:.4f}\n"
        md_content += f"- **Negative Log-Likelihood**: {m.nll:.4f}\n"
        md_content += f"- **Mean Latency**: {m.mean_latency_ms:.2f} ms (p95: {m.p95_latency_ms:.2f} ms)\n"
        md_content += f"- **Tokens Generated**: {m.tokens_generated_per_sample:.1f}\n\n"
        md_content += f"#### Per-Class Metrics\n\n"
        md_content += "| Class | Precision | Recall | F1 | Support |\n"
        md_content += "| :--- | :---: | :---: | :---: | :---: |\n"
        for c, pm in m.per_class.items():
            md_content += f"| {c} | {pm.precision:.4f} | {pm.recall:.4f} | {pm.f1:.4f} | {pm.support} |\n"
        md_content += "\n"

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    logger.info("Saved Markdown summary to: %s", md_path)

    print("\n" + report.to_markdown_table() + "\n")


if __name__ == "__main__":
    main()
