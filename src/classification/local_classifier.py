"""Hybrid local classifier for Dakota Telegram messages."""
from __future__ import annotations

import re
from typing import Any

MODEL_NAME = "Horizon-Labs/multilingual-zeroshot-base"

COMMODITY_PATTERNS = {
    "crude_oil": ("crude oil", "crudeoil", "brent crude", "brent", "wti", "oil trade", "oil price"),
    "gold": ("gold trade", "gold price", "gold"),
    "silver": ("silver trade", "silver price", "silver"),
    "natural_gas": ("natural gas", "naturalgas", "gas trade", "gas price"),
    "copper": ("copper trade", "copper price", "copper"),
}
MACRO_PATTERNS = {
    "rbi_rate": ("rbi", "repo rate", "reverse repo", "rate cut", "rate hike", "interest rate", "interest rates", "monetary policy"),
    "inflation": ("inflation", "cpi", "wpi"),
    "gdp": ("gdp", "economic growth"),
    "fiscal_policy": ("fiscal policy", "fiscal deficit", "union budget", "budget"),
}
INDEX_PATTERNS = {
    "nifty_50": ("nifty 50", "nifty50", "nifty"),
    "bank_nifty": ("bank nifty", "banknifty"),
    "fin_nifty": ("fin nifty", "finnifty"),
    "sensex": ("sensex", "bse sensex"),
}
SECTOR_PATTERNS = {
    "defence": ("defence stocks", "defense stocks", "defence", "defense"),
    "banking": ("banking sector", "banking stocks", "banking"),
    "finance": ("finance sector", "financial sector", "nbfc"),
    "it": ("it sector", "it stocks", "information technology sector", "tech sector"),
    "pharma": ("pharma sector", "pharma stocks", "pharmaceutical sector"),
    "energy": ("energy sector", "energy stocks"),
    "auto": ("auto sector", "automobile sector", "auto stocks"),
    "metals": ("metal sector", "metals sector", "metal stocks"),
    "real_estate": ("real estate sector", "real estate", "realty sector"),
    "chemicals": ("chemical sector", "chemicals sector", "chemical stocks"),
    "telecom": ("telecom sector", "telecom stocks"),
}
TRADING_ACTION_PATTERNS = (
    "buy", "sell", "target", "tgt", "tp", "entry", "stop loss", "sl",
    "breakout", "rally", "rocket", "multibagger", "trade", "call", "buy now",
)


def _match(text: str, aliases: tuple[str, ...]) -> str | None:
    for alias in sorted(aliases, key=len, reverse=True):
        if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", text):
            return alias
    return None


def _known_tickers(text: str) -> list[str]:
    found: list[str] = []
    try:
        import pandas as pd
        from src.ingest.market_data import load_universe
        uni = load_universe()
        for ticker in uni.ticker.astype(str).str.upper():
            if re.search(rf"(?<![A-Z0-9])\$?{re.escape(ticker)}(?![A-Z0-9])", text.upper()):
                found.append(ticker)
    except Exception:
        pass
    for ticker in re.findall(r"\$([A-Z][A-Z0-9]{1,11})\b", text.upper()):
        if ticker not in found:
            found.append(ticker)
    return found[:5]


def _base(message_type: str, domain: str, topic: str | None, tickers: list[str], confidence: float, trading_intent: bool, method: str) -> dict[str, Any]:
    return {
        "message_type": message_type,
        "type": message_type,
        "market_domain": domain,
        "domain": domain,
        "topic": topic,
        "tickers": tickers,
        "confidence": confidence,
        "trading_intent": trading_intent,
        "method": method,
        "status": "classified",
    }


def rule_classify(text: str) -> dict[str, Any] | None:
    clean = " ".join(text.lower().split())
    tickers = _known_tickers(text)
    trading_intent = any(term in clean for term in TRADING_ACTION_PATTERNS)

    if tickers:
        return _base("a specific stock trading tip", "equity", None, tickers, 0.98, trading_intent, "rules")

    for topic, aliases in COMMODITY_PATTERNS.items():
        if _match(clean, aliases):
            return _base("a commodity trading tip", "commodity", topic if topic != "crude_oil" else "commodity", [], 0.96, True, "rules")

    for topic, aliases in MACRO_PATTERNS.items():
        if _match(clean, aliases):
            return _base("a macroeconomic trading tip", "macro", "macro", [], 0.96, trading_intent, "rules")

    for topic, aliases in INDEX_PATTERNS.items():
        if _match(clean, aliases):
            return _base("an index trading tip", "index", "index", [], 0.96, trading_intent, "rules")

    for topic, aliases in SECTOR_PATTERNS.items():
        if _match(clean, aliases):
            return _base("a sector trading tip", "sector", "sector", [], 0.94, True, "rules")

    if not trading_intent and any(x in clean for x in ("birthday", "congratulations", "good morning", "good night", "hello", "thanks", "thank you")):
        return _base("a non-financial message", "none", None, [], 0.94, False, "rules")
    return None


def ml_classify(text: str) -> dict[str, Any]:
    labels = [
        "a specific stock trading tip",
        "a commodity trading tip",
        "a macroeconomic trading tip",
        "a sector trading tip",
        "an index trading tip",
        "a forex trading tip",
        "a non-financial message",
    ]
    try:
        from transformers import pipeline
        classifier = pipeline("zero-shot-classification", model=MODEL_NAME, device=-1)
        result = classifier(text, labels, multi_label=False, hypothesis_template="This message is {}.")
        top = result["labels"][0]
        score = float(result["scores"][0])
    except Exception:
        return _base("a non-financial message", "none", None, [], 0.0, False, "fallback")
    mapping = {
        "a specific stock trading tip": ("equity", None),
        "a commodity trading tip": ("commodity", "commodity"),
        "a macroeconomic trading tip": ("macro", "macro"),
        "a sector trading tip": ("sector", "sector"),
        "an index trading tip": ("index", "index"),
        "a forex trading tip": ("forex", "forex"),
        "a non-financial message": ("none", None),
    }
    domain, topic = mapping[top]
    tickers = _known_tickers(text)
    return _base(top, domain, topic, tickers, score, False, "local_ml")


def classify_message(text: str) -> dict[str, Any]:
    rules = rule_classify(text)
    return rules if rules else ml_classify(text)
