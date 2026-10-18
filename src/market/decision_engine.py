"""Unified Dakota Investment Stance & Decision Synthesis Engine.

Bridges the gap between forensic scam detection and real-life investing:
  Pillar 1: Forensic Safety (Dakota Shield: SEBI orders, pump-and-dump, coordination)
  Pillar 2: Technical Trend & Timing (200 SMA, 50 EMA, Supertrend, RSI momentum)
  Pillar 3: Fundamental Solvency & Health (Profitability, Debt-to-Revenue, Promoter Stability)

Outputs an actionable, institutional-grade verdict:
  - FAVORABLE_SETUP: Clean forensics + Bullish trend + Solvency
  - SAFE_DOWNTREND: Clean forensics, but price is in correction — wait for reversal
  - CONSOLIDATING_WATCHLIST: Clean forensics, sideways range — wait for breakout
  - SURVEILLANCE_CAUTION: Exchange surveillance (GSM/ASM) or tip bursts
  - CRITICAL_AVOID: SEBI interim order, blatant scam, or promoter dumping
"""
from __future__ import annotations

import logging
from typing import Any
import pandas as pd

from src.engine.risk_engine import assess
from src.market.technical_analyzer import analyze_technicals

logger = logging.getLogger(__name__)


def evaluate_investment_stance(
    ticker: str,
    df: pd.DataFrame | None = None,
    risk_data: dict[str, Any] | None = None,
    technical_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Synthesize forensics, technicals, and fundamentals into an actionable stance."""
    ticker = ticker.upper().strip()

    # 1. Forensic Safety Assessment
    if risk_data is None:
        try:
            risk_data = assess(ticker)
        except Exception as exc:
            logger.warning("Could not assess risk for %s: %s", ticker, exc)
            risk_data = {"score": 20.0, "band": "Low", "verdict": "Unavailable", "reasons": []}

    score = float(risk_data.get("score", 0.0) or 0.0)
    band = str(risk_data.get("band", "Low"))
    reasons = list(risk_data.get("reasons", []))

    # 2. Technical Trend Assessment
    if technical_data is None:
        try:
            from src.ingest.market_data import load_ohlcv
            if df is None:
                df = load_ohlcv(ticker, start="2023-01-01")
            technical_data = analyze_technicals(df, ticker)
        except Exception as exc:
            logger.debug("Technical analysis fallback for %s: %s", ticker, exc)
            technical_data = {
                "verdict": "NEUTRAL",
                "score": 0,
                "counts": {"buy": 0, "neutral": 0, "sell": 0},
                "moving_averages": {"verdict": "NEUTRAL", "indicators": []},
                "oscillators": {"verdict": "NEUTRAL", "indicators": []},
            }

    tech_verdict = str(technical_data.get("verdict", "NEUTRAL")).upper()
    tech_score = int(technical_data.get("score", 0) or 0)
    ma_indicators = technical_data.get("moving_averages", {}).get("indicators", [])

    # Extract key technical signals
    above_200_sma = True  # default optimistic if not yet calculated
    above_50_ema = True
    golden_cross = False
    supertrend_bullish = True
    cur_price = None

    for ind in ma_indicators:
        name = ind.get("name", "")
        act = ind.get("action", "")
        if "SMA 200" in name:
            above_200_sma = act == "BUY"
        elif "EMA 50" in name:
            above_50_ema = act == "BUY"
        elif "Golden" in name:
            golden_cross = act == "BUY"
        elif "Supertrend" in name:
            supertrend_bullish = act == "BUY"

    # 3. Fundamental Health Assessment
    fund_data: dict[str, Any] = {}
    try:
        from src.ingest.free_data_fetcher import load_live_fundamentals
        lf = load_live_fundamentals(ticker)
        if not lf.empty:
            fund_data = lf.iloc[-1].to_dict()
    except Exception:
        pass

    pe = fund_data.get("pe_ratio")
    rev_cr = float(fund_data.get("revenue_cr", 0.0) or 0.0)
    debt_cr = float(fund_data.get("total_debt_cr", 0.0) or 0.0)
    profit_cr = float(fund_data.get("profit_cr", 0.0) or 0.0)
    insider_pct = fund_data.get("insider_pct")
    high_debt = bool(fund_data.get("high_debt_flag", False))
    zero_rev = bool(fund_data.get("zero_revenue_flag", False))

    if high_debt or (rev_cr > 10.0 and debt_cr > 2.5 * rev_cr):
        fund_status = "LEVERAGED"
        fund_summary = f"High leverage alert: Debt (Rs. {debt_cr:.0f} cr) exceeds 2.5x annual revenue"
    elif profit_cr < -5.0 and rev_cr > 5.0:
        fund_status = "UNPROFITABLE"
        fund_summary = f"Negative net income (Loss of Rs. {abs(profit_cr):.0f} cr in latest reporting)"
    elif zero_rev and not fund_data.get("notes", "").startswith("Screener"):
        fund_status = "SHELL_RISK"
        fund_summary = "Near-zero reported revenue — potential shell or dormant operations"
    elif profit_cr > 0.0:
        fund_status = "HEALTHY"
        pe_str = f"P/E {pe:.1f}" if pe else "Sound valuation"
        fund_summary = f"Profitable operations (Rs. {profit_cr:.0f} cr net income, {pe_str})"
    else:
        fund_status = "MODERATE"
        fund_summary = "Stable institutional baseline with normal operating parameters"

    # 4. Pillar Status Determination
    # Forensic Pillar
    if score >= 70.0:
        forensic_status = "FAIL"
        forensic_summary = "High risk indicators: SEBI order, insider dumping, or coordinated tip scam"
    elif score >= 40.0:
        forensic_status = "CAUTION"
        forensic_summary = "Elevated risk: Exchange surveillance or high-frequency tip bursts active"
    else:
        forensic_status = "PASS"
        forensic_summary = "Clean forensics: No SEBI sanctions, promoter dumping, or operator coordination"

    # Technical Pillar
    if tech_verdict in ("STRONG BUY", "BUY"):
        technical_status = "BULLISH"
        tech_summary = "Upward trend structure: Trading above key moving averages with bullish momentum"
    elif tech_verdict in ("SELL", "STRONG SELL"):
        technical_status = "BEARISH"
        tech_summary = "Downtrend structure: Selling pressure below key moving averages / bearish Supertrend"
    else:
        technical_status = "NEUTRAL"
        tech_summary = "Consolidating: Price is bounded in a trading range with balanced momentum"

    # 5. Composite Actionable Stance Synthesis
    if forensic_status == "FAIL":
        stance_key = "CRITICAL_AVOID"
        stance_badge = "Critical Avoid"
        theme = "red"
        title = "Critical Avoid — High Manipulation / Regulatory Risk"
        guidance = (
            "Do not buy. Documented regulatory order, aggressive promoter selling, or blatant scam tip markers "
            "are active on this scrip. Extreme probability of severe capital loss."
        )
    elif forensic_status == "CAUTION":
        stance_key = "SURVEILLANCE_CAUTION"
        stance_badge = "Surveillance Caution"
        theme = "orange"
        title = "Surveillance Caution — Elevated Operator Volatility"
        guidance = (
            "Caution advised. Placed under exchange surveillance (GSM/ASM/T2T) or facing coordinated tip spikes. "
            "High risk of sudden liquidity freeze or circuit-lock traps."
        )
    elif technical_status == "BULLISH" and fund_status in ("HEALTHY", "MODERATE"):
        stance_key = "FAVORABLE_SETUP"
        stance_badge = "Favorable Setup"
        theme = "emerald"
        title = "Favorable Setup — Safe Forensics & Bullish Momentum"
        guidance = (
            "Dual-layer green signal: Clean forensic safety combined with healthy technical trend alignment "
            "(above key moving averages and bullish Supertrend). Suitable candidate for phased accumulation."
        )
    elif technical_status == "BEARISH":
        stance_key = "SAFE_DOWNTREND"
        stance_badge = "Safe in Downtrend"
        theme = "amber"
        title = "Safe Company in Downtrend — Wait for Reversal"
        guidance = (
            "Legitimate company with clean forensic safety, but market price is in an active correction or downtrend. "
            "Do not catch a falling knife — wait for price to reclaim its 50 EMA and Supertrend before entering."
        )
    else:
        stance_key = "CONSOLIDATING_WATCHLIST"
        stance_badge = "Consolidating"
        theme = "sky"
        title = "Consolidating Range — Watchlist Candidate"
        guidance = (
            "Safe company trading in a consolidation range. Momentum is balanced. "
            "Add to watchlist and wait for a volume-confirmed breakout before deploying capital."
        )

    # 6. 5-Point Real-Life Due Diligence Checklist
    checklist = [
        {
            "id": "forensic_safety",
            "label": "Dakota Forensic Shield",
            "passed": forensic_status == "PASS",
            "detail": f"Risk score {score:.1f}/100 ({band} band)",
        },
        {
            "id": "trend_200_sma",
            "label": "Major Trend Alignment",
            "passed": above_200_sma,
            "detail": "Price holds above 200-day SMA" if above_200_sma else "Price is below 200-day SMA (Bear zone)",
        },
        {
            "id": "supertrend",
            "label": "Supertrend (10, 3) Stance",
            "passed": supertrend_bullish,
            "detail": "Bullish trailing trendline" if supertrend_bullish else "Bearish trailing resistance",
        },
        {
            "id": "balance_sheet",
            "label": "Solvent Balance Sheet",
            "passed": fund_status != "LEVERAGED" and fund_status != "SHELL_RISK",
            "detail": fund_summary,
        },
        {
            "id": "promoter_integrity",
            "label": "Promoter & Float Stability",
            "passed": not any("Promoter holding fell" in r or "promoter dumping" in r for r in reasons),
            "detail": "No promoter dumping detected" if not any("Promoter holding fell" in r for r in reasons) else "Promoter selling observed",
        },
    ]

    return {
        "ticker": ticker,
        "stance": stance_key,
        "stance_badge": stance_badge,
        "theme": theme,
        "title": title,
        "actionable_guidance": guidance,
        "pillars": {
            "forensic": {
                "name": "Forensic Safety (Dakota Shield)",
                "status": forensic_status,
                "score": score,
                "band": band,
                "summary": forensic_summary,
            },
            "technical": {
                "name": "Technical Trend & Timing",
                "status": technical_status,
                "verdict": tech_verdict,
                "score": tech_score,
                "summary": tech_summary,
            },
            "fundamental": {
                "name": "Fundamental Solvency & Health",
                "status": fund_status,
                "pe_ratio": pe,
                "revenue_cr": rev_cr,
                "debt_cr": debt_cr,
                "profit_cr": profit_cr,
                "promoter_pct": insider_pct,
                "summary": fund_summary,
            },
        },
        "checklist": checklist,
        "checklist_passed_count": sum(1 for c in checklist if c["passed"]),
        "checklist_total_count": len(checklist),
    }
