"""
Dakota impact mapper.

Converts the universal classifier output into a concrete investigation target.

The classifier currently exposes fields such as:
    message_type
    market_domain
    topic
    tickers
    confidence
    trading_intent
    method

This mapper also accepts the shorter aliases:
    type
    domain
"""
from __future__ import annotations

import json
import re
from typing import Any


TOPIC_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "commodity": {
        "crude_oil": (
            "crude oil",
            "crudeoil",
            "brent crude",
            "brent",
            "wti",
            "oil trade",
            "oil price",
        ),
        "gold": ("gold trade", "gold price", "gold"),
        "silver": ("silver trade", "silver price", "silver"),
        "natural_gas": (
            "natural gas",
            "naturalgas",
            "gas trade",
            "gas price",
        ),
        "copper": ("copper trade", "copper price", "copper"),
    },
    "macro": {
        "rbi_rate": (
            "repo rate",
            "reverse repo",
            "rate cut",
            "rate hike",
            "interest rate",
            "interest rates",
            "monetary policy",
            "rbi",
        ),
        "inflation": ("inflation", "cpi", "wpi"),
        "gdp": ("gdp", "economic growth"),
        "fiscal_policy": (
            "fiscal policy",
            "fiscal deficit",
            "union budget",
            "budget",
        ),
        "government_policy": (
            "government policy",
            "policy change",
            "policy reform",
        ),
    },
    "sector": {
        "defence": (
            "defence stocks",
            "defense stocks",
            "defence",
            "defense",
        ),
        "banking": (
            "banking sector",
            "banking stocks",
            "banking",
        ),
        "finance": (
            "finance sector",
            "financial sector",
            "nbfc",
        ),
        "it": (
            "it sector",
            "it stocks",
            "information technology sector",
            "tech sector",
        ),
        "pharma": (
            "pharma sector",
            "pharma stocks",
            "pharmaceutical sector",
        ),
        "energy": ("energy sector", "energy stocks"),
        "auto": (
            "auto sector",
            "automobile sector",
            "auto stocks",
        ),
        "metals": (
            "metal sector",
            "metals sector",
            "metal stocks",
        ),
        "real_estate": (
            "real estate sector",
            "real estate",
            "realty sector",
        ),
        "chemicals": (
            "chemical sector",
            "chemicals sector",
            "chemical stocks",
        ),
        "telecom": (
            "telecom sector",
            "telecom stocks",
        ),
    },
    "index": {
        "nifty_50": ("nifty 50", "nifty50", "nifty"),
        "bank_nifty": ("bank nifty", "banknifty"),
        "fin_nifty": ("fin nifty", "finnifty"),
        "sensex": ("sensex", "bse sensex"),
    },
    "forex": {
        "usd_inr": (
            "usd inr",
            "usd/inr",
            "usdinr",
            "dollar rupee",
        ),
        "eur_inr": (
            "eur inr",
            "eur/inr",
            "eurinr",
            "euro rupee",
        ),
        "gbp_inr": (
            "gbp inr",
            "gbp/inr",
            "gbpinr",
            "pound rupee",
        ),
    },
}


IMPACT_AREAS: dict[str, list[str]] = {
    "crude_oil": ["energy", "aviation", "oil_marketing", "chemicals", "paints"],
    "gold": ["jewellery", "commodities"],
    "silver": ["industrial_metals", "electronics", "commodities"],
    "natural_gas": ["gas", "fertilizers", "chemicals", "power"],
    "copper": ["metals", "industrial_manufacturing", "electrical_equipment"],
    "rbi_rate": ["banks", "nbfcs", "real_estate", "auto", "capital_intensive_businesses"],
    "inflation": ["consumer", "staples", "interest_sensitive_sectors"],
    "gdp": ["broad_equity_market", "banks", "industrials", "consumer"],
    "fiscal_policy": ["infrastructure", "capital_goods", "defence", "public_sector"],
    "government_policy": ["policy_sensitive_sectors"],
    "nifty_50": ["broad_large_cap_equities", "nifty_50_constituents"],
    "bank_nifty": ["banks", "financials"],
    "fin_nifty": ["financials", "banks", "nbfcs", "insurance"],
    "sensex": ["broad_large_cap_equities", "sensex_constituents"],
    "defence": ["defence"],
    "banking": ["banks", "financials"],
    "finance": ["nbfcs", "financials"],
    "it": ["information_technology"],
    "pharma": ["pharmaceuticals", "healthcare"],
    "energy": ["energy"],
    "auto": ["automobiles", "auto_components"],
    "metals": ["metals", "mining"],
    "real_estate": ["real_estate", "construction"],
    "chemicals": ["chemicals", "specialty_chemicals"],
    "telecom": ["telecom"],
    "usd_inr": ["it", "pharma", "importers", "exporters", "commodities"],
    "eur_inr": ["importers", "exporters", "commodities"],
    "gbp_inr": ["importers", "exporters", "commodities"],
}


STATUS_BY_DOMAIN = {
    "commodity": "investigate_commodity",
    "macro": "investigate_macro",
    "sector": "investigate_sector",
    "index": "investigate_index",
    "forex": "investigate_forex",
}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    value = str(value).strip()
    return [value] if value else []


def _get_first(
    mapping: dict[str, Any],
    *keys: str,
    default: Any = None,
) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", [], {}, ()):
            return value
    return default


def _find_topic(text: str, domain: str) -> tuple[str | None, str | None]:
    matches: list[tuple[int, str, str]] = []

    for topic, aliases in TOPIC_ALIASES.get(domain, {}).items():
        for alias in aliases:
            alias = _clean(alias)
            pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
            if re.search(pattern, text):
                matches.append((len(alias), topic, alias))

    if not matches:
        return None, None

    _, topic, alias = max(matches, key=lambda item: item[0])
    return topic, alias


def map_impact(
    message_text: str,
    classification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve a classified Telegram message into an investigation target."""

    classification = classification or {}
    text = _clean(message_text)

    raw_tickers = _get_first(
        classification,
        "tickers",
        default=[],
    )

    tickers = [
        ticker.upper().lstrip("$")
        for ticker in _as_list(raw_tickers)
    ]

    # IMPORTANT:
    # local_classifier.py uses "market_domain" and "message_type".
    # Accept aliases as well so the mapper is robust.
    domain = _clean(
        _get_first(
            classification,
            "market_domain",
            "domain",
            default="none",
        )
    ) or "none"

    confidence = float(
        _get_first(
            classification,
            "confidence",
            default=0.5,
        )
        or 0.5
    )

    classifier_topic = _clean(
        _get_first(
            classification,
            "topic",
            default=None,
        )
    ) or None

    message_type = _get_first(
        classification,
        "message_type",
        "type",
        default=None,
    )

    trading_intent = _get_first(
        classification,
        "trading_intent",
        default=False,
    )

    method = _get_first(
        classification,
        "method",
        default=None,
    )

    # 1. Explicit stock ticker.
    if tickers:
        return {
            "status": "investigate_stock",
            "domain": "equity",
            "entity_type": "stock",
            "entity": tickers[0],
            "exact_topic": None,
            "matched_text": tickers[0],
            "tickers": tickers,
            "potentially_affected_areas": ["single_stock"],
            "investigation_targets": tickers,
            "rationale": (
                "An explicit stock ticker was identified; "
                "investigate the ticker directly."
            ),
            "source_method": "explicit_ticker",
            "classifier_message_type": message_type,
            "classifier_method": method,
            "trading_intent": bool(trading_intent),
            "confidence": max(confidence, 0.98),
        }

    # 2. Non-financial message.
    if domain in {"none", "", "non-financial"}:
        return {
            "status": "classified_non_financial",
            "domain": "none",
            "entity_type": "none",
            "entity": None,
            "exact_topic": None,
            "matched_text": None,
            "tickers": [],
            "potentially_affected_areas": [],
            "investigation_targets": [],
            "rationale": (
                "The message is not market-relevant, so "
                "no market investigation is opened."
            ),
            "source_method": "classifier",
            "classifier_message_type": message_type,
            "classifier_method": method,
            "trading_intent": bool(trading_intent),
            "confidence": confidence,
        }

    # 3. Exact market topic.
    topic, alias = _find_topic(text, domain)

    # Never use a generic classifier label such as "commodity" as the final
    # entity when the message contains a more specific topic.
    if topic is None:
        if classifier_topic in IMPACT_AREAS:
            topic = classifier_topic
            alias = classifier_topic

    # 4. Relevant but unresolved.
    if topic is None:
        return {
            "status": "needs_entity_resolution",
            "domain": domain,
            "entity_type": domain,
            "entity": None,
            "exact_topic": None,
            "matched_text": None,
            "tickers": [],
            "potentially_affected_areas": [],
            "investigation_targets": [],
            "rationale": (
                f"A {domain} message was detected, but "
                "the exact entity/topic was not resolved."
            ),
            "source_method": "classifier_plus_rules",
            "classifier_message_type": message_type,
            "classifier_method": method,
            "trading_intent": bool(trading_intent),
            "confidence": min(confidence, 0.80),
        }

    return {
        "status": STATUS_BY_DOMAIN.get(
            domain,
            "needs_entity_resolution",
        ),
        "domain": domain,
        "entity_type": domain,
        "entity": topic,
        "exact_topic": topic,
        "matched_text": alias,
        "tickers": [],
        "potentially_affected_areas": IMPACT_AREAS.get(topic, []),
        "investigation_targets": [topic],
        "rationale": (
            f"Resolved the {domain} reference to {topic}; "
            "use it to drive the next evidence search."
        ),
        "source_method": "exact_topic_rule",
        "classifier_message_type": message_type,
        "classifier_method": method,
        "trading_intent": bool(trading_intent),
        "confidence": 0.98,
    }


def _run_tests() -> None:
    tests = [
        (
            "CDSL target 1500 tomorrow. Guaranteed breakout.",
            {
                "message_type": "a specific stock trading tip",
                "market_domain": "equity",
                "tickers": ["CDSL"],
                "confidence": 0.98,
                "trading_intent": True,
            },
            "CDSL",
        ),
        (
            "Don't miss crudeoil trade.",
            {
                "message_type": "a commodity trading tip",
                "market_domain": "commodity",
                "topic": "commodity",
                "confidence": 0.96,
                "trading_intent": True,
            },
            "crude_oil",
        ),
        (
            "RBI rate cut coming next week.",
            {
                "message_type": "a macroeconomic trading tip",
                "market_domain": "macro",
                "topic": "macro",
                "confidence": 0.96,
                "trading_intent": False,
            },
            "rbi_rate",
        ),
        (
            "Defence stocks are going to rally tomorrow.",
            {
                "message_type": "a sector trading tip",
                "market_domain": "sector",
                "topic": "sector",
                "confidence": 0.94,
                "trading_intent": True,
            },
            "defence",
        ),
        (
            "NIFTY 50 will cross 26000.",
            {
                "message_type": "an index trading tip",
                "market_domain": "index",
                "topic": "index",
                "confidence": 0.96,
                "trading_intent": False,
            },
            "nifty_50",
        ),
        (
            "Happy birthday bro!",
            {
                "message_type": "a non-financial message",
                "market_domain": "none",
                "confidence": 0.42,
                "trading_intent": False,
            },
            None,
        ),
    ]

    for message, classification, expected in tests:
        result = map_impact(message, classification)
        actual = result["entity"]
        assert actual == expected, (
            f"FAILED: {message!r}: "
            f"expected {expected!r}, got {actual!r}"
        )

        print(f"PASS | {message}")
        print(json.dumps(result, indent=2))
        print()


if __name__ == "__main__":
    _run_tests()
