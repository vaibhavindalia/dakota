"""Dakota Data Pipeline Scheduler.

Runs every night at midnight (00:00) to auto-fetch fresh fundamentals and
shareholding data for all stocks in the universe using free sources
(yfinance + Screener.in). No API key required.

How to run (two options):

OPTION 1 - Manual (run once right now):
    python scripts/scheduler.py --run-now

OPTION 2 - Continuous daemon (keeps running, triggers at midnight daily):
    python scripts/scheduler.py

OPTION 3 - Windows Task Scheduler (recommended for production):
    schtasks /create /tn "DakotaNightlyFetch" /tr "python scripts/scheduler.py --run-now" /sc DAILY /st 00:00
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(BASE_DIR / "logs" / "scheduler.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def run_pipeline() -> None:
    """Execute the full nightly data fetch pipeline."""
    logger.info("=" * 60)
    logger.info("Dakota Nightly Pipeline Starting")
    logger.info("=" * 60)

    start = datetime.utcnow()

    try:
        from src.ingest.free_data_fetcher import fetch_all_and_save
        logger.info("Step 1/1: Fetching fundamentals + shareholding for all universe stocks...")
        stats = fetch_all_and_save()
        elapsed = round((datetime.utcnow() - start).total_seconds(), 1)
        logger.info(
            "Pipeline complete in %ss. OK=%d Failed=%d Total=%d",
            elapsed, stats["ok"], stats["failed"], stats["total"]
        )
    except Exception as exc:
        logger.error("Pipeline failed: %s", exc, exc_info=True)


def _seconds_until_midnight() -> float:
    """Compute seconds until next 00:00 local time."""
    now = datetime.now()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    # Already past midnight today -> next midnight is tomorrow
    diff = (midnight - now).total_seconds()
    if diff <= 0:
        diff += 86400  # 24 hours in seconds
    return diff


def run_daemon() -> None:
    """Infinite loop: wait until midnight, run pipeline, repeat."""
    logger.info("Dakota Scheduler started. Pipeline will run every night at midnight.")
    while True:
        wait = _seconds_until_midnight()
        next_run = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        logger.info("Next pipeline run in %.0f seconds (at %s)", wait, next_run)
        time.sleep(wait)
        run_pipeline()
        time.sleep(60)  # small gap to avoid double-trigger at midnight boundary


def sync_universe_scores(batch_size: int = 50) -> None:
    """Precompute risk scores for pending stocks in the 2,600+ universe."""
    logger.info("=" * 60)
    logger.info("Syncing stock universe scores in batches...")
    logger.info("=" * 60)
    from src.market.universe_manager import sync_pending_batch, query_stocks
    updated = sync_pending_batch(batch_size=batch_size)
    stats = query_stocks(limit=1)
    logger.info(
        "Sync batch complete: %d stocks updated. Total Assessed: %d / %d",
        updated,
        stats.get("global_assessed", 0),
        stats.get("global_total", 0),
    )


if __name__ == "__main__":
    # Ensure logs directory exists
    (BASE_DIR / "logs").mkdir(parents=True, exist_ok=True)

    parser = argparse.ArgumentParser(description="Dakota nightly data scheduler")
    parser.add_argument(
        "--run-now",
        action="store_true",
        help="Run the pipeline immediately and exit (for manual runs / Task Scheduler)",
    )
    parser.add_argument(
        "--sync-scores",
        action="store_true",
        help="Precompute scores for pending Indian stocks into SQLite database",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=25,
        help="Batch size for --sync-scores (default: 25)",
    )
    args = parser.parse_args()

    if args.sync_scores:
        sync_universe_scores(batch_size=args.batch_size)
    elif args.run_now:
        run_pipeline()
    else:
        run_daemon()
