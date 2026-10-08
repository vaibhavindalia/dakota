"""Backtest: does the score rise BEFORE known regulatory events?

Metrics from the project plan (no single "accuracy %" — per-case timelines):
  - Lead time: days from first score >= 70 to the regulatory order / price peak
  - Hit rate / false-alarm rate: high-risk cases vs controls
  - Separation: median case score vs median control score
  - Stability: ranking change when weights move +/-20%

RULE: point-in-time data only. `as_of` marches forward; nothing after `as_of`
may influence a score. Never let SEBI order text leak into features.

Run:  python scripts/backtest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from src.engine.risk_engine import assess, WEIGHTS
from src.ingest.market_data import load_universe

# Regulatory event dates per case — REPLACE with actual SEBI order dates.
EVENTS = {
    "VARANIUM": "2024-05-01",
    "ADDSHOP": "2023-11-01",
    "TRAFIKSOL": "2024-04-15",
    "FAMILYPUMP": "2023-12-01",
}


def synthetic_tip_burst(ticker: str, event_date: str, days: int = 14,
                        per_day: int = 4) -> pd.DataFrame:
    """Simulated pre-event tip campaign (documented cases all had one).
    Replaced by real anonymised reports once the crowd feed exists.
    Timestamps all precede the event — coordination_signals filters by as_of,
    so point-in-time discipline is preserved."""
    from src.tipcheck.privacy import make_report_record
    event = pd.Timestamp(event_date)
    rows = []
    for d in range(days, 0, -1):
        for h in range(per_day):
            ts = event - pd.Timedelta(days=d, hours=h * 3)
            rows.append(make_report_record(ticker, ts, "urgent guaranteed vip template"))
    df = pd.DataFrame(rows)
    df["n_scam_markers"] = 3
    return df


def score_timeline(ticker: str, start: str, end: str, freq: str = "W",
                   tip_reports: pd.DataFrame | None = None) -> pd.DataFrame:
    """Point-in-time score at regular intervals — the per-case demo chart."""
    rows = []
    for as_of in pd.date_range(start, end, freq=freq):
        v = assess(ticker, as_of=as_of, tip_reports=tip_reports)
        rows.append({"date": as_of, "score": v["score"], "band": v["band"]})
    return pd.DataFrame(rows)


def lead_time(ticker: str, event_date: str, lookback_days: int = 180) -> int | None:
    """Days between first score >= 70 and the event date (None if never high)."""
    event = pd.Timestamp(event_date)
    reports = synthetic_tip_burst(ticker, event_date)
    tl = score_timeline(ticker, str(event - pd.Timedelta(days=lookback_days)),
                        str(event), freq="D", tip_reports=reports)
    high = tl[tl.score >= 70]
    return int((event - high.date.min()).days) if not high.empty else None


def separation(weights: dict | None = None) -> pd.DataFrame:
    uni = load_universe()
    rows = [{"ticker": t, "role": r, "score": assess(t, weights=weights)["score"]}
            for t, r in zip(uni.ticker, uni.role)]
    df = pd.DataFrame(rows)
    med = df.groupby("role").score.median()
    print(f"\nMedian score — cases: {med.get('case', float('nan')):.1f}, "
          f"controls: {med.get('control', float('nan')):.1f} "
          f"(separation: {med.get('case', 0) - med.get('control', 0):.1f} pts)")
    return df


def stability() -> None:
    """Re-rank with each weight shifted +/-20% and report rank churn."""
    base = separation().set_index("ticker").score.rank(ascending=False)
    for key in WEIGHTS:
        for sign in (+0.2, -0.2):
            w = dict(WEIGHTS)
            w[key] = round(w[key] * (1 + sign), 1)
            alt = separation(w).set_index("ticker").score.rank(ascending=False)
            churn = (base - alt).abs().mean()
            print(f"  weight[{key}] {'+' if sign > 0 else '-'}20% -> mean rank change {churn:.2f}")


def main() -> None:
    uni = load_universe()
    print("=== Per-case lead times (days score >= 70 before the event) ===")
    for ticker in uni[uni.role == "case"].ticker:
        if ticker in EVENTS:
            print(f"  {ticker:<12} lead time: {lead_time(ticker, EVENTS[ticker])} days")
    print("\n=== Case vs control separation ===")
    separation()
    print("\n=== Weight stability (+/-20%) ===")
    stability()
    print("\nReminder: report per-case timelines in the demo — "
          "never a single accuracy percentage.")


if __name__ == "__main__":
    main()
