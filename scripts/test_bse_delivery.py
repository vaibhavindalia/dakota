from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd
from bse import BSE


def parse_datetime(value: str) -> datetime:
    formats = [
        "%d-%b-%Y",
        "%Y-%m-%d",
        "%d-%m-%Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass

    raise ValueError(
        f"Invalid date: {value}. "
        "Use DD-MMM-YYYY, for example 06-Oct-2026."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test BSE daily delivery report."
    )

    parser.add_argument(
        "--date",
        default="06-Oct-2026",
    )

    args = parser.parse_args()

    trading_datetime = parse_datetime(args.date)

    output_dir = Path("data/raw/bse")
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 60)
    print("DAKOTA BSE DELIVERY TEST")
    print("=" * 60)

    print("Date  :", trading_datetime.date())
    print("Folder:", output_dir.resolve())
    print()

    try:
        with BSE(
            download_folder=output_dir
        ) as bse:

            print("Connecting to BSE...")
            print("Downloading delivery report...")
            print()

            file_path = bse.deliveryReport(
                trading_datetime
            )

            print("Download successful.")
            print(
                "File:",
                Path(file_path).resolve(),
            )

            df = pd.read_csv(
                file_path
            )

    except Exception as exc:
        print()
        print("=" * 60)
        print("BSE DELIVERY DOWNLOAD FAILED")
        print("=" * 60)

        print(
            type(exc).__name__
        )

        print(
            str(exc)
        )

        raise SystemExit(1)

    print()
    print("=" * 60)
    print("BSE DELIVERY DATASET")
    print("=" * 60)

    print("Rows   :", len(df))
    print("Columns:", len(df.columns))

    print()
    print("Columns returned by BSE:")

    for column in df.columns:
        print("  -", column)

    print()
    print("First 10 rows:")
    print(
        df.head(10).to_string(
            index=False
        )
    )

    print()
    print("=" * 60)
    print("BSE DELIVERY TEST PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()