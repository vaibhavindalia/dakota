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

SPAM_PROMO_PATTERNS = (
    "join vip", "vip channel", "vip group", "free channel", "premium channel", "premium group",
    "telegram channel", "join telegram", "whatsapp", "call +", "contact admin", "dm for",
    "paid calls", "jackpot calls", "sure shot", "sure shots", "100% assured", "guaranteed profit",
    "assured returns", "profit screenshot", "proof", "booking open", "daily profit",
    "earn daily", "crypto signals", "forex signals", "subscription", "register now", "paid service",
    "click here", "t.me/", "link in bio", "admin contact", "account handling", "recover loss",
)

CHIT_CHAT_PATTERNS = (
    "good morning", "good evening", "good night", "gm all", "gm guys", "gn all", "hello",
    "hi guys", "hi all", "happy diwali", "happy new year", "thanks", "thank you", "congrats",
    "congratulations", "welcome", "happy trading", "have a nice day", "trading holiday",
    "market closed today", "happy weekend", "birthday",
)

MARKET_STATUS_PATTERNS = (
    "market opens", "market closed", "pre-market", "post-market", "market opening",
    "heavy volatility", "expiry day today", "market update", "trading session ended",
    "stay cautious", "closing bell", "opening bell",
)


def _match(text: str, aliases: tuple[str, ...]) -> str | None:
    for alias in sorted(aliases, key=len, reverse=True):
        if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", text):
            return alias
    return None


def _known_tickers(text: str) -> list[str]:
    found: list[str] = []
    upper = text.upper()
    try:
        from src.tipcheck.parser import get_extended_name_to_ticker
        ext_map = get_extended_name_to_ticker()
        for name_key in sorted(ext_map.keys(), key=len, reverse=True):
            ticker_val = ext_map[name_key]
            if re.search(rf"\b{re.escape(name_key)}\b", upper):
                if ticker_val not in found:
                    found.append(ticker_val)
    except Exception:
        pass
    for ticker in re.findall(r"\$([A-Z][A-Z0-9]{1,11})\b", upper):
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

    # 1. Important: Stock Tip (identified company or ticker)
    if tickers:
        return _base("a specific stock trading tip", "equity", None, tickers, 0.98, trading_intent, "rules")

    # 2. Tracked commodities
    for topic, aliases in COMMODITY_PATTERNS.items():
        if _match(clean, aliases):
            return _base("a commodity trading tip", "commodity", topic if topic != "crude_oil" else "commodity", [], 0.96, True, "rules")

    # 3. Macroeconomic
    for topic, aliases in MACRO_PATTERNS.items():
        if _match(clean, aliases):
            return _base("a macroeconomic trading tip", "macro", "macro", [], 0.96, trading_intent, "rules")

    # 4. Indices
    for topic, aliases in INDEX_PATTERNS.items():
        if _match(clean, aliases):
            return _base("an index trading tip", "index", "index", [], 0.96, trading_intent, "rules")

    # 5. Sectors
    for topic, aliases in SECTOR_PATTERNS.items():
        if _match(clean, aliases):
            return _base("a sector trading tip", "sector", "sector", [], 0.94, True, "rules")

    # 6. Shit / Noise Messages: Promotional spam / VIP funnel without a stock
    if any(p in clean for p in SPAM_PROMO_PATTERNS):
        return _base("a non-financial message", "none", None, [], 0.98, False, "rules_spam_filter")

    # 7. Shit / Noise Messages: Chit-chat / Greetings
    if any(p in clean for p in CHIT_CHAT_PATTERNS):
        return _base("a non-financial message", "none", None, [], 0.98, False, "rules_chit_chat")

    # 8. Noise Messages: General market status without actionable target
    if any(p in clean for p in MARKET_STATUS_PATTERNS):
        return _base("a non-financial message", "none", None, [], 0.90, False, "rules_general_status")

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

    # Prevent phantom sector or stock investigations for noisy/unactionable messages
    if top in ("a specific stock trading tip", "a sector trading tip") and not tickers:
        clean = " ".join(text.lower().split())
        matched_sector = None
        for sec_topic, aliases in SECTOR_PATTERNS.items():
            if _match(clean, aliases):
                matched_sector = sec_topic
                break
        if matched_sector:
            return _base("a sector trading tip", "sector", matched_sector, [], score, True, "local_ml")
        return _base("a non-financial message", "none", None, [], min(score, 0.40), False, "ml_unactionable_fallback")

    return _base(top, domain, topic, tickers, score, False, "local_ml")


def classify_message(text: str) -> dict[str, Any]:
    # Feature flag: enable JEV classification when DAKOTA_USE_JEV is active
    import os
    if os.environ.get("DAKOTA_USE_JEV", "0").strip().lower() in ("1", "true", "yes", "on"):
        try:
            from src.classification.jev_classifier import classify_message_jev
            res = classify_message_jev(text)
            res.setdefault("fallback_used", False)
            return res
        except Exception as exc:
            import logging
            logging.getLogger("dakota.classifier").warning(
                "JEV classification failed (%s); falling back to local rule/ML classifier.", exc
            )
            rules = rule_classify(text)
            fallback_res = dict(rules if rules else ml_classify(text))
            fallback_res["fallback_used"] = True
            fallback_res["fallback_reason"] = str(exc)
            fallback_res["original_classifier"] = "jev_qwen3.5_4bit"
            fallback_res.setdefault("evidence_ids", [f"E_MSG_{hash(text) & 0xFFFFFFFF:08x}"])
            return fallback_res

    rules = rule_classify(text)
    return rules if rules else ml_classify(text)

