"""Curated Indian Equity Financial Benchmark Dataset for Task B (Sentiment & Tip Divergence).

Provides chronologically ordered, point-in-time validated samples spanning:
Bullish, Bearish, Neutral, Mixed, and Insufficient Evidence.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class FinancialBenchmarkSample(BaseModel):
    """Normalized benchmark sample with strict temporal and evidence annotations."""
    sample_id: str
    ticker: str
    timestamp: str  # ISO-8601 UTC string
    label: str  # Bullish | Bearish | Neutral | Mixed | Insufficient Evidence
    claim: str
    evidence_ids: List[str]
    sample: Dict[str, Any]
    rationale: str


def get_curated_indian_equity_dataset() -> List[FinancialBenchmarkSample]:
    """Returns a rigorously annotated, chronologically ordered benchmark dataset of Indian equity market events."""
    raw_data = [
        # --- Split 1: September 2026 Observations ---
        {
            "sample_id": "IN-20260915-001",
            "ticker": "RELIANCE",
            "timestamp": "2026-09-15T10:30:00Z",
            "label": "Bullish",
            "claim": "Reliance Retail EBITDA expands 28% YoY with 400 new store additions. Institutional buying surges.",
            "evidence_ids": ["E_MKT_RELIANCE", "E_FILING_BSE_REL"],
            "sample": {
                "ticker": "RELIANCE",
                "as_of": "2026-09-15T10:30:00Z",
                "latest_price": 3020.50,
                "change_pct": 2.85,
                "volume": 6520000,
                "delivery_pct": 68.4,
                "technicals": {"trend_vs_ema20": "bullish_expansion", "rsi_status": "bullish_65"},
                "risk_score": 5.0,
                "risk_band": "Low",
                "is_surveillance": False,
                "news_headlines": ["Reliance Retail posts record quarterly EBITDA of ₹6,200 Cr"],
                "social_signals": ["FII block deals reported in Reliance counters this morning"],
            },
            "rationale": "Strong operational beat corroborated by 68.4% delivery volume and breakout above EMA20."
        },
        {
            "sample_id": "IN-20260918-002",
            "ticker": "PAYTM",
            "timestamp": "2026-09-18T14:15:00Z",
            "label": "Bearish",
            "claim": "RBI issues fresh regulatory directive imposing lending restrictions on partner NBFCs.",
            "evidence_ids": ["E_MKT_PAYTM", "E_REG_RBI", "E_NEWS_PAYTM"],
            "sample": {
                "ticker": "PAYTM",
                "as_of": "2026-09-18T14:15:00Z",
                "latest_price": 412.30,
                "change_pct": -6.40,
                "volume": 9800000,
                "delivery_pct": 32.1,
                "technicals": {"trend_vs_ema20": "severe_breakdown", "rsi_status": "oversold_28"},
                "risk_score": 75.0,
                "risk_band": "High",
                "is_surveillance": True,
                "news_headlines": ["Regulator tightens consumer lending norms for fintech aggregators"],
                "social_signals": ["Retail panic selling observed across fintech counters"],
            },
            "rationale": "Material adverse regulatory scrutiny causing sharp price breakdown and surveillance tagging."
        },
        {
            "sample_id": "IN-20260922-003",
            "ticker": "INFY",
            "timestamp": "2026-09-22T16:00:00Z",
            "label": "Neutral",
            "claim": "Infosys submits routine intimation of Q2 earnings board meeting date to BSE and NSE.",
            "evidence_ids": ["E_FILING_BSE_INFY", "E_MKT_INFY"],
            "sample": {
                "ticker": "INFY",
                "as_of": "2026-09-22T16:00:00Z",
                "latest_price": 1940.00,
                "change_pct": 0.15,
                "volume": 2100000,
                "delivery_pct": 52.0,
                "technicals": {"trend_vs_ema20": "flat_consolidation", "rsi_status": "neutral_51"},
                "risk_score": 2.0,
                "risk_band": "Low",
                "is_surveillance": False,
                "news_headlines": ["Infosys Board to consider Q2 FY27 results on October 15, 2026"],
                "social_signals": ["Routine calendar announcement, no unexpected commentary"],
            },
            "rationale": "Standard regulatory calendar disclosure; price and technical indicators remain completely rangebound."
        },
        {
            "sample_id": "IN-20260925-004",
            "ticker": "SUZLON",
            "timestamp": "2026-09-25T11:45:00Z",
            "label": "Mixed",
            "claim": "Massive telegram touting: 'Suzlon hitting ₹150 next week guaranteed! Load up now!'",
            "evidence_ids": ["E_MKT_SUZLON", "E_SOC_TG_SUZ", "E_SURV_BSE"],
            "sample": {
                "ticker": "SUZLON",
                "as_of": "2026-09-25T11:45:00Z",
                "latest_price": 78.40,
                "change_pct": 1.20,
                "volume": 45000000,
                "delivery_pct": 19.5,
                "technicals": {"trend_vs_ema20": "choppy_divergence", "rsi_status": "overbought_74"},
                "risk_score": 68.0,
                "risk_band": "High",
                "is_surveillance": True,
                "news_headlines": ["BSE places scrip under Enhanced Surveillance Measure (ESM) Stage 1"],
                "social_signals": ["15 unverified Telegram channels broadcasting identical copy-paste buy targets"],
            },
            "rationale": "Aggressive promotional hype starkly contradicts low delivery (19.5%) and active exchange surveillance."
        },
        {
            "sample_id": "IN-20260928-005",
            "ticker": "SHREEPENNY",
            "timestamp": "2026-09-28T09:30:00Z",
            "label": "Insufficient Evidence",
            "claim": "Whisper of multi-bagger government defense contract for micro-cap engineering entity.",
            "evidence_ids": ["E_SOC_WHISPER"],
            "sample": {
                "ticker": "SHREEPENNY",
                "as_of": "2026-09-28T09:30:00Z",
                "latest_price": 14.20,
                "change_pct": 0.0,
                "volume": 500,
                "delivery_pct": None,
                "technicals": {"trend_vs_ema20": "illiquid", "rsi_status": "unavailable"},
                "risk_score": 85.0,
                "risk_band": "Critical",
                "is_surveillance": False,
                "news_headlines": [],
                "social_signals": ["Anonymous X post alleging private contract award without company filing"],
            },
            "rationale": "Zero exchange corroboration, negligible liquidity, and absence of regulatory disclosures."
        },

        # --- Split 2: Early October 2026 Observations ---
        {
            "sample_id": "IN-20261002-006",
            "ticker": "TATAMOTORS",
            "timestamp": "2026-10-02T13:00:00Z",
            "label": "Bullish",
            "claim": "JLR wholesale dispatches jump 18% in Q2, EV order backlog touches record high.",
            "evidence_ids": ["E_MKT_TATA", "E_FILING_NSE_TATA"],
            "sample": {
                "ticker": "TATAMOTORS",
                "as_of": "2026-10-02T13:00:00Z",
                "latest_price": 1045.80,
                "change_pct": 3.40,
                "volume": 8400000,
                "delivery_pct": 61.2,
                "technicals": {"trend_vs_ema20": "strong_uptrend", "rsi_status": "bullish_68"},
                "risk_score": 8.0,
                "risk_band": "Low",
                "is_surveillance": False,
                "news_headlines": ["Tata Motors UK arm JLR reports strongest quarterly cash flow in 5 years"],
                "social_signals": ["Positive analyst consensus updates from Morgan Stanley and CLSA"],
            },
            "rationale": "Tangible operational delivery acceleration supported by high delivery percentage and price action."
        },
        {
            "sample_id": "IN-20261005-007",
            "ticker": "ADANIENT",
            "timestamp": "2026-10-05T15:20:00Z",
            "label": "Neutral",
            "claim": "Adani Enterprises successfully commissions Phase 1 solar cell manufacturing line in Mundra.",
            "evidence_ids": ["E_FILING_BSE_ADANI", "E_MKT_ADANI"],
            "sample": {
                "ticker": "ADANIENT",
                "as_of": "2026-10-05T15:20:00Z",
                "latest_price": 3150.00,
                "change_pct": 0.45,
                "volume": 1850000,
                "delivery_pct": 48.7,
                "technicals": {"trend_vs_ema20": "rangebound", "rsi_status": "neutral_53"},
                "risk_score": 25.0,
                "risk_band": "Moderate",
                "is_surveillance": False,
                "news_headlines": ["Adani Solar commercializes 2GW wafer production unit in Gujarat"],
                "social_signals": ["Expected project milestone delivered on schedule; markets digest news calmly"],
            },
            "rationale": "In-line project milestone execution already factored in by markets; price remains steady."
        },
        {
            "sample_id": "IN-20261007-008",
            "ticker": "ZOMATO",
            "timestamp": "2026-10-07T12:00:00Z",
            "label": "Bullish",
            "claim": "Blinkit hits EBITDA breakeven ahead of guidance as quick-commerce GOV expands 110% YoY.",
            "evidence_ids": ["E_MKT_ZOMATO", "E_FILING_NSE_ZOM"],
            "sample": {
                "ticker": "ZOMATO",
                "as_of": "2026-10-07T12:00:00Z",
                "latest_price": 288.60,
                "change_pct": 4.10,
                "volume": 32000000,
                "delivery_pct": 59.8,
                "technicals": {"trend_vs_ema20": "breakout_volume", "rsi_status": "bullish_71"},
                "risk_score": 12.0,
                "risk_band": "Low",
                "is_surveillance": False,
                "news_headlines": ["Quick commerce dark store expansion reaches 900 locations nationwide"],
                "social_signals": ["Heavy institutional participation observed in cash delivery segment"],
            },
            "rationale": "High-conviction fundamental inflection point backed by heavy delivery volume and earnings milestone."
        },
        {
            "sample_id": "IN-20261008-009",
            "ticker": "CDSL",
            "timestamp": "2026-10-08T12:27:52Z",
            "label": "Mixed",
            "claim": "Telegram channel @markemahakelpredictions promises target ₹1,500 (+19%) with urgency markers.",
            "evidence_ids": ["E_MKT_CDSL", "E_SOC_TG_CDSL", "E_FILING_BSE_CDSL"],
            "sample": {
                "ticker": "CDSL",
                "as_of": "2026-10-08T12:27:52Z",
                "latest_price": 1263.40,
                "change_pct": 1.07,
                "volume": 896613,
                "delivery_pct": 41.2,
                "technicals": {"trend_vs_ema20": "flat", "rsi_status": "unavailable"},
                "risk_score": 10.0,
                "risk_band": "Low",
                "is_surveillance": False,
                "news_headlines": ["Routine Regulation 74(5) compliance certificate filed on BSE"],
                "social_signals": [
                    "Telegram tip claims target ₹1500 but exchange filing is purely administrative",
                    "Reddit mentions 25 discussions across 17 communities without coordination proof"
                ],
            },
            "rationale": "Direct Dakota live case: Promotional tip target diverges from routine depository business data."
        },
        {
            "sample_id": "IN-20261008-010",
            "ticker": "CRUDE_OIL",
            "timestamp": "2026-10-08T12:20:36Z",
            "label": "Mixed",
            "claim": "Global crude oil price spike due to Hormuz shipping concerns; tip urges immediate commodity buying.",
            "evidence_ids": ["E_MKT_COMMODITY", "E_SOC_REDDIT_CRUDE"],
            "sample": {
                "ticker": "CRUDE_OIL",
                "as_of": "2026-10-08T12:20:36Z",
                "latest_price": 104.50,
                "change_pct": 3.50,
                "volume": 120000,
                "delivery_pct": None,
                "technicals": {"trend_vs_ema20": "volatile_uptrend", "rsi_status": "overbought_76"},
                "risk_score": 10.0,
                "risk_band": "Low",
                "is_surveillance": False,
                "news_headlines": ["Hormuz shipping lanes reopen as energy convoys resume passage"],
                "social_signals": ["50 Reddit discussions across 39 subreddits debating conflicting geopolitical outcomes"],
            },
            "rationale": "Direct Dakota live case: Commodity price rally encounters conflicting news of tanker lane reopening."
        },

        # --- Split 3: Mid-October 2026 Observations ---
        {
            "sample_id": "IN-20261011-011",
            "ticker": "HDFCBANK",
            "timestamp": "2026-10-11T16:30:00Z",
            "label": "Bullish",
            "claim": "Credit-to-deposit ratio normalizes to 84%, NIMs stabilize at 3.65% with declining credit costs.",
            "evidence_ids": ["E_MKT_HDFC", "E_FILING_BSE_HDFC"],
            "sample": {
                "ticker": "HDFCBANK",
                "as_of": "2026-10-11T16:30:00Z",
                "latest_price": 1780.20,
                "change_pct": 2.15,
                "volume": 14200000,
                "delivery_pct": 66.5,
                "technicals": {"trend_vs_ema20": "accumulation_uptrend", "rsi_status": "bullish_62"},
                "risk_score": 3.0,
                "risk_band": "Low",
                "is_surveillance": False,
                "news_headlines": ["HDFC Bank deposit accretion outpaces loan growth in Q2 FY27"],
                "social_signals": ["DII and FII net buying concentrated in private banking index leaders"],
            },
            "rationale": "Key structural balance sheet overhang resolved; confirmed by heavy delivery accumulation."
        },
        {
            "sample_id": "IN-20261013-012",
            "ticker": "QUICKPUMP",
            "timestamp": "2026-10-13T10:00:00Z",
            "label": "Insufficient Evidence",
            "claim": "VIP WhatsApp group claims tiny biotech scrip received patent for Alzheimer drug.",
            "evidence_ids": ["E_SOC_WA_PUMP"],
            "sample": {
                "ticker": "QUICKPUMP",
                "as_of": "2026-10-13T10:00:00Z",
                "latest_price": 8.50,
                "change_pct": 4.90,
                "volume": 1200,
                "delivery_pct": None,
                "technicals": {"trend_vs_ema20": "circuit_frozen", "rsi_status": "unavailable"},
                "risk_score": 92.0,
                "risk_band": "Critical",
                "is_surveillance": True,
                "news_headlines": [],
                "social_signals": ["Unregistered advisory claims 1000% returns on unverified drug patent"],
            },
            "rationale": "Classic pump-and-dump signature: upper circuit on micro-volume with zero clinical or regulatory filing."
        },
        {
            "sample_id": "IN-20261015-013",
            "ticker": "TCS",
            "timestamp": "2026-10-15T18:00:00Z",
            "label": "Neutral",
            "claim": "TCS announces Q2 operating margin of 24.1%, in-line revenue growth of 1.2% in constant currency.",
            "evidence_ids": ["E_MKT_TCS", "E_FILING_BSE_TCS"],
            "sample": {
                "ticker": "TCS",
                "as_of": "2026-10-15T18:00:00Z",
                "latest_price": 4150.00,
                "change_pct": -0.30,
                "volume": 2400000,
                "delivery_pct": 55.4,
                "technicals": {"trend_vs_ema20": "steady_consolidation", "rsi_status": "neutral_49"},
                "risk_score": 1.0,
                "risk_band": "Low",
                "is_surveillance": False,
                "news_headlines": ["TCS Q2 order book reaches $8.6 Billion; interim dividend ₹10/share declared"],
                "social_signals": ["Results align exactly with broker consensus estimates, minimal surprise factor"],
            },
            "rationale": "Operational metrics strictly in line with market expectations; price variation is negligible."
        },
        {
            "sample_id": "IN-20261016-014",
            "ticker": "FRAUDVENT",
            "timestamp": "2026-10-16T11:20:00Z",
            "label": "Bearish",
            "claim": "Statutory auditors tender resignation citing inability to verify overseas cash balances.",
            "evidence_ids": ["E_FILING_AUDITOR_RESIGN", "E_MKT_FRAUD"],
            "sample": {
                "ticker": "FRAUDVENT",
                "as_of": "2026-10-16T11:20:00Z",
                "latest_price": 82.00,
                "change_pct": -19.90,
                "volume": 12500000,
                "delivery_pct": 74.0,
                "technicals": {"trend_vs_ema20": "circuit_down", "rsi_status": "oversold_18"},
                "risk_score": 98.0,
                "risk_band": "Critical",
                "is_surveillance": True,
                "news_headlines": ["Auditor walks out after management fails to provide bank confirmations"],
                "social_signals": ["Whistleblower complaints submitted to SEBI and MCA regarding circular billing"],
            },
            "rationale": "Severe corporate governance breakdown leading to lower circuit freeze and auditor disavowal."
        },
        {
            "sample_id": "IN-20261018-015",
            "ticker": "MEDIASPIN",
            "timestamp": "2026-10-18T14:40:00Z",
            "label": "Mixed",
            "claim": "Social influencers tout mega OTT merger while exchange data shows promoter share pledge rises to 82%.",
            "evidence_ids": ["E_MKT_MEDIASPIN", "E_SOC_INSTA", "E_PLEDGE_BSE"],
            "sample": {
                "ticker": "MEDIASPIN",
                "as_of": "2026-10-18T14:40:00Z",
                "latest_price": 142.50,
                "change_pct": 2.10,
                "volume": 18200000,
                "delivery_pct": 21.0,
                "technicals": {"trend_vs_ema20": "distribution_divergence", "rsi_status": "bearish_divergence"},
                "risk_score": 82.0,
                "risk_band": "Critical",
                "is_surveillance": True,
                "news_headlines": ["Promoters pledge an additional 12% stake to secure debt restructuring"],
                "social_signals": ["Instagram reels aggressively promoting scrip with luxury lifestyle imagery"],
            },
            "rationale": "High-urgency retail marketing directly conflicts with severe balance-sheet promoter pledge distress."
        },
    ]

    return [FinancialBenchmarkSample(**item) for item in raw_data]
