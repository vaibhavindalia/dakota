from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd
from nse import NSE


DATA_DIR = Path("data/raw/nse")


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


def normalize_text(value) -> str:
    if value is None:
        return ""

    return str(value).strip()


def find_column(
    df: pd.DataFrame,
    candidates: list[str],
) -> str | None:
    for column in candidates:
        if column in df.columns:
            return column

    return None


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Expected file does not exist: {path}"
        )

    return pd.read_csv(path)


def download_nse_data(
    trading_datetime: datetime,
) -> dict[str, Path]:
    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    downloaded: dict[str, Path] = {}

    with NSE(
        download_folder=DATA_DIR
    ) as nse:

        print("Downloading NSE bhavcopy...")
        bhavcopy = Path(
            nse.equity_bhavcopy(
                trading_datetime
            )
        )

        downloaded["bhavcopy"] = bhavcopy

        print(
            "  OK:",
            bhavcopy.name,
        )

        print("Downloading NSE delivery...")
        delivery = Path(
            nse.delivery_bhavcopy(
                trading_datetime
            )
        )

        downloaded["delivery"] = delivery

        print(
            "  OK:",
            delivery.name,
        )

        print("Downloading NSE price-band report...")
        priceband = Path(
            nse.priceband_report(
                trading_datetime
            )
        )

        downloaded["priceband"] = priceband

        print(
            "  OK:",
            priceband.name,
        )

    return downloaded


def summarize_dataset(
    name: str,
    path: Path,
) -> pd.DataFrame:
    df = load_csv(path)

    print()
    print("-" * 60)
    print(name.upper())
    print("-" * 60)

    print("File   :", path.name)
    print("Rows   :", len(df))
    print("Columns:", len(df.columns))

    print()
    print("Columns:")

    for column in df.columns:
        print("  -", column)

    return df


def find_ticker(
    df: pd.DataFrame,
    ticker: str,
) -> pd.DataFrame:
    ticker = ticker.upper().strip()

    symbol_column = find_column(
        df,
        [
            "TckrSymb",
            "TckrSymb ",
            "Symbol",
            "SYMBOL",
            "symbol",
        ],
    )

    if symbol_column is None:
        return df.iloc[0:0]

    normalized = (
        df[symbol_column]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    return df[normalized == ticker]


def print_ticker_result(
    name: str,
    df: pd.DataFrame,
    ticker: str,
) -> None:
    matches = find_ticker(
        df,
        ticker,
    )

    print()
    print(
        f"{name}: {ticker}"
    )

    print(
        "Matches:",
        len(matches),
    )

    if matches.empty:
        print(
            "  No matching row found."
        )
        return

    print()

    print(
        matches.to_string(
            index=False
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Download the NSE datasets used by Dakota "
            "for a single trading date."
        )
    )

    parser.add_argument(
        "--date",
        default="06-Oct-2026",
        help="Trading date.",
    )

    parser.add_argument(
        "--ticker",
        default="CDSL",
        help="Optional ticker to inspect.",
    )

    args = parser.parse_args()

    trading_datetime = parse_datetime(
        args.date
    )

    ticker = normalize_text(
        args.ticker
    ).upper()

    print("=" * 60)
    print("DAKOTA NSE COLLECTOR")
    print("=" * 60)

    print(
        "Date   :",
        trading_datetime.date(),
    )

    print(
        "Ticker :",
        ticker,
    )

    print(
        "Output :",
        DATA_DIR.resolve(),
    )

    print()

    try:
        files = download_nse_data(
            trading_datetime
        )

    except Exception as exc:
        print()
        print("=" * 60)
        print("NSE COLLECTION FAILED")
        print("=" * 60)

        print(
            type(exc).__name__
        )

        print(
            str(exc)
        )

        raise SystemExit(1)

    datasets: dict[str, pd.DataFrame] = {}

    for name, path in files.items():
        datasets[name] = summarize_dataset(
            name,
            path,
        )

    if ticker:
        print()
        print("=" * 60)
        print(
            f"TICKER INSPECTION: {ticker}"
        )
        print("=" * 60)

        for name, df in datasets.items():
            print_ticker_result(
                name,
                df,
                ticker,
            )

    print()
    print("=" * 60)
    print("NSE COLLECTION COMPLETE")
    print("=" * 60)

    print(
        "Downloaded:",
        len(files),
        "datasets",
    )


if __name__ == "__main__":
    main()