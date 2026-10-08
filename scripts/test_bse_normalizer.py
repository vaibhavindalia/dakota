from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.market.normalizer import normalize_bse


DATA_DIR = Path("data/raw/bse")


def main() -> None:
    print("=" * 60)
    print("DAKOTA BSE NORMALIZER TEST")
    print("=" * 60)

    # --------------------------------------------------------
    # Find downloaded files
    # --------------------------------------------------------

    bhavcopy_files = list(
        DATA_DIR.glob("BhavCopy*.CSV")
    )

    delivery_files = list(
        DATA_DIR.glob("SCBSEALL*.csv")
    )

    if not bhavcopy_files:
        raise FileNotFoundError(
            "No BSE BhavCopy file found."
        )

    if not delivery_files:
        raise FileNotFoundError(
            "No BSE delivery file found."
        )

    bhavcopy_file = bhavcopy_files[0]
    delivery_file = delivery_files[0]

    print()
    print("BhavCopy:")
    print(bhavcopy_file.resolve())

    print()
    print("Delivery:")
    print(delivery_file.resolve())

    # --------------------------------------------------------
    # Load datasets
    # --------------------------------------------------------

    bhavcopy = pd.read_csv(
        bhavcopy_file
    )

    delivery = pd.read_csv(
        delivery_file
    )

    print()
    print("Loaded datasets:")

    print(
        "  BhavCopy rows :",
        len(bhavcopy),
    )

    print(
        "  Delivery rows :",
        len(delivery),
    )

    print()
    print("BhavCopy columns:")
    print(bhavcopy.columns.tolist())

    print()
    print("Delivery columns:")
    print(delivery.columns.tolist())

    # --------------------------------------------------------
    # Use a stock that is actually present in this file
    #
    # From the downloaded BSE sample:
    # Ticker   = AEGISLOG
    # Code     = 500003
    # --------------------------------------------------------

    ticker = "AEGISLOG"
    bse_code = "500003"

    print()
    print("=" * 60)
    print("NORMALIZING AEGISLOG")
    print("=" * 60)

    print(
        "Ticker :",
        ticker,
    )

    print(
        "BSE code:",
        bse_code,
    )

    event = normalize_bse(
        bhavcopy=bhavcopy,
        delivery=delivery,
        ticker=ticker,
        bse_code=bse_code,
    )

    # --------------------------------------------------------
    # Print canonical event
    # --------------------------------------------------------

    print()
    print("Canonical MarketEvent:")
    print()

    print(
        json.dumps(
            event.to_dict(),
            indent=2,
            default=str,
        )
    )

    # --------------------------------------------------------
    # Validation
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("VALIDATION")
    print("=" * 60)

    checks = {
        "exchange": event.exchange == "BSE",
        "ticker": event.ticker == "AEGISLOG",
        "trade_date": bool(event.trade_date),
        "open": event.open is not None,
        "high": event.high is not None,
        "low": event.low is not None,
        "close": event.close is not None,
        "volume": event.volume is not None,
        "delivery_qty": (
            event.delivery_quantity is not None
        ),
        "delivery_pct": (
            event.delivery_pct is not None
        ),
    }

    all_passed = True

    for name, passed in checks.items():

        status = (
            "PASS"
            if passed
            else "FAIL"
        )

        print(
            f"{name:15} : {status}"
        )

        if not passed:
            all_passed = False

    print()

    if not all_passed:
        print(
            "BSE normalization has missing fields."
        )

        raise SystemExit(1)

    print("=" * 60)
    print("BSE NORMALIZER TEST PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()