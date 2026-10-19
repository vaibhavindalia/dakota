"""Task B: Financial Sentiment and Social Tip Divergence Classification.

Evaluates market telemetry, corporate news, and social chatter to detect grounded sentiment
and flag dangerous divergences where promotional touting conflicts with deteriorating fundamentals.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .base import BaseFinancialTask


class SentimentDivergenceTask(BaseFinancialTask):
    """Classifies sentiment across Indian equities using evidence-grounded multi-vector analysis."""

    def __init__(self, task_version: str = "v1.0"):
        super().__init__(task_name="sentiment_divergence", task_version=task_version)

    @property
    def candidate_classes(self) -> Dict[str, str]:
        return {
            "Bullish": "Evidence demonstrates positive operational trajectory, institutional accumulation, or sustained technical breakout.",
            "Bearish": "Evidence demonstrates deteriorating financial fundamentals, exchange surveillance placement, regulatory scrutiny, or breakdown.",
            "Neutral": "Evidence demonstrates balanced, range-bound trading activity, ordinary corporate updates, or normal market operations.",
            "Mixed": "Prominent conflict between sources (e.g. intense promotional social media touting occurring alongside declining delivery volume or negative earnings).",
            "Ambiguous": "Available context contains contradictory indicators of comparable strength or undecidable statements where neither bullish nor bearish can be established.",
            "Insufficient Evidence": "Available context lacks adequate information or verified market/news disclosures to form a grounded assessment.",
        }

    @property
    def task_instructions(self) -> str:
        return (
            "Analyze the verified stock telemetry, recent news, and social signals provided in the context.\n"
            "Determine the prevailing sentiment classification. Pay specific attention to contradictions: "
            "if high-frequency social media touting promises massive gains while exchange data shows delivery volume collapse "
            "or exchange surveillance (GSM/ASM), classify strictly as 'Mixed'. If available context contains conflicting or undecidable statements of equal weight, classify as 'Ambiguous'. "
            "If context has no verifiable disclosures or telemetry, classify as 'Insufficient Evidence'."
        )

    def build_evidence_state(self, sample: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        """Extract and structure factual fields from Dakota sample while strictly preventing future leakage."""
        ticker = str(sample.get("ticker", "UNKNOWN")).upper()
        as_of = str(sample.get("as_of", ""))
        
        # Build normalized, compact state object preserving all evidence without token bloat
        price_data = {
            k: v for k, v in {
                "latest_price": sample.get("latest_price"),
                "change_pct": sample.get("change_pct"),
                "volume": sample.get("volume"),
                "delivery_pct": sample.get("delivery_pct"),
            }.items() if v is not None
        }

        forensic_data = {
            k: v for k, v in {
                "risk_score": sample.get("risk_score"),
                "risk_band": sample.get("risk_band"),
                "active_surveillance": sample.get("is_surveillance", False),
            }.items() if v is not None
        }

        # Deduplicate headlines and signals while strictly preserving order
        raw_headlines = sample.get("news_headlines", [])
        clean_headlines = list(dict.fromkeys(h.strip() for h in raw_headlines if h and h.strip()))

        raw_signals = sample.get("social_signals", [])
        clean_signals = list(dict.fromkeys(s.strip() for s in raw_signals if s and s.strip()))

        state: Dict[str, Any] = {
            "ticker": ticker,
            "as_of_date": as_of,
        }
        if price_data:
            state["price_summary"] = price_data
        if sample.get("technicals"):
            state["technical_indicators"] = sample["technicals"]
        if forensic_data:
            state["forensic_signals"] = forensic_data
        if clean_headlines:
            state["recent_news_headlines"] = clean_headlines
        if clean_signals:
            state["social_signals"] = clean_signals

        evidence_ids = sample.get("evidence_ids", [])
        if not evidence_ids:
            # Generate default provenance tags if missing
            evidence_ids = [f"E_MKT_{ticker}"]
            if sample.get("news_headlines"):
                evidence_ids.append(f"E_NEWS_{ticker}")
            if sample.get("social_signals"):
                evidence_ids.append(f"E_SOC_{ticker}")

        return state, evidence_ids
