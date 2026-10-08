"""
Tip Check parser v1: regex + keyword rules. Fast, explainable, no LLM.

Pipeline:
    raw tip text
      -> privacy.scrub
      -> extract ticker / price target / urgency / scam markers
      -> create an anonymised tip report
      -> hand off to engine.assess() for stock-level score

The scam markers mirror the warning table in the Dakota report.
The LLM extraction layer is a later polish pass — never a replacement,
because Dakota must remain explainable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

from src.tipcheck import privacy


# --------------------------------------------------------------------------
# Scam markers
# --------------------------------------------------------------------------

SCAM_MARKERS: dict[str, list[str]] = {
    "guaranteed_returns": [
        r"guaranteed returns?",
        r"assured (returns?|profit)",
        r"\b100 ?% ?(sure|certain|guaranteed)\b",
        r"risk[- ]?free",
        r"fixed (monthly |weekly )?(returns?|income)",
    ],
    "urgency_pressure": [
        r"\burgent\b",
        r"last chance",
        r"only (today|2 days|\d+ slots?)",
        r"act (now|fast|immediately)",
        r"limited (slots?|seats?|time)",
        r"before (monday|market opens?|it'?s too late)",
    ],
    "vip_funnel": [
        r"\bvip\b.{0,20}(group|channel|community)",
        r"\bvip (group|channel|members?)\b",
        r"free (course|training|webinar|workshop)",
        r"join .{0,25}(premium |paid )?(group|channel)",
        r"(whatsapp|telegram) (group|channel) (link|invite)",
    ],
    "app_or_payment_diversion": [
        r"\bapk\b",
        r"download (the |this |our )?app",
        r"install .{0,20}app",
        r"third[- ]party payment",
        r"\bupi\b.{0,30}(transfer|pay|deposit)",
        r"deposit .{0,20}(wallet|account)",
    ],
    "social_proof": [
        r"profit screenshots?",
        r"testimonials?",
        r"my (students?|members?) (made|earned|booked)",
        r"\b\d{4,7}\b.{0,20}profit (booked|made)",
        r"see (the |my )?results?",
    ],
    "missing_registration": [
        r"sebi registered(?!.{0,40}(ina|inh|inz)\d{6,})",
        r"registered investment advi[sz]er(?!.{0,40}(ina|inh)\d{6,})",
    ],
}


URGENCY_WORDS = [
    "urgent",
    "act now",
    "last chance",
    "limited",
    "hurry",
    "don't miss",
    "dont miss",
]


PRICE_TARGET_RE = re.compile(
    r"(?:target|tgt|tp)"
    r"\s*[:\-]?"
    r"\s*(?:rs\.?|₹|inr)?"
    r"\s*(\d[\d,]*(?:\.\d+)?)",
    re.I,
)


SEBI_REG_RE = re.compile(
    r"\b(INA|INH|INZ)\d{6,12}\b"
)


# --------------------------------------------------------------------------
# Parsed tip
# --------------------------------------------------------------------------

@dataclass
class ParsedTip:
    clean_text: str

    tickers: list[str] = field(
        default_factory=list
    )

    price_target: float | None = None

    markers_found: dict[str, list[str]] = field(
        default_factory=dict
    )

    n_scam_markers: int = 0

    urgency: bool = False

    sebi_reg_claimed: bool = False

    sebi_reg_number: str | None = None

    sebi_reg_verified: bool | None = None

    fingerprint: str = ""


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------

def parse_tip(
    raw_text: str,
    universe_tickers: list[str] | None = None,
) -> ParsedTip:
    """
    Parse one forwarded tip.

    Privacy scrubbing happens before parsing.
    Raw text is never stored in the returned report.
    """

    text = privacy.scrub(
        raw_text
    )

    tip = ParsedTip(
        clean_text=text
    )

    # ------------------------------------------------------------------
    # Ticker extraction
    # ------------------------------------------------------------------

    if universe_tickers is None:

        from src.ingest.market_data import load_universe

        universe_tickers = (
            load_universe()
            .ticker
            .tolist()
        )

    upper = text.upper()

    # Known tickers from Dakota's tracked universe.
    for ticker in universe_tickers:

        if re.search(
            rf"\b{re.escape(ticker.upper())}\b",
            upper,
        ):
            tip.tickers.append(
                ticker
            )

    # Also catch $TICKER / #TICKER even if
    # it is not currently in the universe.
    for match in re.findall(
        r"[$#]([A-Z]{2,12})\b",
        upper,
    ):

        if match not in tip.tickers:
            tip.tickers.append(
                match
            )

    # ------------------------------------------------------------------
    # Price target
    # ------------------------------------------------------------------

    match = PRICE_TARGET_RE.search(
        text
    )

    if match:

        tip.price_target = float(
            match.group(1)
            .replace(",", "")
        )

    # ------------------------------------------------------------------
    # Scam markers
    # ------------------------------------------------------------------

    for category, patterns in SCAM_MARKERS.items():

        hits = [
            pattern
            for pattern in patterns
            if re.search(
                pattern,
                text,
                re.I,
            )
        ]

        if hits:
            tip.markers_found[
                category
            ] = hits

    tip.n_scam_markers = sum(
        len(values)
        for values in tip.markers_found.values()
    )

    tip.urgency = (
        any(
            word in text.lower()
            for word in URGENCY_WORDS
        )
        or "urgency_pressure"
        in tip.markers_found
    )

    # ------------------------------------------------------------------
    # SEBI registration
    # ------------------------------------------------------------------

    registration = SEBI_REG_RE.search(
        upper
    )

    if registration:

        tip.sebi_reg_claimed = True

        tip.sebi_reg_number = (
            registration.group(0)
        )

        # Verification is intentionally not claimed here.
        tip.sebi_reg_verified = None

    elif (
        "missing_registration"
        in tip.markers_found
    ):

        tip.sebi_reg_claimed = True

        tip.sebi_reg_number = None

    # ------------------------------------------------------------------
    # Fingerprint
    # ------------------------------------------------------------------

    tip.fingerprint = (
        privacy.fingerprint(text)
    )

    return tip


# --------------------------------------------------------------------------
# Build a tip report for the risk engine
# --------------------------------------------------------------------------

def build_tip_reports(
    tip: ParsedTip,
    source_label: str = "telegram",
    timestamp: str | None = None,
) -> pd.DataFrame:
    """
    Convert the parsed tip into the anonymised DataFrame format expected
    by the Dakota coordination signal engine.

    No raw tip text is included.

    Columns:
        ticker
        ts
        fingerprint
        n_scam_markers
        source_label
    """

    if timestamp is None:

        ts = pd.Timestamp.now().normalize()

    else:

        ts = pd.Timestamp(
            timestamp
        )

    rows = []

    for ticker in tip.tickers:

        rows.append(
            {
                "ticker": ticker,
                "ts": ts,
                "fingerprint": tip.fingerprint,
                "n_scam_markers": tip.n_scam_markers,
                "source_label": source_label,
            }
        )

    if not rows:

        return pd.DataFrame(
            columns=[
                "ticker",
                "ts",
                "fingerprint",
                "n_scam_markers",
                "source_label",
            ]
        )

    return pd.DataFrame(
        rows
    )


# --------------------------------------------------------------------------
# Full Tip Check
# --------------------------------------------------------------------------

def check_tip(
    raw_text: str,
    source_label: str = "manual",
    timestamp: str | None = None,
) -> dict:
    """
    Full Tip Check:

        parse tip
        -> create anonymised tip report
        -> score every mentioned known ticker
        -> return combined verdict

    The tip report is now passed into the risk engine, so
    suspicious tip characteristics can affect the coordination score.
    """

    from src.engine.risk_engine import assess

    from src.ingest.market_data import (
        load_universe,
    )

    # ------------------------------------------------------------------
    # Parse
    # ------------------------------------------------------------------

    tip = parse_tip(
        raw_text
    )

    # ------------------------------------------------------------------
    # Universe
    # ------------------------------------------------------------------

    known = set(
        load_universe()
        .ticker
    )

    # ------------------------------------------------------------------
    # Tip report
    # ------------------------------------------------------------------

    tip_reports = build_tip_reports(
        tip,
        source_label=source_label,
        timestamp=timestamp,
    )

    # ------------------------------------------------------------------
    # Point-in-time date
    # ------------------------------------------------------------------

    if timestamp is None:

        as_of = pd.Timestamp.now().normalize()

    else:

        as_of = pd.Timestamp(
            timestamp
        )

    # ------------------------------------------------------------------
    # Stock verdicts
    # ------------------------------------------------------------------

    verdicts = []

    for ticker in tip.tickers:

        if ticker not in known:
            continue

        verdicts.append(
            assess(
                ticker,
                as_of=as_of,
                tip_reports=tip_reports,
            )
        )

    # ------------------------------------------------------------------
    # Best stock verdict
    # ------------------------------------------------------------------

    best = max(
        verdicts,
        key=lambda verdict: verdict["score"],
        default=None,
    )

    # ------------------------------------------------------------------
    # Tip-level reasons
    # ------------------------------------------------------------------

    tip_reasons = _tip_level_reasons(
        tip
    )

    # ------------------------------------------------------------------
    # Final result
    # ------------------------------------------------------------------

    return {
        "parsed": tip,

        "tip_reports": tip_reports,

        "stock_verdicts": verdicts,

        "headline": (
            best["verdict"]
            if best
            else (
                "Suspicious message patterns detected"
                if tip.n_scam_markers >= 2
                else "No known stock identified in this tip"
            )
        ),

        "tip_level_reasons": tip_reasons,

        "combined_reasons": (
            tip_reasons
            + (
                best["reasons"]
                if best
                else []
            )
        ),

        "next_steps": (
            best["next_steps"]
            if best
            else [
                "Could not match a tracked stock "
                "— double-check the ticker name."
            ]
        ),

        "disclaimer": (
            "Risk indicators, not an accusation. "
            "Not investment advice."
        ),
    }


# --------------------------------------------------------------------------
# Human-readable tip reasons
# --------------------------------------------------------------------------

def _tip_level_reasons(
    tip: ParsedTip,
) -> list[str]:

    reasons = []

    labels = {

        "guaranteed_returns":
            "Promises guaranteed/assured returns",

        "urgency_pressure":
            "Uses urgency and pressure language",

        "vip_funnel":
            "Funnels you into a VIP group / free-course channel",

        "app_or_payment_diversion":
            "Pushes an app/APK or third-party payment — "
            "a higher-risk scam pattern",

        "social_proof":
            "Uses profit screenshots/testimonials as a "
            "substitute for verification",

        "missing_registration":
            "Claims advisory status without a visible "
            "SEBI registration number",
    }

    for category in tip.markers_found:

        if category in labels:

            reasons.append(
                labels[category]
            )

    if tip.price_target:

        reasons.append(
            "Quotes a specific price target "
            f"(₹{tip.price_target:,.0f})"
        )

    if (
        tip.sebi_reg_claimed
        and tip.sebi_reg_number
        and tip.sebi_reg_verified is None
    ):

        reasons.append(
            "Shows SEBI number "
            f"{tip.sebi_reg_number} — "
            "NOT yet verified against the register"
        )

    return reasons


# --------------------------------------------------------------------------
# Manual test
# --------------------------------------------------------------------------

if __name__ == "__main__":

    sample = (
        "URGENT!! CDSL target Rs 1500 tomorrow. "
        "Guaranteed returns. "
        "Join my VIP telegram channel. "
        "Only 10 slots left."
    )

    result = check_tip(
        sample,
        source_label="telegram",
    )

    print(
        "HEADLINE:",
        result["headline"],
    )

    print(
        "\nTICKERS:",
        result["parsed"].tickers,
    )

    print(
        "TARGET:",
        result["parsed"].price_target,
    )

    print(
        "MARKERS:",
        result["parsed"].markers_found,
    )

    print(
        "\nSTOCK VERDICTS:"
    )

    for verdict in result[
        "stock_verdicts"
    ]:

        print(
            verdict
        )

    print(
        "\nTIP REPORTS:"
    )

    print(
        result[
            "tip_reports"
        ]
        .to_string(index=False)
    )

    print(
        "\nREASONS:"
    )

    for reason in result[
        "combined_reasons"
    ]:

        print(
            " -",
            reason,
        )