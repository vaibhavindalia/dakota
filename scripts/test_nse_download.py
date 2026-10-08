from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd
from nse import NSE


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


def find_symbol_column(df: pd.DataFrame) -> str:
    candidates = [
        "TckrSymb",
        "TckrSymb ",
        "Symbol",
        "SYMBOL",
        "symbol",
    ]

    for column in candidates:
        if column in df.columns:
            return column

    raise RuntimeError(
        "Could not find the ticker column.\n"
        f"Available columns:\n{list(df.columns)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test NSE daily equity bhavcopy download."
    )

    parser.add_argument(
        "--date",
        default="06-Oct-2026",
        help="Trading date, e.g. 06-Oct-2026",
    )

    parser.add_argument(
        "--ticker",
        default="CDSL",
        help="NSE ticker to search for.",
    )

    args = parser.parse_args()

    trading_datetime = parse_datetime(args.date)
    ticker = args.ticker.strip().upper()

    download_dir = Path("data/raw/nse")
    download_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 60)
    print("DAKOTA NSE DATA TEST")
    print("=" * 60)

    print("Date   :", trading_datetime.date())
    print("Ticker :", ticker)
    print("Folder :", download_dir.resolve())
    print()

    try:
        with NSE(
            download_folder=download_dir
        ) as nse:

            print("Connecting to NSE...")
            print("Downloading CM-UDiFF bhavcopy...")
            print()

            file_path = nse.equity_bhavcopy(
                trading_datetime
            )

            print("Download successful.")
            print("File:")
            print(Path(file_path).resolve())

            df = pd.read_csv(
                file_path
            )

    except Exception as exc:
        print()
        print("=" * 60)
        print("NSE DOWNLOAD FAILED")
        print("=" * 60)
        print(type(exc).__name__)
        print(str(exc))
        raise SystemExit(1)

    print()
    print("=" * 60)
    print("DATASET INFORMATION")
    print("=" * 60)

    print("Rows   :", len(df))
    print("Columns:", len(df.columns))

    print()
    print("Columns returned by NSE:")

    for column in df.columns:
        print("  -", column)

    symbol_column = find_symbol_column(df)

    matches = df[
        df[symbol_column]
        .astype(str)
        .str.strip()
        .str.upper()
        == ticker
    ]

    print()
    print("=" * 60)
    print(f"SEARCH RESULT: {ticker}")
    print("=" * 60)

    print("Matches:", len(matches))

    if matches.empty:
        print()
        print(
            f"{ticker} was not found in the NSE "
            f"bhavcopy for {trading_datetime.date()}."
        )
        return

    print()
    print("Matching row:")
    print()

    print(
        matches.to_string(
            index=False
        )
    )

    print()
    print("=" * 60)
    print("NSE TEST PASSED")
    print("=" * 60)

    print(
        "Dakota successfully downloaded and read "
        "NSE market data."
    )


if __name__ == "__main__":
    main()