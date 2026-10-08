"""Sync one exchange session of public NSE/BSE data into data/raw."""
from __future__ import annotations

import argparse
from datetime import date

from src.market.exchange_sync import latest_weekday, sync_date


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", dest="trade_date", default=None, help="YYYY-MM-DD; defaults to latest weekday")
    args = parser.parse_args()

    trade_date = date.fromisoformat(args.trade_date) if args.trade_date else latest_weekday()
    print(f"Syncing exchange reports for {trade_date.isoformat()}...")
    print(sync_date(trade_date))


if __name__ == "__main__":
    main()
