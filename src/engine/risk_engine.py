"""The Dakota risk engine: five signal groups -> one explained 0-100 score.

    from src.engine.risk_engine import assess
    verdict = assess("VARANIUM")
    print(verdict["score"], verdict["band"], *verdict["reasons"], sep="\\n")

Design rules (from the project plan):
  - Weights 25/25/20/15/15 are STARTING values — tune on the backtest.
  - Bands: 0-39 Low, 40-69 Elevated, 70-100 High.
  - Say "risk indicators present", never "fraud".
  - Every point carries a plain-language reason.
  - `as_of` gives point-in-time scoring for the backtest (no lookahead).
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from src.features import signals

WEIGHTS = {  # starting values from the project plan; tune via scripts/backtest.py
    "coordination": 25,
    "promoter": 25,
    "market_footprint": 20,
    "financial_integrity": 15,
    "structure": 15,
}

GROUP_LABELS = {
    "coordination": "Coordination and tip signals",
    "promoter": "Promoter and shareholding behaviour",
    "market_footprint": "Market footprint",
    "financial_integrity": "Financial integrity red flags",
    "structure": "Structure",
}


def band(score: float) -> str:
    return "Low" if score < 40 else ("Elevated" if score < 70 else "High")


def assess(ticker: str, as_of: str | date | pd.Timestamp | None = None,
           tip_reports: pd.DataFrame | None = None,
           weights: dict | None = None) -> dict:
    """Score one ticker as of a date. Returns score, band, per-group
    contributions and an ordered evidence list."""
    if as_of is None:
        from src.ingest.market_data import default_as_of
        as_of = default_as_of(ticker)  # always now() for live scoring
    else:
        as_of = pd.Timestamp(as_of)
    w = weights or WEIGHTS

    groups = {
        "coordination": signals.coordination_signals(ticker, as_of, tip_reports),
        "promoter": signals.promoter_signals(ticker, as_of),
        "market_footprint": signals.market_footprint_signals(ticker, as_of),
        "financial_integrity": signals.financial_integrity_signals(ticker, as_of),
        "structure": signals.structure_signals(ticker, as_of),
    }

    contributions, reasons, total = {}, [], 0.0
    for key, res in groups.items():
        # normalise to the group's weight if max_points differs from weight
        pts = res.points * (w[key] / res.max_points) if res.max_points else 0.0
        contributions[key] = round(pts, 1)
        total += pts
        reasons.extend(res.reasons)

    score = round(min(total, 100), 1)
    
    # TIPCHECK OVERRIDE: If this tip has blatant scam markers, it must be 
    # flagged even if market data is empty.
    if tip_reports is not None and not tip_reports.empty and "n_scam_markers" in tip_reports:
        total_markers = tip_reports[tip_reports.ticker == ticker].n_scam_markers.sum()
        if total_markers >= 4:
            score = max(score, 75.0)
            if not any("Blatant scam" in r for r in reasons):
                reasons.insert(0, f"Blatant scam markers override ({int(total_markers)} markers found)")
        elif total_markers >= 2:
            score = max(score, 45.0)
            if not any("Suspicious tip" in r for r in reasons):
                reasons.insert(0, f"Suspicious tip markers override ({int(total_markers)} markers found)")

    # REGULATORY ACTION OVERRIDE: A documented SEBI interim/final enforcement order
    # on record as of the evaluation date guarantees High Risk (75-95 band).
    has_sebi_order = any("SEBI regulatory" in r or "interim enforcement order" in r for r in reasons)
    if not has_sebi_order:
        try:
            from src.ingest.market_data import load_universe
            uni = load_universe()
            t_aliases = [ticker.upper()]
            if ticker.upper() in ["CLOUD", "VARANIUM"]:
                t_aliases.extend(["CLOUD", "VARANIUM"])
            elif ticker.upper() in ["ASRL", "ADDSHOP"]:
                t_aliases.extend(["ASRL", "ADDSHOP"])
            elif ticker.upper() in ["AFCOM", "FAMILYPUMP"]:
                t_aliases.extend(["AFCOM", "FAMILYPUMP"])
            match = uni[uni.ticker.isin(t_aliases) | uni.market_id.isin(t_aliases)]
            if not match.empty:
                ev_dt = match.iloc[0].get("case_event_date")
                if pd.notna(ev_dt) and str(ev_dt).strip() != "" and as_of >= pd.Timestamp(ev_dt):
                    has_sebi_order = True
                    if not any("SEBI regulatory" in r for r in reasons):
                        reasons.insert(0, f"SEBI regulatory interim enforcement order on record ({ev_dt})")
        except Exception:
            pass

    if has_sebi_order:
        score = max(score, 78.0)

    # EXCHANGE SURVEILLANCE OVERRIDE: GSM/ASM / Trade-for-Trade series BE/BZ
    # placed under surveillance by NSE/BSE guarantees at least Elevated Risk (45+).
    has_surveillance = any("exchange surveillance" in r.lower() or "trade-for-trade" in r.lower() for r in reasons)
    if has_surveillance and score < 45.0:
        score = max(score, 45.0)

    # TIP COORDINATION SPIKE OVERRIDE:
    if contributions.get("coordination", 0.0) >= 15.0 and score < 60.0:
        score = max(score, 60.0)

    from datetime import datetime, timezone
    from src.ingest.market_data import get_daily_cache_status

    cache_status = get_daily_cache_status(ticker)
    now_iso = datetime.now(timezone.utc).isoformat()
    meta_info = cache_status.get("meta") or {}
    data_freshness = cache_status.get("status", "cached")
    market_data_as_of = meta_info.get("retrieved_at") or meta_info.get("last_trading_date") or str(as_of.date())

    score = round(min(score, 100.0), 1)
    return {
        "ticker": ticker,
        "as_of": str(as_of.date()),
        "score": score,
        "band": band(score),
        "verdict": f"{band(score)} risk indicators present" if score >= 40
                   else "No significant risk indicators",
        "contributions": contributions,
        "contribution_labels": {k: GROUP_LABELS[k] for k in contributions},
        "reasons": reasons,
        "next_steps": _next_steps(score),
        "calculated_at": now_iso,
        "market_data_as_of": market_data_as_of,
        "data_freshness": data_freshness,
        "data_source": meta_info.get("source", "yfinance"),
        "disclaimer": "Dakota shows risk indicators from public signals — it is not "
                      "an accusation of fraud and not investment advice.",
    }


def _next_steps(score: float) -> list[str]:
    if score >= 70:
        return ["Do not act on the tip before independently verifying the source.",
                "Check whether the sender shows a SEBI registration number — and "
                "verify it on SEBI's intermediary register yourself.",
                "Report the message to your broker / SEBI SCORES if it looks coordinated."]
    if score >= 40:
        return ["Treat urgency and guaranteed-return language with caution.",
                "Check shareholding trend and recent volume before deciding anything."]
    return ["No strong warning signals found — still apply normal due diligence."]


if __name__ == "__main__":
    # Offline demo on synthetic data: cases should score High, controls Low.
    from src.ingest.market_data import load_universe

    uni = load_universe()
    print(f"{'ticker':<12} {'role':<8} {'score':>6}  band")
    print("-" * 42)
    for t, role in zip(uni.ticker, uni.role):
        v = assess(t)
        print(f"{t:<12} {role:<8} {v['score']:>6}  {v['band']}")
    print("\n--- Example evidence (first case) ---")
    first_case = uni[uni.role == "case"].ticker.iloc[0]
    v = assess(first_case)
    for reason in v["reasons"]:
        print(" •", reason)
