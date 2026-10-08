from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd


# ============================================================
# Canonical Dakota market event
# ============================================================

@dataclass
class MarketEvent:
    exchange: str
    ticker: str
    trade_date: str

    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    previous_close: float | None = None

    volume: float | None = None

    delivery_quantity: float | None = None
    delivery_pct: float | None = None

    price_band: str | None = None
    remarks: str | None = None

    source_files: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ============================================================
# Generic helpers
# ============================================================

def clean_column_name(value: Any) -> str:
    return (
        str(value)
        .strip()
        .lower()
        .replace(" ", "_")
    )


def find_column(
    df: pd.DataFrame,
    candidates: list[str],
) -> str | None:
    """
    Find a dataframe column using normalized,
    case-insensitive matching.
    """

    normalized_columns = {
        clean_column_name(column): column
        for column in df.columns
    }

    for candidate in candidates:
        key = clean_column_name(candidate)

        if key in normalized_columns:
            return normalized_columns[key]

    return None


def get_value(
    row: pd.Series,
    candidates: list[str],
    default: Any = None,
) -> Any:
    """
    Get the first available value from a row using
    normalized column-name matching.
    """

    normalized_index = {
        clean_column_name(index): index
        for index in row.index
    }

    for candidate in candidates:
        key = clean_column_name(candidate)

        actual_column = normalized_index.get(key)

        if actual_column is None:
            continue

        value = row[actual_column]

        try:
            if pd.isna(value):
                continue
        except Exception:
            pass

        return value

    return default


def to_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    try:
        return float(
            str(value)
            .replace(",", "")
            .strip()
        )
    except (TypeError, ValueError):
        return None


def to_string(value: Any) -> str | None:
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    value = str(value).strip()

    if not value:
        return None

    return value


# ============================================================
# NSE helpers
# ============================================================

def find_nse_row(
    df: pd.DataFrame,
    ticker: str,
) -> pd.Series:
    ticker = ticker.strip().upper()

    symbol_column = find_column(
        df,
        [
            "TckrSymb",
            "Symbol",
            "SYMBOL",
        ],
    )

    if symbol_column is None:
        raise ValueError(
            "NSE dataset does not contain a ticker column."
        )

    normalized = (
        df[symbol_column]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    matches = df[
        normalized == ticker
    ]

    if matches.empty:
        raise ValueError(
            f"{ticker} was not found in NSE dataset."
        )

    return matches.iloc[0]


def find_nse_delivery_row(
    delivery: pd.DataFrame,
    ticker: str,
) -> pd.Series | None:

    ticker = ticker.strip().upper()

    symbol_column = find_column(
        delivery,
        [
            "SYMBOL",
            "Symbol",
            "TckrSymb",
        ],
    )

    if symbol_column is None:
        return None

    normalized = (
        delivery[symbol_column]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    matches = delivery[
        normalized == ticker
    ]

    if matches.empty:
        return None

    return matches.iloc[0]


def find_nse_priceband_row(
    priceband: pd.DataFrame,
    ticker: str,
) -> pd.Series | None:

    ticker = ticker.strip().upper()

    symbol_column = find_column(
        priceband,
        [
            "Symbol",
            "SYMBOL",
            "TckrSymb",
        ],
    )

    if symbol_column is None:
        return None

    normalized = (
        priceband[symbol_column]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    matches = priceband[
        normalized == ticker
    ]

    if matches.empty:
        return None

    return matches.iloc[0]


# ============================================================
# NSE normalizer
# ============================================================

def normalize_nse(
    bhavcopy: pd.DataFrame,
    delivery: pd.DataFrame | None = None,
    priceband: pd.DataFrame | None = None,
    ticker: str | None = None,
) -> MarketEvent:

    if not ticker:
        raise ValueError(
            "Ticker is required for NSE normalization."
        )

    ticker = ticker.strip().upper()

    row = find_nse_row(
        bhavcopy,
        ticker,
    )

    trade_date = to_string(
        get_value(
            row,
            [
                "TradDt",
                "Trade Date",
                "DATE",
                "Date",
            ],
        )
    )

    open_price = to_float(
        get_value(
            row,
            [
                "OpnPric",
                "OPEN_PRICE",
                "OPEN",
                "Open Price",
            ],
        )
    )

    high_price = to_float(
        get_value(
            row,
            [
                "HghPric",
                "HIGH_PRICE",
                "HIGH",
                "High Price",
            ],
        )
    )

    low_price = to_float(
        get_value(
            row,
            [
                "LwPric",
                "LOW_PRICE",
                "LOW",
                "Low Price",
            ],
        )
    )

    close_price = to_float(
        get_value(
            row,
            [
                "ClsPric",
                "CLOSE_PRICE",
                "CLOSE",
                "Close Price",
            ],
        )
    )

    previous_close = to_float(
        get_value(
            row,
            [
                "PrvsClsgPric",
                "PREV_CLOSE",
                "Previous Close",
            ],
        )
    )

    volume = to_float(
        get_value(
            row,
            [
                "TtlTradgVol",
                "TTL_TRD_QNTY",
                "Total Trade Quantity",
                "Volume",
            ],
        )
    )

    # --------------------------------------------------------
    # NSE delivery
    # --------------------------------------------------------

    delivery_quantity = None
    delivery_pct = None

    if delivery is not None:

        delivery_row = find_nse_delivery_row(
            delivery,
            ticker,
        )

        if delivery_row is not None:

            delivery_quantity = to_float(
                get_value(
                    delivery_row,
                    [
                        "DELIV_QTY",
                        "Deliverable Quantity",
                        "DeliverableQty",
                        "Delivery Quantity",
                    ],
                )
            )

            delivery_pct = to_float(
                get_value(
                    delivery_row,
                    [
                        "DELIV_PER",
                        "Delivery %",
                        "Delivery Percentage",
                        "Delivery Percent",
                    ],
                )
            )

    # --------------------------------------------------------
    # NSE price band
    # --------------------------------------------------------

    price_band = None
    remarks = None

    if priceband is not None:

        priceband_row = find_nse_priceband_row(
            priceband,
            ticker,
        )

        if priceband_row is not None:

            price_band = to_string(
                get_value(
                    priceband_row,
                    [
                        "Band",
                        "Price Band",
                    ],
                )
            )

            remarks = to_string(
                get_value(
                    priceband_row,
                    [
                        "Remarks",
                    ],
                )
            )

    return MarketEvent(
        exchange="NSE",
        ticker=ticker,
        trade_date=trade_date or "",
        open=open_price,
        high=high_price,
        low=low_price,
        close=close_price,
        previous_close=previous_close,
        volume=volume,
        delivery_quantity=delivery_quantity,
        delivery_pct=delivery_pct,
        price_band=price_band,
        remarks=remarks,
        source_files=[
            "bhavcopy",
            "delivery",
            "priceband",
        ],
    )


# ============================================================
# BSE helpers
# ============================================================

def find_bse_row(
    bhavcopy: pd.DataFrame,
    ticker: str | None = None,
    bse_code: str | None = None,
) -> pd.Series:

    symbol_column = find_column(
        bhavcopy,
        [
            "TckrSymb",
            "SC_SYMBOL",
            "Symbol",
            "SYMBOL",
        ],
    )

    code_column = find_column(
        bhavcopy,
        [
            "FinInstrmId",
            "SC_CODE",
            "SCRIP_CD",
            "Scrip Code",
            "ScripCode",
            "Security Code",
        ],
    )

    name_column = find_column(
        bhavcopy,
        [
            "FinInstrmNm",
            "SC_NAME",
            "Security Name",
            "Security_Name",
        ],
    )

    matches = bhavcopy.iloc[0:0]

    # --------------------------------------------------------
    # Try BSE instrument/scrip code first
    # --------------------------------------------------------

    if bse_code and code_column:

        normalized_code = (
            bhavcopy[code_column]
            .astype(str)
            .str.strip()
            .str.replace(
                ".0",
                "",
                regex=False,
            )
        )

        matches = bhavcopy[
            normalized_code
            == str(bse_code)
        ]

    # --------------------------------------------------------
    # Try ticker
    # --------------------------------------------------------

    if (
        matches.empty
        and ticker
        and symbol_column
    ):

        normalized_symbol = (
            bhavcopy[symbol_column]
            .astype(str)
            .str.strip()
            .str.upper()
        )

        matches = bhavcopy[
            normalized_symbol
            == ticker.strip().upper()
        ]

    # --------------------------------------------------------
    # Try security name
    # --------------------------------------------------------

    if (
        matches.empty
        and ticker
        and name_column
    ):

        normalized_name = (
            bhavcopy[name_column]
            .astype(str)
            .str.strip()
            .str.upper()
        )

        matches = bhavcopy[
            normalized_name.str.contains(
                ticker.strip().upper(),
                na=False,
            )
        ]

    if matches.empty:
        raise ValueError(
            f"BSE security not found: "
            f"ticker={ticker}, code={bse_code}"
        )

    return matches.iloc[0]


def find_bse_delivery_row(
    delivery: pd.DataFrame,
    bse_code: str | None = None,
    ticker: str | None = None,
) -> pd.Series | None:

    code_column = find_column(
        delivery,
        [
            "SCRIP CODE",
            "Scrip Code",
            "SC_CODE",
            "SCRIP_CD",
        ],
    )

    if code_column and bse_code:

        normalized_code = (
            delivery[code_column]
            .astype(str)
            .str.strip()
            .str.replace(
                ".0",
                "",
                regex=False,
            )
        )

        matches = delivery[
            normalized_code
            == str(bse_code)
        ]

        if not matches.empty:
            return matches.iloc[0]

    # Fallback in case the delivery source later provides
    # a ticker/symbol field.
    symbol_column = find_column(
        delivery,
        [
            "TckrSymb",
            "SYMBOL",
            "Symbol",
        ],
    )

    if symbol_column and ticker:

        normalized_symbol = (
            delivery[symbol_column]
            .astype(str)
            .str.strip()
            .str.upper()
        )

        matches = delivery[
            normalized_symbol
            == ticker.strip().upper()
        ]

        if not matches.empty:
            return matches.iloc[0]

    return None


# ============================================================
# BSE normalizer
# ============================================================

def normalize_bse(
    bhavcopy: pd.DataFrame,
    delivery: pd.DataFrame | None = None,
    ticker: str | None = None,
    bse_code: str | None = None,
) -> MarketEvent:

    if not ticker and not bse_code:
        raise ValueError(
            "BSE normalization requires ticker or bse_code."
        )

    row = find_bse_row(
        bhavcopy,
        ticker=ticker,
        bse_code=bse_code,
    )

    # --------------------------------------------------------
    # Resolve BSE ticker
    # --------------------------------------------------------

    symbol_column = find_column(
        bhavcopy,
        [
            "TckrSymb",
            "SC_SYMBOL",
            "Symbol",
            "SYMBOL",
        ],
    )

    resolved_ticker = ticker

    if not resolved_ticker and symbol_column:
        resolved_ticker = to_string(
            row[symbol_column]
        )

    resolved_ticker = (
        resolved_ticker or ""
    ).strip().upper()

    # --------------------------------------------------------
    # Resolve BSE instrument/scrip code
    #
    # In the current UDiFF BhavCopy shown above this is
    # FinInstrmId.
    # --------------------------------------------------------

    code_column = find_column(
        bhavcopy,
        [
            "FinInstrmId",
            "SC_CODE",
            "SCRIP_CD",
            "Scrip Code",
        ],
    )

    resolved_bse_code = bse_code

    if not resolved_bse_code and code_column:

        resolved_bse_code = to_string(
            row[code_column]
        )

        if resolved_bse_code:
            resolved_bse_code = (
                resolved_bse_code
                .replace(".0", "")
            )

    # --------------------------------------------------------
    # Market fields
    # --------------------------------------------------------

    trade_date = to_string(
        get_value(
            row,
            [
                "TradDt",
                "Trade Date",
                "DATE",
                "Date",
            ],
        )
    )

    open_price = to_float(
        get_value(
            row,
            [
                "OpnPric",
                "OPEN_PRICE",
                "OPEN",
                "Open Price",
            ],
        )
    )

    high_price = to_float(
        get_value(
            row,
            [
                "HghPric",
                "HIGH_PRICE",
                "HIGH",
                "High Price",
            ],
        )
    )

    low_price = to_float(
        get_value(
            row,
            [
                "LwPric",
                "LOW_PRICE",
                "LOW",
                "Low Price",
            ],
        )
    )

    close_price = to_float(
        get_value(
            row,
            [
                "ClsPric",
                "CLOSE_PRICE",
                "CLOSE",
                "Close Price",
            ],
        )
    )

    previous_close = to_float(
        get_value(
            row,
            [
                "PrvsClsgPric",
                "PREV_CLOSE",
                "Previous Close",
            ],
        )
    )

    volume = to_float(
        get_value(
            row,
            [
                "TtlTradgVol",
                "TTL_TRD_QNTY",
                "Total Trade Quantity",
                "Volume",
            ],
        )
    )

    # --------------------------------------------------------
    # BSE delivery
    # --------------------------------------------------------

    delivery_quantity = None
    delivery_pct = None

    if delivery is not None:

        delivery_row = find_bse_delivery_row(
            delivery,
            bse_code=resolved_bse_code,
            ticker=resolved_ticker,
        )

        if delivery_row is not None:

            delivery_quantity = to_float(
                get_value(
                    delivery_row,
                    [
                        "DELIVERY QTY",
                        "DELIV_QTY",
                        "Deliverable Quantity",
                        "Delivery Quantity",
                    ],
                )
            )

            delivery_pct = to_float(
                get_value(
                    delivery_row,
                    [
                        "DELV. PER.",
                        "DELV_PER",
                        "DELIV_PER",
                        "Delivery %",
                        "Delivery Percentage",
                    ],
                )
            )

    return MarketEvent(
        exchange="BSE",
        ticker=resolved_ticker,
        trade_date=trade_date or "",
        open=open_price,
        high=high_price,
        low=low_price,
        close=close_price,
        previous_close=previous_close,
        volume=volume,
        delivery_quantity=delivery_quantity,
        delivery_pct=delivery_pct,
        price_band=None,
        remarks=None,
        source_files=[
            "bhavcopy",
            "delivery",
        ],
    )


# ============================================================
# JSON helper
# ============================================================

def save_event(
    event: MarketEvent,
    output_path: str | Path,
) -> Path:

    import json

    output_path = Path(output_path)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            event.to_dict(),
            file,
            indent=2,
            default=str,
        )

    return output_path