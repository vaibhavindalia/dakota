"""Dakota real-market history store.

Builds a unified, point-in-time daily market table from the raw NSE/BSE
bhavcopy + delivery files already collected in data/raw/.

Important: exchange files can mix ISO dates such as 2026-10-06 with human
readable dates such as 06-Oct-2026. The parser below handles both explicitly;
using a blanket dayfirst=True on ISO dates would silently turn 2026-10-06 into
2026-06-10 and break joins with delivery files.

This module uses only files that actually exist locally. It does not generate
synthetic prices and it never fills missing delivery data with a fabricated
value.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW_ROOT = ROOT / "data" / "raw"
DEFAULT_OUTPUT = ROOT / "data" / "market_history.csv"

CANONICAL_COLUMNS = [
    "exchange",
    "ticker",
    "bse_code",
    "isin",
    "trade_date",
    "series",
    "open",
    "high",
    "low",
    "close",
    "previous_close",
    "volume",
    "delivery_quantity",
    "delivery_pct",
    "price_band",
    "remarks",
    "source_bhavcopy",
    "source_delivery",
    "source_priceband",
]


def _clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip().replace("\ufeff", "") for c in out.columns]
    return out


def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(",", "", regex=False).str.strip(),
        errors="coerce",
    )


def _first_existing(df: pd.DataFrame, names: Iterable[str]) -> str | None:
    lookup = {str(c).strip().upper(): c for c in df.columns}
    for name in names:
        found = lookup.get(name.upper())
        if found is not None:
            return found
    return None


def _parse_mixed_dates(series: pd.Series) -> pd.Series:
    """Parse both ISO (YYYY-MM-DD) and day-first display dates safely."""
    raw = series.astype(str).str.strip()
    out = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")

    iso_mask = raw.str.match(
        r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:\s.*)?$",
        na=False,
    )

    if iso_mask.any():
        out.loc[iso_mask] = pd.to_datetime(
            raw.loc[iso_mask],
            errors="coerce",
            dayfirst=False,
        )

    non_iso = ~iso_mask
    if non_iso.any():
        out.loc[non_iso] = pd.to_datetime(
            raw.loc[non_iso],
            errors="coerce",
            dayfirst=True,
        )

    return out.dt.normalize()


def _date_from_columns(df: pd.DataFrame, names: Iterable[str]) -> pd.Series:
    col = _first_existing(df, names)
    if col is None:
        return pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")
    return _parse_mixed_dates(df[col])


def _date_from_filename(path: Path) -> pd.Timestamp | None:
    # 06102026 / 06-10-2026 / 06_10_2026
    match = re.search(r"(?<!\d)(\d{2})[-_]?([01]\d)[-_]?(20\d{2})(?!\d)", path.name)
    if match:
        d, m, y = match.groups()
        try:
            return pd.Timestamp(year=int(y), month=int(m), day=int(d)).normalize()
        except ValueError:
            pass

    # 20261006 / 2026-10-06 / 2026_10_06
    match = re.search(r"(?<!\d)(20\d{2})[-_]?([01]\d)[-_]?(\d{2})(?!\d)", path.name)
    if match:
        y, m, d = match.groups()
        try:
            return pd.Timestamp(year=int(y), month=int(m), day=int(d)).normalize()
        except ValueError:
            pass

    return None


def _read_csv(path: Path) -> pd.DataFrame:
    return _clean_columns(pd.read_csv(path, low_memory=False))


def _nse_bhavcopy(path: Path) -> pd.DataFrame:
    df = _read_csv(path)

    ticker_col = _first_existing(df, ["TckrSymb", "Symbol"])
    series_col = _first_existing(df, ["SctySrs", "Series"])
    isin_col = _first_existing(df, ["ISIN"])
    date = _date_from_columns(df, ["TradDt", "Date", "DATE1"])

    if ticker_col is None:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)

    if series_col is not None:
        df = df[df[series_col].astype(str).str.upper().isin(["EQ", "SM", "BE", "ST", ""])].copy()
        date = date.loc[df.index]

    out = pd.DataFrame(index=df.index)
    out["exchange"] = "NSE"
    out["ticker"] = df[ticker_col].astype(str).str.strip().str.upper()
    out["bse_code"] = pd.NA
    out["isin"] = df[isin_col].astype(str).str.strip() if isin_col else pd.NA
    out["trade_date"] = date
    out["series"] = df[series_col].astype(str).str.strip() if series_col else pd.NA

    mapping = {
        "open": ["OpnPric", "OPEN_PRICE", "Open"],
        "high": ["HghPric", "HIGH_PRICE", "High"],
        "low": ["LwPric", "LOW_PRICE", "Low"],
        "close": ["ClsPric", "CLOSE_PRICE", "Close"],
        "previous_close": ["PrvsClsgPric", "PREV_CLOSE", "Previous Close"],
        "volume": ["TtlTradgVol", "TTL_TRD_QNTY", "Volume"],
    }

    for target, names in mapping.items():
        col = _first_existing(df, names)
        out[target] = _num(df[col]) if col else pd.NA

    out["delivery_quantity"] = pd.NA
    out["delivery_pct"] = pd.NA
    out["price_band"] = pd.NA
    out["remarks"] = pd.NA
    out["source_bhavcopy"] = path.name
    out["source_delivery"] = pd.NA
    out["source_priceband"] = pd.NA

    return out.reset_index(drop=True)


def _nse_delivery(path: Path) -> pd.DataFrame:
    df = _read_csv(path)
    ticker_col = _first_existing(df, ["SYMBOL", "Symbol"])
    if ticker_col is None:
        return pd.DataFrame()

    date = _date_from_columns(df, ["DATE1", "DATE", "TradDt"])
    out = pd.DataFrame(index=df.index)
    out["ticker"] = df[ticker_col].astype(str).str.strip().str.upper()
    out["trade_date"] = date

    qty_col = _first_existing(df, ["DELIV_QTY", "DELIVERY QTY"])
    pct_col = _first_existing(df, ["DELIV_PER", "DELV. PER.", "DELIVERY PCT"])
    out["delivery_quantity"] = _num(df[qty_col]) if qty_col else pd.NA
    out["delivery_pct"] = _num(df[pct_col]) if pct_col else pd.NA
    out["source_delivery"] = path.name
    return out.reset_index(drop=True)


def _nse_priceband(path: Path) -> pd.DataFrame:
    df = _read_csv(path)
    ticker_col = _first_existing(df, ["Symbol", "SYMBOL"])
    if ticker_col is None:
        return pd.DataFrame()

    band_col = _first_existing(df, ["Band", "Price Band"])
    out = pd.DataFrame(index=df.index)
    out["ticker"] = df[ticker_col].astype(str).str.strip().str.upper()
    out["price_band"] = (
        df[band_col].astype(str).str.strip()
        if band_col
        else pd.NA
    )
    remarks_col = _first_existing(df, ["Remarks", "REMARKS"])
    out["remarks"] = (
        df[remarks_col].astype(str).str.strip()
        if remarks_col
        else pd.NA
    )
    out["source_priceband"] = path.name
    return out.reset_index(drop=True)


def _bse_bhavcopy(path: Path) -> pd.DataFrame:
    df = _read_csv(path)

    ticker_col = _first_existing(df, ["TckrSymb", "Ticker"])
    code_col = _first_existing(df, ["FinInstrmId", "SCRIP CODE", "Security Code"])
    series_col = _first_existing(df, ["SctySrs", "Series"])
    isin_col = _first_existing(df, ["ISIN"])

    if ticker_col is None and code_col is None:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)

    date = _date_from_columns(df, ["TradDt", "BizDt", "DATE"])

    if series_col is not None:
        series_upper = df[series_col].astype(str).str.upper()
        keep = series_upper.isin(["A", "B", "T", "X", "XT", "Z", "M", "F", "EQ", ""])
        df = df[keep].copy()
        date = date.loc[df.index]

    out = pd.DataFrame(index=df.index)
    out["exchange"] = "BSE"
    out["ticker"] = (
        df[ticker_col].astype(str).str.strip().str.upper()
        if ticker_col else pd.NA
    )
    out["bse_code"] = (
        df[code_col].astype(str).str.extract(r"(\d+)", expand=False)
        if code_col else pd.NA
    )
    out["isin"] = df[isin_col].astype(str).str.strip() if isin_col else pd.NA
    out["trade_date"] = date
    out["series"] = df[series_col].astype(str).str.strip() if series_col else pd.NA

    mapping = {
        "open": ["OpnPric", "OPEN_PRICE", "Open"],
        "high": ["HghPric", "HIGH_PRICE", "High"],
        "low": ["LwPric", "LOW_PRICE", "Low"],
        "close": ["ClsPric", "CLOSE_PRICE", "Close"],
        "previous_close": ["PrvsClsgPric", "PREV_CLOSE", "Previous Close"],
        "volume": ["TtlTradgVol", "TTL_TRD_QNTY", "Volume"],
    }

    for target, names in mapping.items():
        col = _first_existing(df, names)
        out[target] = _num(df[col]) if col else pd.NA

    out["delivery_quantity"] = pd.NA
    out["delivery_pct"] = pd.NA
    out["price_band"] = pd.NA
    out["remarks"] = pd.NA
    out["source_bhavcopy"] = path.name
    out["source_delivery"] = pd.NA
    out["source_priceband"] = pd.NA
    return out.reset_index(drop=True)


def _bse_delivery(path: Path) -> pd.DataFrame:
    df = _read_csv(path)
    code_col = _first_existing(df, ["SCRIP CODE", "Security Code"])
    if code_col is None:
        return pd.DataFrame()

    out = pd.DataFrame(index=df.index)
    out["bse_code"] = df[code_col].astype(str).str.extract(r"(\d+)", expand=False)
    out["trade_date"] = _date_from_columns(df, ["DATE", "DATE1", "TradDt"])

    qty_col = _first_existing(df, ["DELIVERY QTY", "DELIV_QTY"])
    pct_col = _first_existing(df, ["DELV. PER.", "DELIV_PER"])
    out["delivery_quantity"] = _num(df[qty_col]) if qty_col else pd.NA
    out["delivery_pct"] = _num(df[pct_col]) if pct_col else pd.NA
    out["source_delivery"] = path.name
    return out.reset_index(drop=True)


def _attach_nse_side_data(
    base: pd.DataFrame,
    delivery_files: list[Path],
    priceband_files: list[Path],
) -> pd.DataFrame:
    if base.empty:
        return base

    delivery = (
        pd.concat(
            [_nse_delivery(p) for p in delivery_files],
            ignore_index=True,
        )
        if delivery_files
        else pd.DataFrame()
    )

    if not delivery.empty:
        base = base.merge(
            delivery[
                [
                    "ticker",
                    "trade_date",
                    "delivery_quantity",
                    "delivery_pct",
                    "source_delivery",
                ]
            ],
            on=["ticker", "trade_date"],
            how="left",
            suffixes=("", "_new"),
        )
        base["delivery_quantity"] = base["delivery_quantity_new"].combine_first(
            base["delivery_quantity"]
        )
        base["delivery_pct"] = base["delivery_pct_new"].combine_first(
            base["delivery_pct"]
        )
        base["source_delivery"] = base["source_delivery_new"].combine_first(
            base["source_delivery"]
        )
        base = base.drop(columns=[c for c in base.columns if c.endswith("_new")])

    rows: list[pd.DataFrame] = []
    for p in priceband_files:
        part = _nse_priceband(p)
        trade_date = _date_from_filename(p)
        if trade_date is not None:
            part["trade_date"] = trade_date
            rows.append(part)

    if rows:
        bands = pd.concat(rows, ignore_index=True)
        base = base.merge(
            bands[
                [
                    "ticker",
                    "trade_date",
                    "price_band",
                    "remarks",
                    "source_priceband",
                ]
            ],
            on=["ticker", "trade_date"],
            how="left",
            suffixes=("", "_new"),
        )
        base["price_band"] = base["price_band_new"].combine_first(base["price_band"])
        base["remarks"] = base["remarks_new"].combine_first(base["remarks"])
        base["source_priceband"] = base["source_priceband_new"].combine_first(
            base["source_priceband"]
        )
        base = base.drop(columns=[c for c in base.columns if c.endswith("_new")])

    return base


def _attach_bse_side_data(
    base: pd.DataFrame,
    delivery_files: list[Path],
) -> pd.DataFrame:
    if base.empty or not delivery_files:
        return base

    delivery_parts = [_bse_delivery(p) for p in delivery_files]
    valid_parts = [p for p in delivery_parts if not p.empty]
    delivery = pd.concat(valid_parts, ignore_index=True) if valid_parts else pd.DataFrame()

    if delivery.empty:
        return base

    base = base.merge(
        delivery[
            [
                "bse_code",
                "trade_date",
                "delivery_quantity",
                "delivery_pct",
                "source_delivery",
            ]
        ],
        on=["bse_code", "trade_date"],
        how="left",
        suffixes=("", "_new"),
    )

    base["delivery_quantity"] = base["delivery_quantity_new"].combine_first(
        base["delivery_quantity"]
    )
    base["delivery_pct"] = base["delivery_pct_new"].combine_first(
        base["delivery_pct"]
    )
    base["source_delivery"] = base["source_delivery_new"].combine_first(
        base["source_delivery"]
    )
    return base.drop(columns=[c for c in base.columns if c.endswith("_new")])


def build_market_history(
    raw_root: str | Path = DEFAULT_RAW_ROOT,
    output_path: str | Path = DEFAULT_OUTPUT,
) -> pd.DataFrame:
    raw_root = Path(raw_root)
    nse_root = raw_root / "nse"
    bse_root = raw_root / "bse"

    nse_bhav = sorted(nse_root.glob("*.csv")) if nse_root.exists() else []
    nse_bhav = [
        p
        for p in nse_bhav
        if "BhavCopy_NSE_CM" in p.name
        or "bhavcopy" in p.name.lower()
    ]
    nse_delivery = sorted(nse_root.glob("sec_bhavdata_full_*.csv"))
    nse_priceband = sorted(nse_root.glob("sec_list_*.csv"))

    bse_bhav = (
        sorted(bse_root.glob("BhavCopy_BSE_CM_*.CSV"))
        if bse_root.exists()
        else []
    )
    bse_delivery = (
        sorted(bse_root.glob("SCBSEALL*.csv"))
        if bse_root.exists()
        else []
    )

    parts: list[pd.DataFrame] = []

    for path in nse_bhav:
        part = _nse_bhavcopy(path)
        part = _attach_nse_side_data(
            part,
            nse_delivery,
            nse_priceband,
        )
        parts.append(part)

    for path in bse_bhav:
        part = _bse_bhavcopy(path)
        part = _attach_bse_side_data(
            part,
            bse_delivery,
        )
        parts.append(part)

    if not parts:
        raise FileNotFoundError(
            f"No NSE/BSE bhavcopy CSVs were found under {raw_root}"
        )

    history = pd.concat(parts, ignore_index=True)

    history = history[history["trade_date"].notna()].copy()
    history = history[history["ticker"].notna()].copy()
    history["ticker"] = history["ticker"].astype(str).str.strip().str.upper()
    history["trade_date"] = pd.to_datetime(history["trade_date"]).dt.normalize()

    history = history[history["close"].notna()].copy()
    history = history[history["volume"].fillna(0) >= 0].copy()

    history = history[CANONICAL_COLUMNS].drop_duplicates(
        subset=["exchange", "ticker", "trade_date"],
        keep="last",
    )
    history = history.sort_values(
        ["trade_date", "exchange", "ticker"]
    ).reset_index(drop=True)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    history.to_csv(output_path, index=False)

    return history


def load_history(
    ticker: str,
    exchange: str | None = None,
    path: str | Path = DEFAULT_OUTPUT,
) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=CANONICAL_COLUMNS)

    df = pd.read_csv(path, parse_dates=["trade_date"])
    df["ticker"] = df["ticker"].astype(str).str.upper()

    mask = df["ticker"].eq(ticker.upper().strip())
    if exchange:
        mask &= df["exchange"].eq(exchange.upper().strip())

    return df.loc[mask].sort_values("trade_date").reset_index(drop=True)


if __name__ == "__main__":
    df = build_market_history()
    print("DAKOTA MARKET HISTORY BUILD")
    print("=" * 60)
    print(f"Rows:       {len(df)}")
    print(f"Tickers:    {df.ticker.nunique()}")
    print(f"Exchanges:  {', '.join(sorted(df.exchange.unique()))}")
    print(
        f"Date range: {df.trade_date.min().date()} -> {df.trade_date.max().date()}"
    )
    print()
    print(df.head(10).to_string(index=False))
