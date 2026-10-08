"""
Dakota — Jev / TokenRa Classification Adapter
==============================================

Purpose:
    Classify EVERY incoming market-related message.

Jev is used for:
    - message class
    - market relevance
    - market domain
    - trading intent
    - urgency
    - promotion / hype
    - asset specificity
    - manipulation-style language

Jev does NOT produce Dakota's final manipulation-risk score.

Final risk scoring remains deterministic and evidence-based.

Architecture:

Telegram message
        ↓
privacy scrub
        ↓
Jev classifier
        ↓
structured classification
        ↓
Dakota investigation router
        ↓
market / news / social evidence
        ↓
risk engine
"""


from __future__ import annotations

import os
from typing import Any

import requests


# --------------------------------------------------------------------------
# TokenRa / Jev configuration
# --------------------------------------------------------------------------

TOKENRA_JEV_URL = (
    "https://tokenra.io/v1/decisions"
)

JEV_MODEL = os.environ.get(
    "JEV_MODEL",
    "jev-latest",
).strip()


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _answer(
    answers: dict[str, Any],
    key: str,
) -> dict[str, Any]:

    value = answers.get(key)

    if isinstance(value, dict):
        return value

    return {}


def _choice(
    answers: dict[str, Any],
    key: str,
) -> str | None:

    value = _answer(
        answers,
        key,
    ).get("choice")

    if value is None:
        return None

    return str(value)


def _confidence(
    answers: dict[str, Any],
    key: str,
) -> float | None:

    value = _answer(
        answers,
        key,
    ).get("confidence")

    try:
        return float(value)

    except (
        TypeError,
        ValueError,
    ):
        return None


def _probability(
    answers: dict[str, Any],
    key: str,
) -> float | None:

    value = _answer(
        answers,
        key,
    ).get("noul")

    try:
        return float(value)

    except (
        TypeError,
        ValueError,
    ):
        return None


def _score(
    answers: dict[str, Any],
    key: str,
) -> float | None:

    value = _answer(
        answers,
        key,
    ).get("score")

    try:
        return float(value)

    except (
        TypeError,
        ValueError,
    ):
        return None


# --------------------------------------------------------------------------
# Main classifier
# --------------------------------------------------------------------------

def classify(
    text: str,
    timeout: int = 30,
) -> dict[str, Any]:
    """
    Classify one message using Jev through TokenRa.

    The message is sent to TokenRa only for classification.
    Dakota does not persist the raw message in this adapter.
    """

    api_key = os.environ.get(
        "TOKENRA_API_KEY",
        "",
    ).strip()

    if not api_key:

        raise RuntimeError(
            "TOKENRA_API_KEY is not set."
        )

    text = (
        text or ""
    ).strip()

    if not text:

        raise ValueError(
            "Cannot classify empty text."
        )

    # ----------------------------------------------------------------------
    # Jev questions
    #
    # TokenRa's Jev endpoint accepts a `questions` object containing
    # typed questions: noul, choice and score.
    # ----------------------------------------------------------------------

    questions = {

        "message_class": {
            "type": "choice",
            "instructions": (
                "Classify the main type of this message."
            ),
            "criteria": {
                "stock_tip": (
                    "A message recommending, promoting, warning about, "
                    "or predicting a specific stock."
                ),
                "index_tip": (
                    "A message about an equity index such as NIFTY, "
                    "SENSEX or BANK NIFTY."
                ),
                "sector_tip": (
                    "A trading claim about a market sector."
                ),
                "commodity_tip": (
                    "A message about crude oil, gold, silver, "
                    "natural gas or another commodity."
                ),
                "macro_tip": (
                    "A message about RBI, interest rates, inflation, "
                    "GDP, government policy or another macro event."
                ),
                "forex_tip": (
                    "A message primarily about currencies or FX."
                ),
                "general_market_comment": (
                    "A market-related observation that is not a "
                    "direct trading recommendation."
                ),
                "unrelated": (
                    "Not meaningfully related to financial markets."
                ),
            },
        },

        "market_relevant": {
            "type": "noul",
            "instructions": (
                "Is this message materially relevant to financial "
                "markets, listed securities, commodities, indices, "
                "currencies, sectors or macroeconomic trading?"
            ),
            "criteria": {
                "true": (
                    "Clearly market-related or potentially actionable "
                    "for financial markets."
                ),
                "false": (
                    "Not meaningfully related to financial markets."
                ),
            },
        },

        "trading_intent": {
            "type": "score",
            "instructions": (
                "How strongly does this message attempt to influence "
                "a trading action?"
            ),
            "criteria": [
                "No trading intent",
                "Market discussion",
                "Trading suggestion",
                "Strong trading call",
                "Urgent or forceful call to act",
            ],
        },

        "urgency": {
            "type": "score",
            "instructions": (
                "How urgent or time-pressured is the message?"
            ),
            "criteria": [
                "No urgency",
                "Mild urgency",
                "Moderate urgency",
                "High urgency",
            ],
        },

        "promotion_style": {
            "type": "score",
            "instructions": (
                "How strongly does the message use promotional, "
                "hype-driven or potentially manipulative language?"
            ),
            "criteria": [
                "Neutral information",
                "Mild promotion",
                "Strong promotion",
                "Suspicious hype",
                "Highly manipulative promotional language",
            ],
        },

        "market_domain": {
            "type": "choice",
            "instructions": (
                "Identify the dominant market domain."
            ),
            "criteria": {
                "equity": (
                    "Specific listed shares or equity investing."
                ),
                "index": (
                    "Equity indices such as NIFTY, SENSEX "
                    "or BANK NIFTY."
                ),
                "commodity": (
                    "Crude oil, gold, silver, natural gas "
                    "or another commodity."
                ),
                "forex": (
                    "Currencies or foreign exchange."
                ),
                "macro": (
                    "RBI, interest rates, inflation, policy, "
                    "GDP or broad macro."
                ),
                "sector": (
                    "A sector-level market theme such as defence, "
                    "IT, pharma, banking or energy."
                ),
                "mixed": (
                    "Several market domains are involved."
                ),
                "none": (
                    "No meaningful market domain."
                ),
            },
        },

        "specific_asset": {
            "type": "noul",
            "instructions": (
                "Does the message clearly refer to one or more "
                "specific financial assets rather than only "
                "a broad market topic?"
            ),
            "criteria": {
                "true": (
                    "A specific stock, index, commodity, currency "
                    "or other identifiable asset is referenced."
                ),
                "false": (
                    "Only a broad topic or general market idea "
                    "is referenced."
                ),
            },
        },

        "claim_strength": {
            "type": "score",
            "instructions": (
                "How strongly does the message present its market "
                "claim as something the reader should believe "
                "or act on?"
            ),
            "criteria": [
                "Speculative or uncertain",
                "Moderately confident",
                "Strongly confident",
                "Presented as near-certain",
            ],
        },

        "manipulation_language": {
            "type": "noul",
            "instructions": (
                "Does the message contain language that appears "
                "designed to pressure, hype, manipulate or unduly "
                "influence traders?"
            ),
            "criteria": {
                "true": (
                    "Pressure, hype, guaranteed outcomes, "
                    "or manipulative promotional language."
                ),
                "false": (
                    "Neutral or ordinary market language."
                ),
            },
        },
    }

    payload = {
        "model": JEV_MODEL,
        "state": text,
        "questions": questions,
    }

    headers = {
        "Authorization": (
            f"Bearer {api_key}"
        ),
        "Content-Type": "application/json",
    }

    response = requests.post(
        TOKENRA_JEV_URL,
        headers=headers,
        json=payload,
        timeout=timeout,
    )

    response.raise_for_status()

    data = response.json()

    answers = data.get(
        "answers"
    )

    if not isinstance(
        answers,
        dict,
    ):

        raise RuntimeError(
            "TokenRa Jev response did not "
            "contain a valid answers object."
        )

    # ----------------------------------------------------------------------
    # Normalize Jev response
    # ----------------------------------------------------------------------

    return {
        "jev_id": data.get(
            "id"
        ),

        "model": data.get(
            "model",
            JEV_MODEL,
        ),

        "provider": data.get(
            "provider"
        ),

        "message_class": _choice(
            answers,
            "message_class",
        ),

        "message_class_confidence":
            _confidence(
                answers,
                "message_class",
            ),

        "market_relevant":
            _probability(
                answers,
                "market_relevant",
            ),

        "trading_intent":
            _score(
                answers,
                "trading_intent",
            ),

        "urgency":
            _score(
                answers,
                "urgency",
            ),

        "promotion_style":
            _score(
                answers,
                "promotion_style",
            ),

        "market_domain":
            _choice(
                answers,
                "market_domain",
            ),

        "market_domain_confidence":
            _confidence(
                answers,
                "market_domain",
            ),

        "specific_asset":
            _probability(
                answers,
                "specific_asset",
            ),

        "claim_strength":
            _score(
                answers,
                "claim_strength",
            ),

        "manipulation_language":
            _probability(
                answers,
                "manipulation_language",
            ),

        "usage": data.get(
            "usage",
            {},
        ),

        "raw_answers": answers,
    }


# --------------------------------------------------------------------------
# Manual test
# --------------------------------------------------------------------------

if __name__ == "__main__":

    samples = [
        "CDSL target 1500 tomorrow. Guaranteed breakout.",
        "Don't miss crudeoil trade.",
        "RBI rate cut coming next week.",
    ]

    for index, sample in enumerate(
        samples,
        start=1,
    ):

        print()
        print(
            "=" * 72
        )

        print(
            f"TEST {index}: {sample}"
        )

        print(
            "=" * 72
        )

        try:

            result = classify(
                sample
            )

            for key, value in result.items():

                if key in {
                    "raw_answers",
                    "usage",
                }:
                    continue

                print(
                    f"{key}: {value}"
                )

        except Exception as exc:

            print(
                "ERROR:",
                exc,
            )