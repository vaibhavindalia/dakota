"""Reproducible Indian Stock Manipulation Research & Model Training Pipeline (Phase 10).

Executes end-to-end:
1. Refresh / verify 500-equity Indian surveillance universe.
2. Validate regulatory evidence provenance (SEBI orders, ASM/GSM notices).
3. Build leakage-safe observation windows with 15-day embargo purge windows.
4. Fit preprocessing and train calibrated QN Quantitative Manipulation Model.
5. Evaluate on holdout test fold with ROC-AUC, PR-AUC, ECE, Brier score, and Confusion Matrix.
6. Serialize model artifacts and verify inference readiness in Project Dakota.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.surveillance.dataset_builder import dataset_builder
from src.surveillance.evidence import evidence_registry
from src.surveillance.model import QNManipulationModel, qn_inference
from src.surveillance.universe import surveillance_universe

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("reproduce_experiment")


def run_pipeline(
    random_state: int = 42,
    purge_days: int = 15,
    allow_synthetic: bool = False,
    output_report_path: Path | None = None,
) -> dict:
    start_time = time.perf_counter()
    logger.info("======================================================================")
    logger.info("DAKOTA INDIAN STOCK MANIPULATION SURVEILLANCE RESEARCH PIPELINE")
    logger.info("======================================================================")

    # Step 0: Data Quality & Provenance Audit
    logger.info("--- STEP 0: Forensic Data Quality & Provenance Audit (500 Equities) ---")
    from src.surveillance.data_audit import run_universe_data_audit
    data_audit_summary = run_universe_data_audit()
    logger.info(
        "Data audit complete: %d / %d usable (%.1f%%). Delisted/Unavailable: %d",
        data_audit_summary["usable_equities_count"],
        data_audit_summary["total_equities_audited"],
        data_audit_summary["usable_percentage"],
        data_audit_summary["unusable_equities_count"],
    )

    # Step 1: Universe Verification
    logger.info("--- STEP 1: Verifying 500-Equity Surveillance Universe ---")
    surveillance_universe._build_from_repository()
    uni_summary = surveillance_universe.get_summary()
    logger.info(
        "Universe verified: %d equities (%d cases, %d controls | %d NSE, %d BSE)",
        uni_summary["total_count"],
        uni_summary["case_count"],
        uni_summary["control_count"],
        uni_summary["exchanges"]["NSE"],
        uni_summary["exchanges"]["BSE"],
    )

    # Step 2: Evidence Provenance Verification
    logger.info("--- STEP 2: Verifying Regulatory Evidence Registry ---")
    evidence_registry._seed_official_cases()
    ev_summary = evidence_registry.get_summary()
    logger.info(
        "Evidence registry verified: %d total events (%d confirmed SEBI orders, %d suspicious)",
        ev_summary["total_registered_events"],
        ev_summary["confirmed_manipulation_count"],
        ev_summary["suspicious_unconfirmed_count"],
    )

    # Step 3: Dataset Construction & Walk-Forward Splitting
    logger.info("--- STEP 3: Constructing Walk-Forward Splits (Embargo: %d days, allow_synthetic=%s) ---", purge_days, allow_synthetic)
    dataset_builder.purge_days = purge_days
    manifest = dataset_builder.build_dataset(allow_synthetic=allow_synthetic)
    splits = manifest["splits"]
    logger.info(
        "Splits constructed: Train=%d (pos=%d), Val=%d (pos=%d), Test=%d (pos=%d)",
        splits["train"]["count"],
        splits["train"]["positive_count"],
        splits["val"]["count"],
        splits["val"]["positive_count"],
        splits["test"]["count"],
        splits["test"]["positive_count"],
    )
    logger.info(
        "Leakage Invariants: Event Isolation=%s, Temporal Monotonicity=%s, Cross-Split Overlap=%d",
        manifest["leakage_invariants"]["event_isolation_verified"],
        manifest["leakage_invariants"]["temporal_monotonicity_verified"],
        manifest["leakage_invariants"]["cross_split_event_overlap"],
    )

    # Step 4: Model Training with Calibrated Estimator & Validation Threshold Tuning
    logger.info("--- STEP 4: Training Calibrated QN Model with Validation-Tuned Operating Threshold ---")
    model = QNManipulationModel(random_state=random_state)
    val_report, test_report, model_meta = model.train()

    # Step 5: Inference Engine Verification
    logger.info("--- STEP 5: Verifying Model Inference in Dakota ---")
    qn_inference._load()
    if not qn_inference.is_model_available():
        raise RuntimeError("Model artifact failed to load into inference engine!")

    probe_tickers = ["CLOUD", "ASRL", "INFY", "RELIANCE"]
    probe_results = {}
    for t in probe_tickers:
        pred = qn_inference.analyze_ticker(t)
        probe_results[t] = {
            "score": pred.model_score,
            "band": pred.risk_band,
            "prob": pred.manipulation_probability,
            "latency_ms": pred.latency_ms,
        }
        logger.info(
            "Probe %s -> Score: %.1f/100 (%s Band, Prob: %.2f%%, Latency: %.1fms)",
            t,
            pred.model_score,
            pred.risk_band,
            pred.manipulation_probability * 100,
            pred.latency_ms,
        )

    elapsed = round(time.perf_counter() - start_time, 2)
    logger.info("--- PIPELINE EXECUTION COMPLETE (Elapsed: %.2fs) ---", elapsed)

    report = {
        "pipeline_name": "Dakota QN & JAV Manipulation Surveillance Pipeline",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": elapsed,
        "configuration": {
            "random_state": random_state,
            "purge_embargo_days": purge_days,
            "allow_synthetic": allow_synthetic,
            "target_universe_size": 500,
        },
        "universe_summary": uni_summary,
        "evidence_summary": ev_summary,
        "data_quality_summary": {
            "total_equities_audited": data_audit_summary["total_equities_audited"],
            "usable_equities_count": data_audit_summary["usable_equities_count"],
            "usable_percentage": data_audit_summary["usable_percentage"],
            "unusable_equities_count": data_audit_summary["unusable_equities_count"],
            "provenance_breakdown": data_audit_summary["provenance_breakdown"],
            "aggregate_telemetry": data_audit_summary["aggregate_telemetry"],
        },
        "dataset_splits": splits,
        "operating_threshold": model_meta.get("operating_threshold", 0.50),
        "validation_metrics": val_report.to_dict(),
        "holdout_test_metrics": test_report.to_dict(),
        "inference_probe_checks": probe_results,
    }

    out_file = output_report_path or (BASE_DIR / "data" / "research" / "reproducibility_report.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info("Reproducibility report saved to %s", out_file)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reproduce Dakota QN Surveillance Experiment")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for model training")
    parser.add_argument("--purge-days", type=int, default=15, help="Embargo purge window in days")
    parser.add_argument("--allow-synthetic", action="store_true", default=False, help="Allow synthetic fallback for test suites")
    parser.add_argument("--out", type=str, default="", help="Optional output JSON report path")
    args = parser.parse_args()

    out_p = Path(args.out) if args.out else None
    run_pipeline(
        random_state=args.seed,
        purge_days=args.purge_days,
        allow_synthetic=args.allow_synthetic,
        output_report_path=out_p,
    )
