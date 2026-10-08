from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.market.normalizer import normalize_nse


DATA_DIR = Path("data/raw/nse")


BHAVCOPY_FILE = (
    DATA_DIR
    / "BhavCopy_NSE_CM_0_0_0_20261006_F_0000.csv"
)

DELIVERY_FILE = (
    DATA_DIR
    / "sec_bhavdata_full_06102026.csv"
)

PRICEBAND_FILE = (
    DATA_DIR
    / "sec_list_06102026.csv"
)


def main() -> None:
    print("=" * 60)
    print("DAKOTA NSE NORMALIZER TEST")
    print("=" * 60)

    print()
    print("Loading files...")

    print(
        "BhavCopy :",
        BHAVCOPY_FILE,
    )

    print(
        "Delivery  :",
        DELIVERY_FILE,
    )

    print(
        "PriceBand :",
        PRICEBAND_FILE,
    )

    # ---------------------------------------------------------
    # Check files
    # ---------------------------------------------------------

    files = [
        BHAVCOPY_FILE,
        DELIVERY_FILE,
        PRICEBAND_FILE,
    ]

    for file in files:
        if not file.exists():
            raise FileNotFoundError(
                f"Missing file: {file}"
            )

    # ---------------------------------------------------------
    # Load datasets
    # ---------------------------------------------------------

    bhavcopy = pd.read_csv(
        BHAVCOPY_FILE
    )

    delivery = pd.read_csv(
        DELIVERY_FILE
    )

    priceband = pd.read_csv(
        PRICEBAND_FILE
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

    print(
        "  PriceBand rows:",
        len(priceband),
    )

    # ---------------------------------------------------------
    # Normalize CDSL
    # ---------------------------------------------------------

    print()
    print("=" * 60)
    print("NORMALIZING CDSL")
    print("=" * 60)

    event = normalize_nse(
        bhavcopy=bhavcopy,
        delivery=delivery,
        priceband=priceband,
        ticker="CDSL",
    )

    # ---------------------------------------------------------
    # Print result
    # ---------------------------------------------------------

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

    # ---------------------------------------------------------
    # Basic validation
    # ---------------------------------------------------------

    print()
    print("=" * 60)
    print("VALIDATION")
    print("=" * 60)

    checks = {
        "exchange": event.exchange == "NSE",
        "ticker": event.ticker == "CDSL",
        "trade_date": bool(event.trade_date),
        "close": event.close is not None,
        "volume": event.volume is not None,
        "delivery_pct": event.delivery_pct is not None,
        "price_band": event.price_band is not None,
    }

    all_passed = True

    for name, passed in checks.items():
        status = "PASS" if passed else "FAIL"

        print(
            f"{name:15} : {status}"
        )

        if not passed:
            all_passed = False

    print()

    if not all_passed:
        print(
            "NSE normalization has missing fields."
        )

        raise SystemExit(1)

    print("=" * 60)
    print("NSE NORMALIZER TEST PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()