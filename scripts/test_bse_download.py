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


def find_column(
    df: pd.DataFrame,
    candidates: list[str],
) -> str | None:
    for column in candidates:
        if column in df.columns:
            return column

    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test BSE daily BhavCopy."
    )

    parser.add_argument(
        "--date",
        default="06-Oct-2026",
        help="Trading date.",
    )

    parser.add_argument(
        "--ticker",
        default="CDSL",
        help="Ticker/company to search for.",
    )

    args = parser.parse_args()

    trading_datetime = parse_datetime(args.date)
    ticker = args.ticker.strip().upper()

    data_dir = Path("data/raw/bse")
    data_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 60)
    print("DAKOTA BSE DATA TEST")
    print("=" * 60)

    print("Date   :", trading_datetime.date())
    print("Ticker :", ticker)
    print("Folder :", data_dir.resolve())
    print()

    try:
        with BSE(
            download_folder=data_dir
        ) as bse:

            print("Connecting to BSE...")
            print("Downloading BSE BhavCopy...")
            print()

            file_path = bse.bhavcopyReport(
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
        print("BSE DOWNLOAD FAILED")
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
    print("BSE DATASET")
    print("=" * 60)

    print("Rows   :", len(df))
    print("Columns:", len(df.columns))

    print()
    print("Columns returned by BSE:")

    for column in df.columns:
        print("  -", column)

    # -----------------------------------------------------
    # Try to identify BSE fields
    # -----------------------------------------------------

    code_column = find_column(
        df,
        [
            "SC_CODE",
            "SCRIP_CD",
            "Scrip Code",
            "ScripCode",
            "Security Code",
        ],
    )

    name_column = find_column(
        df,
        [
            "SC_NAME",
            "Security Name",
            "Security_Name",
        ],
    )

    symbol_column = find_column(
        df,
        [
            "SC_SYMBOL",
            "Symbol",
            "SYMBOL",
            "TckrSymb",
        ],
    )

    print()
    print("=" * 60)
    print("DETECTED BSE FIELDS")
    print("=" * 60)

    print(
        "Code column   :",
        code_column,
    )

    print(
        "Name column   :",
        name_column,
    )

    print(
        "Symbol column :",
        symbol_column,
    )

    # -----------------------------------------------------
    # Search for ticker
    # -----------------------------------------------------

    matches = df.iloc[0:0]

    if symbol_column:
        normalized_symbol = (
            df[symbol_column]
            .astype(str)
            .str.strip()
            .str.upper()
        )

        matches = df[
            normalized_symbol == ticker
        ]

    if matches.empty and name_column:
        normalized_name = (
            df[name_column]
            .astype(str)
            .str.strip()
            .str.upper()
        )

        matches = df[
            normalized_name.str.contains(
                ticker,
                na=False,
            )
        ]

    print()
    print("=" * 60)
    print(f"SEARCH RESULT: {ticker}")
    print("=" * 60)

    print(
        "Matches:",
        len(matches),
    )

    if not matches.empty:

        print()
        print("Matching row:")
        print()

        print(
            matches.to_string(
                index=False
            )
        )

    else:

        print()
        print(
            "The BSE file downloaded successfully, "
            "but the ticker was not found using "
            "the automatically detected fields."
        )

        print()
        print("First 10 rows:")

        print(
            df.head(10).to_string(
                index=False
            )
        )

    print()
    print("=" * 60)
    print("BSE BHAVCOPY TEST COMPLETE")
    print("=" * 60)

    print(
        "BSE BhavCopy was successfully downloaded "
        "and parsed."
    )


if __name__ == "__main__":
    main()