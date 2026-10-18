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
try:
    from src.ingest.free_data_fetcher import load_live_fundamentals, load_live_shareholding
    _HAS_LIVE = True
except ImportError:
    _HAS_LIVE = False
    import pandas as _pd
    def load_live_fundamentals(ticker=None): return _pd.DataFrame()
    def load_live_shareholding(ticker=None): return _pd.DataFrame()


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

    # Auto-link database tip reports if not explicitly provided
    if tip_reports is None or tip_reports.empty:
        try:
            import sqlite3
            from pathlib import Path
            db_p = Path(__file__).resolve().parents[2] / "data" / "dakota.db"
            if db_p.exists():
                conn = sqlite3.connect(str(db_p), timeout=1.0)
                cur = conn.cursor()
                cur.execute(
                    "SELECT ticker, ts, fingerprint, source_label FROM tip_events WHERE ticker = ? ORDER BY ts DESC LIMIT 50",
                    (ticker.upper(),)
                )
                db_rows = cur.fetchall()
                conn.close()
                if db_rows:
                    tip_reports = pd.DataFrame(db_rows, columns=["ticker", "ts", "fingerprint", "source_label"])
                    tip_reports["ts"] = pd.to_datetime(tip_reports["ts"]).dt.tz_localize(None)
                    tip_reports["n_scam_markers"] = 1
        except Exception:
            pass

    if tip_reports is None or tip_reports.empty:
        return r

    # Normalize timestamp timezones for clean comparison
    tip_ts = pd.to_datetime(tip_reports["ts"])
    if tip_ts.dt.tz is not None:
        tip_ts = tip_ts.dt.tz_localize(None)
    tip_reports = tip_reports.copy()
    tip_reports["ts"] = tip_ts

    as_of_naive = as_of.tz_localize(None) if as_of.tzinfo is not None else as_of

    t_aliases = [ticker.upper()]
    if ticker.upper() in ["CLOUD", "VARANIUM"]:
        t_aliases.extend(["CLOUD", "VARANIUM"])
    elif ticker.upper() in ["ASRL", "ADDSHOP"]:
        t_aliases.extend(["ASRL", "ADDSHOP"])
    elif ticker.upper() in ["AFCOM", "FAMILYPUMP"]:
        t_aliases.extend(["AFCOM", "FAMILYPUMP"])

    rep = tip_reports[(tip_reports.ticker.isin(t_aliases)) & (tip_reports.ts <= as_of_naive)]
    if rep.empty:
        return r

    # Burst in trailing 24h window
    window24 = rep[rep.ts >= as_of_naive - pd.Timedelta(hours=24)]
    # Trailing 14-day window for coordinated campaign tracking
    window14d = rep[rep.ts >= as_of_naive - pd.Timedelta(days=14)]

    n_reporters = window24.shape[0]
    n_14d = window14d.shape[0]
    if n_reporters >= 20:
        r.add(10, f"{n_reporters} reports for this ticker within 24 hours")
    elif n_reporters >= 8:
        r.add(6, f"{n_reporters} reports for this ticker within 24 hours")
    elif n_reporters >= 3:
        r.add(3, f"{n_reporters} reports for this ticker within 24 hours")
    elif n_14d >= 10:
        r.add(5, f"{n_14d} coordinated tip reports logged in the past 14 days")
    elif n_14d >= 3:
        r.add(2, f"{n_14d} tip reports logged in the past 14 days")

    # Near-duplicates: same text fingerprint across reporters
    dup = window14d.fingerprint.value_counts() if not window14d.empty else pd.Series(dtype=int)
    if not dup.empty and dup.iloc[0] >= 5:
        r.add(8, f"Near-duplicate tip text seen {int(dup.iloc[0])} times — copy-paste coordination")
    elif not dup.empty and dup.iloc[0] >= 2:
        r.add(4, "Repeated near-identical tip text across reports")

    # Scam markers inside the messages (from tipcheck.parser)
    markers = int(window14d.n_scam_markers.sum()) if "n_scam_markers" in window14d else 0
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
    # Check live shareholding data (from free daily fetch)
    try:
        live_sh = load_live_shareholding(ticker)
        if not live_sh.empty:
            lrow = live_sh.iloc[-1]
            delta_val = lrow.get("promoter_delta_pp")
            dumping = str(lrow.get("promoter_dumping_flag", "False")) == "True"
            if dumping or (delta_val is not None and float(delta_val) <= -5.0):
                r.add(15, "Promoter sold " + str(abs(float(delta_val))) + "pp of holding last quarter (live data: promoter dumping alert)")
            elif delta_val is not None and float(delta_val) <= -2.0:
                r.add(7, "Promoter reduced holding by " + str(abs(float(delta_val))) + "pp (live data)")
    except Exception:
        pass

    trend = shareholding.promoter_trend(ticker, as_of)
    if trend["quarters"] < 2:
        return r  # no manual data - only live checks above apply

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
    hits, price vs issue price, volatility & technical overbought momentum."""
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

    # Technical Momentum / RSI Overbought Exhaustion Check
    if len(df) >= 20:
        c = df["close"]
        delta = c.diff()
        gain = delta.clip(lower=0).rolling(14, min_periods=14).mean()
        loss = (-delta.clip(upper=0)).rolling(14, min_periods=14).mean()
        rs = gain / loss.replace(0, float("nan"))
        rsi = 100 - (100 / (1 + rs))
        last_rsi = rsi.iloc[-1] if not rsi.empty else None
        if pd.notna(last_rsi) and last_rsi >= 80 and vol_ratio >= 1.5:
            r.add(4, f"Overbought RSI exhaustion ({last_rsi:.1f}) with elevated volume — distribution risk")

    # Extreme Historical Volatility (20-day annualized)
    if len(df) >= 20:
        pct = df["close"].pct_change().dropna()
        if len(pct) >= 20:
            ann_vol = pct.tail(20).std() * (252 ** 0.5) * 100
            if ann_vol >= 90:
                r.add(3, f"Severe historical volatility ({ann_vol:.0f}% annualized) — erratic price action")

    # Delivery collapse during the high-volume window = distribution, not
    # investment buying. Compare the last 40 sessions with the 40 before.
    # (delivery_pct is NaN when sourced from yfinance — skip check safely)
    if len(df) >= 80 and "delivery_pct" in df.columns:
        del_recent = df.tail(40).delivery_pct.mean()
        del_hist = df.iloc[-80:-40].delivery_pct.mean()
        if (pd.notna(del_recent) and pd.notna(del_hist) and del_hist > 0
                and vol_ratio >= 2 and del_recent < 0.7 * del_hist):
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
    related-party share, use of proceeds, regulatory action."""
    r = SignalResult(0, 15)

    # Check SEBI regulatory action / interim enforcement order on record
    try:
        uni = market_data.load_universe()
        t_aliases = [ticker.upper()]
        if ticker.upper() in ["CLOUD", "VARANIUM"]:
            t_aliases.extend(["CLOUD", "VARANIUM"])
        elif ticker.upper() in ["ASRL", "ADDSHOP"]:
            t_aliases.extend(["ASRL", "ADDSHOP"])
        elif ticker.upper() in ["AFCOM", "FAMILYPUMP"]:
            t_aliases.extend(["AFCOM", "FAMILYPUMP"])
        match = uni[uni.ticker.isin(t_aliases) | uni.market_id.isin(t_aliases)]
        if not match.empty:
            row = match.iloc[0]
            ev_dt = row.get("case_event_date")
            if pd.notna(ev_dt) and str(ev_dt).strip() != "":
                if as_of >= pd.Timestamp(ev_dt):
                    r.add(10, f"SEBI regulatory investigation / interim enforcement order on record ({ev_dt})")
    except Exception:
        pass

    # Check live fundamentals (from free daily fetch via yfinance / Screener.in)
    try:
        live_fund = load_live_fundamentals(ticker)
        if not live_fund.empty:
            lf = live_fund.iloc[-1]
            if str(lf.get("zero_revenue_flag", "False")) == "True":
                r.add(5, "Company has near-zero revenue but significant market cap (shell company risk)")
            if str(lf.get("high_debt_flag", "False")) == "True":
                r.add(4, "Debt is more than 3x annual revenue (high leverage red flag)")
            if str(lf.get("price_pump_flag", "False")) == "True":
                pct = lf.get("price_52w_change_pct", "?")
                r.add(6, "Stock price rose " + str(pct) + "pct in 52 weeks with weak fundamentals (pump pattern)")
    except Exception:
        pass

    f = fundamentals.red_flags(ticker, as_of)
    if f["years_available"] == 0 and r.points == 0:
        return r  # no data at all
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
    t_aliases = [ticker.upper()]
    if ticker.upper() in ["CLOUD", "VARANIUM"]:
        t_aliases.extend(["CLOUD", "VARANIUM"])
    elif ticker.upper() in ["ASRL", "ADDSHOP"]:
        t_aliases.extend(["ASRL", "ADDSHOP"])
    elif ticker.upper() in ["AFCOM", "FAMILYPUMP"]:
        t_aliases.extend(["AFCOM", "FAMILYPUMP"])
    row = uni[uni.ticker.isin(t_aliases) | uni.market_id.isin(t_aliases)]
    if row.empty:
        try:
            from pathlib import Path
            nse_p = Path(__file__).resolve().parents[2] / "config" / "nse_universe.csv"
            if nse_p.exists():
                nse_df = pd.read_csv(nse_p)
                match_nse = nse_df[nse_df.ticker.isin(t_aliases)]
                if not match_nse.empty:
                    row = match_nse
        except Exception:
            pass
    if row.empty:
        return r
    row = row.iloc[0]

    if str(row.get("segment", "")).upper() == "SME":
        r.add(5, "Listed on the SME platform (thin liquidity, wider manipulation risk)")

    if pd.notna(row.get("free_float_pct")) and str(row.get("free_float_pct")).strip() != "":
        try:
            ff = float(row.free_float_pct)
            if ff < 25:
                r.add(5, f"Very thin free float ({ff:.0f}%) — tightly held insider supply")
            elif ff < 30:
                r.add(3, f"Low free float ({ff:.0f}%)")
        except (ValueError, TypeError):
            pass

    if pd.notna(row.get("issue_size_cr")) and str(row.get("issue_size_cr")).strip() != "":
        try:
            iss = float(row.issue_size_cr)
            if iss < 50:
                r.add(3, f"Small issue size (Rs. {iss:.0f} cr) — easily cornered float")
        except (ValueError, TypeError):
            pass

    # Surveillance flag or Series BE / BZ (Trade-for-Trade / Surveillance)
    surv = (
        str(row.get("surveillance_flag", "")).lower() == "true"
        or str(row.get("segment", "")).lower() == "surveillance"
    )
    if surv:
        r.add(5, "Placed under exchange surveillance (GSM/ASM / Trade-for-Trade series BE/BZ)")

    return r
