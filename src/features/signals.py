"""Feature blocks -> the five signal groups of the Dakota risk engine.

Each group function returns a SignalResult(points, max_points, reasons).
Rules are deliberately simple and explainable — every point must be traceable
to a sentence a judge/retail user can read. Tune thresholds on the backtest,
not by vibes.

All functions take `as_of` and must NOT use data after that date (point-in-time).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from src.ingest import market_data, shareholding, fundamentals


@dataclass
class SignalResult:
    points: float
    max_points: float
    reasons: list[str] = field(default_factory=list)

    def add(self, pts: float, reason: str):
        self.points = min(self.points + pts, self.max_points)
        self.reasons.append(reason)


# ---------------------------------------------------------------- G1 (25)
def coordination_signals(ticker: str, as_of: pd.Timestamp,
                         tip_reports: pd.DataFrame | None = None) -> SignalResult:
    """Coordination & tip signals (25): report counts, near-duplicates,
    scam markers, channel overlap. Fed by src.tipcheck + src.campaign.

    `tip_reports`: anonymised reports with columns
        [ticker, ts, fingerprint, n_scam_markers, source_label]
    """
    r = SignalResult(0, 25)
    if tip_reports is None or tip_reports.empty:
        return r
    rep = tip_reports[(tip_reports.ticker == ticker) & (tip_reports.ts <= as_of)]
    if rep.empty:
        return r

    # Burst: many distinct reporters in a trailing 24h window (the plan's
    # documented example: 31 users / 40 minutes on a real case)
    window = rep[rep.ts >= as_of - pd.Timedelta(hours=24)]
    n_reporters = window.shape[0]
    if n_reporters >= 20:
        r.add(10, f"{n_reporters} reports for this ticker within 24 hours")
    elif n_reporters >= 8:
        r.add(6, f"{n_reporters} reports for this ticker within 24 hours")
    elif n_reporters >= 3:
        r.add(3, f"{n_reporters} reports for this ticker within 24 hours")

    # Near-duplicates: same text fingerprint from different reporters
    dup = window.fingerprint.value_counts()
    if not dup.empty and dup.iloc[0] >= 5:
        r.add(8, f"Near-duplicate tip text seen {int(dup.iloc[0])} times — copy-paste coordination")
    elif not dup.empty and dup.iloc[0] >= 2:
        r.add(4, "Repeated near-identical tip text")

    # Scam markers inside the messages (from tipcheck.parser)
    markers = int(window.n_scam_markers.sum()) if "n_scam_markers" in window else 0
    if markers >= 5:
        r.add(7, f"Strong scam language in tips ({markers} markers: guaranteed returns, VIP funnel, app/APK diversion...)")
    elif markers >= 2:
        r.add(4, "Scam-style language present in tips")
    return r


# ---------------------------------------------------------------- G2 (25)
def promoter_signals(ticker: str, as_of: pd.Timestamp) -> SignalResult:
    """Promoter & shareholding behaviour (25): promoter trend, public-holding
    jump after peak, lock-in window."""
    r = SignalResult(0, 25)
    trend = shareholding.promoter_trend(ticker, as_of)
    if trend["quarters"] < 2:
        return r  # no data = no points, say nothing

    if trend["promoter_delta_pp"] <= -10:
        r.add(15, f"Promoter holding fell {abs(trend['promoter_delta_pp'])}pp over "
                  f"{trend['quarters']} quarters while public holding rose")
    elif trend["promoter_falling"]:
        r.add(9, f"Promoter holding fell {abs(trend['promoter_delta_pp'])}pp "
                 f"while public holding rose {trend['public_delta_pp']}pp")

    d = shareholding.days_to_lockin_expiry(ticker, as_of)
    if d is not None:
        if -30 <= d <= 60:
            r.add(10, f"Lock-in expiry {'in ' + str(d) + ' days' if d >= 0 else str(-d) + ' days ago'} "
                      "— insiders can legally sell in this window")
        elif 60 < d <= 120:
            r.add(4, f"Lock-in expiry approaching ({d} days)")
        elif -365 <= d < -30 and trend["promoter_falling"]:
            r.add(6, "Promoter has been selling in the year after lock-in expiry")
    return r


# ---------------------------------------------------------------- G3 (20)
def market_footprint_signals(ticker: str, as_of: pd.Timestamp) -> SignalResult:
    """Market footprint (20): volume/delivery spike vs 20-day avg, circuit
    hits, price vs issue price."""
    r = SignalResult(0, 20)
    df = market_data.load_ohlcv(ticker)
    df = df[df.date <= as_of]
    if len(df) < 25:
        return r

    # Volume spike: max 5-day average vs the 20 sessions BEFORE it, scanned
    # over the last 40 sessions — catches the spike even mid-dump.
    vol = df.volume.reset_index(drop=True)
    roll5 = vol.rolling(5).mean()
    spikes = []
    for i in range(max(25, len(df) - 40), len(df)):
        prior = vol.iloc[i - 20:i].mean()
        if prior > 0:
            spikes.append(roll5.iloc[i] / prior)
    vol_ratio = max(spikes, default=1.0)
    if vol_ratio >= 5:
        r.add(8, f"Volume spiked to {vol_ratio:.1f}× the recent 20-day average")
    elif vol_ratio >= 3:
        r.add(5, f"Volume spiked to {vol_ratio:.1f}× the recent 20-day average")
    elif vol_ratio >= 2:
        r.add(2, f"Volume elevated at {vol_ratio:.1f}× the 20-day average")

    # Delivery collapse during the high-volume window = distribution, not
    # investment buying. Compare the last 40 sessions with the 40 before.
    if len(df) >= 80:
        del_recent = df.tail(40).delivery_pct.mean()
        del_hist = df.iloc[-80:-40].delivery_pct.mean()
        if vol_ratio >= 2 and del_recent < 0.7 * del_hist:
            r.add(5, f"Delivery share dropped to {del_recent:.0f}% (from ~{del_hist:.0f}%) "
                     "— speculative, not investment buying")

    hits30 = int(market_data.circuit_hits(df.tail(30)).sum())
    if hits30 >= 5:
        r.add(4, f"{hits30} circuit-band hits in the last 30 sessions")
    elif hits30 >= 2:
        r.add(2, f"{hits30} circuit-band hits in the last 30 sessions")

    # Pump shape: big run-up to a peak within ~3 months, then collapse.
    if len(df) >= 60:
        window = df.close.tail(60)
        peak, last = window.max(), df.close.iloc[-1]
        runup = peak / window.iloc[0] - 1
        drawdown = last / peak - 1
        if runup >= 0.8:
            r.add(3, f"Price ran up {runup:.0%} to its peak within ~3 months on thin float")
        if drawdown <= -0.3:
            r.add(3, f"Price already {drawdown:.0%} below the peak — late buyers are trapped")
    return r


# ---------------------------------------------------------------- G4 (15)
def financial_integrity_signals(ticker: str, as_of: pd.Timestamp) -> SignalResult:
    """Financial integrity red flags (15): revenue jump, concentration,
    related-party share, use of proceeds."""
    r = SignalResult(0, 15)
    f = fundamentals.red_flags(ticker, as_of)
    if f["years_available"] == 0:
        return r
    if f["revenue_jump"]:
        r.add(4, "Revenue more than doubled in the latest year (year-end jump)")
    if f["unbilled_high"]:
        r.add(3, "High share of unbilled revenue")
    if f["concentration_high"]:
        r.add(3, "Heavy dependence on a single customer")
    if f["related_party_high"]:
        r.add(3, "Large related-party transaction share")
    if f["proceeds_misuse"]:
        r.add(2, "IPO proceeds not used as stated in the offer document")
    return r


# ---------------------------------------------------------------- G5 (15)
def structure_signals(ticker: str, as_of: pd.Timestamp) -> SignalResult:
    """Structure (15): free float, issue size, SME listing, surveillance list."""
    r = SignalResult(0, 15)
    uni = market_data.load_universe()
    row = uni[uni.ticker == ticker]
    if row.empty:
        return r
    row = row.iloc[0]

    if str(row.segment).upper() == "SME":
        r.add(5, "Listed on the SME platform (thin liquidity, wider manipulation risk)")
    if pd.notna(row.free_float_pct):
        if row.free_float_pct < 25:
            r.add(5, f"Very thin free float ({row.free_float_pct:.0f}%)")
        elif row.free_float_pct < 30:
            r.add(3, f"Low free float ({row.free_float_pct:.0f}%)")
    if pd.notna(row.issue_size_cr) and row.issue_size_cr < 50:
        r.add(3, f"Small issue size (₹{row.issue_size_cr:.0f} cr)")

    # TODO(live-data): NSE GSM/ASM surveillance-list check.
    # For the demo, read an optional manual flag column if you add one to universe.csv.
    if "surveillance_flag" in uni.columns and bool(row.get("surveillance_flag", False)):
        r.add(2, "Currently on an exchange surveillance list (GSM/ASM)")
    return r
