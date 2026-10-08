"""Explainable tip repetition / coordination signals."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.campaign.store import TipStore


def analyze_tip_coordination(store: TipStore, ticker: str, clean_text: str, source_label: str) -> dict[str, Any]:
    fp = __import__("src.tipcheck.privacy", fromlist=["fingerprint"]).fingerprint(clean_text)
    recent = store.recent(ticker, limit=200)
    same_fp = sum(1 for item in recent if item["fingerprint"] == fp)
    sources = {item["source_label"] for item in recent if item["source_label"]}

    observations: list[dict[str, Any]] = []
    if same_fp >= 3:
        observations.append({
            "signal": "repeated_tip_fingerprint",
            "severity": "high",
            "text": f"The same normalized tip fingerprint has appeared {same_fp} times for {ticker} in stored Dakota tip events.",
        })
    elif same_fp >= 2:
        observations.append({
            "signal": "repeated_tip_fingerprint",
            "severity": "medium",
            "text": f"The same normalized tip fingerprint has appeared {same_fp} times for {ticker}.",
        })

    if len(sources) >= 3:
        observations.append({
            "signal": "cross_source_tip_repeat",
            "severity": "medium",
            "text": f"Matching normalized tip activity is present across {len(sources)} coarse source labels; this is a coordination signal, not proof of coordinated activity.",
        })

    return {
        "status": "connected",
        "ticker": ticker.upper().strip(),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "same_fingerprint_count": same_fp,
        "source_count": len(sources),
        "observations": observations,
        "recent_events": recent[:25],
    }
