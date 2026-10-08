"""Build Dakota unified real NSE/BSE market history."""
from __future__ import annotations

from src.market.history_store import build_market_history


def main() -> None:
    df = build_market_history()
    print("=" * 64)
    print("DAKOTA REAL MARKET HISTORY")
    print("=" * 64)
    print(f"Rows:       {len(df)}")
    print(f"Tickers:    {df.ticker.nunique()}")
    print(f"Exchanges:  {', '.join(sorted(df.exchange.unique()))}")
    print(f"Date range: {df.trade_date.min().date()} -> {df.trade_date.max().date()}")
    print()
    for exchange in sorted(df.exchange.unique()):
        part = df[df.exchange == exchange]
        print(f"{exchange}: {len(part)} rows / {part.ticker.nunique()} tickers / {part.trade_date.nunique()} trading day(s)")
    print()
    print("Target rows:")
    targets = df[df.ticker.isin(["CDSL", "AEGISLOG"])][[
        "exchange", "ticker", "trade_date", "close", "volume",
        "delivery_quantity", "delivery_pct", "price_band"
    ]]
    print(targets.to_string(index=False))


if __name__ == "__main__":
    main()
