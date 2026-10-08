"""
Dakota — Tip Intake Layer
=========================

Telegram / WhatsApp / X / manual tip
        -> privacy scrub
        -> parse
        -> investigation record
        -> persisted (no raw text, no PII)

This module is source-agnostic. Telegram is just one caller.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]

TIP_STORE_DIR = ROOT / "data" / "tips"
TIP_STORE_FILE = TIP_STORE_DIR / "investigations.jsonl"


ALLOWED_SOURCES = {
    "telegram",
    "whatsapp",
    "x",
    "reddit",
    "instagram",
    "manual",
    "unknown",
}


# --------------------------------------------------------------------------
# Fallback privacy scrubber
# --------------------------------------------------------------------------

_PHONE = re.compile(
    r"(?:\+?\d[\d\-\s()]{7,}\d)"
)

_EMAIL = re.compile(
    r"[\w.\-+]+@[\w\-]+\.[\w.\-]+"
)

_HANDLE = re.compile(
    r"(?<!\w)@\w{2,}"
)

_URL = re.compile(
    r"(?:https?://|www\.|t\.me/)\S+",
    re.IGNORECASE,
)

_UPI = re.compile(
    r"\b[\w.\-]{2,}@(?:ybl|oksbi|okaxis|paytm|upi|ibl|axl)\b",
    re.IGNORECASE,
)


def _fallback_scrub(text: str) -> str:
    """Fallback PII scrubber used if the project privacy module is unavailable."""

    out = text

    out = _URL.sub("[link]", out)
    out = _EMAIL.sub("[email]", out)
    out = _UPI.sub("[upi]", out)
    out = _PHONE.sub("[phone]", out)
    out = _HANDLE.sub("[handle]", out)

    out = re.sub(r"[ \t]+", " ", out)

    return out.strip()


def scrub(text: str) -> str:
    """
    Prefer the project's existing privacy.scrub() implementation.

    Falls back to the local scrubber if the existing privacy module
    cannot be imported.
    """

    try:
        from src.tipcheck import privacy

        fn = getattr(privacy, "scrub", None)

        if callable(fn):
            result = fn(text)

            if isinstance(result, str):
                return result

    except Exception:
        pass

    return _fallback_scrub(text)


# --------------------------------------------------------------------------
# Parser bridge
# --------------------------------------------------------------------------

_TICKER_CASHTAG = re.compile(
    r"[\$#]([A-Z][A-Z0-9&\-]{1,14})"
)


def _parse_with_project_parser(
    clean_text: str,
) -> dict[str, Any] | None:
    """
    Use Dakota's existing parser.

    The current project exposes parse_tip(), so that is preferred.
    A few fallback function names are tolerated for compatibility.
    """

    try:
        from src.tipcheck import parser
    except Exception:
        return None

    parse_fn = getattr(parser, "parse_tip", None)

    if callable(parse_fn):
        try:
            parsed = parse_fn(clean_text)

            if hasattr(parsed, "__dict__"):
                return dict(vars(parsed))

            if isinstance(parsed, dict):
                return parsed

        except Exception:
            pass

    return None


def _fallback_parse(
    clean_text: str,
) -> dict[str, Any]:
    """Minimal parser if the project's parser cannot be loaded."""

    upper = clean_text.upper()

    tickers = sorted(
        set(
            _TICKER_CASHTAG.findall(upper)
        )
    )

    target = None

    target_match = re.search(
        r"(?:target|tgt|tp)"
        r"\s*[:=\-]?"
        r"\s*(?:rs\.?|inr|₹)?"
        r"\s*([0-9][0-9,]*(?:\.\d+)?)",
        clean_text,
        re.IGNORECASE,
    )

    if target_match:
        try:
            target = float(
                target_match.group(1).replace(",", "")
            )
        except ValueError:
            target = None

    urgency = bool(
        re.search(
            r"\b("
            r"urgent|hurry|today only|last chance|"
            r"don't miss|dont miss|buy now|fast|immediately"
            r")\b",
            clean_text,
            re.IGNORECASE,
        )
    )

    return {
        "clean_text": clean_text,
        "tickers": tickers,
        "price_target": target,
        "markers_found": [],
        "n_scam_markers": 0,
        "urgency": urgency,
        "sebi_reg_claimed": bool(
            re.search(
                r"\bsebi\b",
                clean_text,
                re.IGNORECASE,
            )
        ),
        "sebi_reg_number": None,
        "sebi_reg_verified": False,
        "fingerprint": fingerprint(clean_text),
        "parser": "fallback",
    }


# --------------------------------------------------------------------------
# Fingerprint
# --------------------------------------------------------------------------

def fingerprint(text: str) -> str:
    """
    Stable normalized fingerprint for near-duplicate detection.
    """

    normalized = re.sub(
        r"\d+",
        "#",
        text.lower(),
    )

    normalized = re.sub(
        r"[^a-z0-9# ]",
        " ",
        normalized,
    )

    normalized = re.sub(
        r"\s+",
        " ",
        normalized,
    ).strip()

    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()[:16]


# --------------------------------------------------------------------------
# Investigation record
# --------------------------------------------------------------------------

@dataclass
class InvestigationRecord:
    investigation_id: str
    created_at: str
    source: str

    tickers: list[str]
    primary_ticker: str | None

    price_target: float | None

    urgency: bool

    n_scam_markers: int
    markers_found: list[str] = field(
        default_factory=list
    )

    sebi_reg_claimed: bool = False
    sebi_reg_verified: bool = False

    fingerprint: str = ""

    status: str = "created"
    parser: str = "project"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _coerce_list(
    value: Any,
) -> list[str]:
    if value is None:
        return []

    if isinstance(value, dict):
        return [
            str(key)
            for key in value.keys()
        ]

    if isinstance(value, (list, tuple, set)):
        return [
            str(item)
            for item in value
        ]

    return [str(value)]


def _normalise_tickers(
    value: Any,
) -> list[str]:
    tickers = _coerce_list(value)

    result: list[str] = []

    for ticker in tickers:
        clean = (
            str(ticker)
            .strip()
            .upper()
        )

        if clean and clean not in result:
            result.append(clean)

    return result


# --------------------------------------------------------------------------
# Main intake function
# --------------------------------------------------------------------------

def intake_tip(
    raw_text: str,
    source: str = "unknown",
) -> InvestigationRecord:
    """
    Main entry point for every incoming Dakota tip.

    Pipeline:

        raw text
            ↓
        privacy scrub
            ↓
        parse
            ↓
        investigation record
            ↓
        JSONL persistence

    Raw message text is NOT stored in the investigation record.
    """

    source = (
        source
        .strip()
        .lower()
    )

    if source not in ALLOWED_SOURCES:
        source = "unknown"

    raw_text = raw_text or ""

    clean_text = scrub(raw_text)

    parsed = _parse_with_project_parser(
        clean_text
    )

    if parsed is None:
        parsed = _fallback_parse(
            clean_text
        )

    tickers = _normalise_tickers(
        parsed.get("tickers")
    )

    markers = _coerce_list(
        parsed.get("markers_found")
    )

    n_scam_markers = parsed.get(
        "n_scam_markers"
    )

    try:
        n_scam_markers = int(
            n_scam_markers
            if n_scam_markers is not None
            else len(markers)
        )
    except (TypeError, ValueError):
        n_scam_markers = len(markers)

    parsed_fingerprint = str(
        parsed.get("fingerprint")
        or ""
    ).strip()

    if not parsed_fingerprint:
        parsed_fingerprint = fingerprint(
            clean_text
        )

    sebi_verified = parsed.get(
        "sebi_reg_verified"
    )

    # None means "not checked".
    # The intake record only stores a conservative boolean.
    sebi_verified_bool = (
        True
        if sebi_verified is True
        else False
    )

    record = InvestigationRecord(
        investigation_id=uuid.uuid4().hex[:12],

        created_at=datetime.now(
            timezone.utc
        ).isoformat(
            timespec="seconds"
        ),

        source=source,

        tickers=tickers,

        primary_ticker=(
            tickers[0]
            if tickers
            else None
        ),

        price_target=parsed.get(
            "price_target"
        ),

        urgency=bool(
            parsed.get("urgency")
        ),

        n_scam_markers=n_scam_markers,

        markers_found=markers,

        sebi_reg_claimed=bool(
            parsed.get(
                "sebi_reg_claimed"
            )
        ),

        sebi_reg_verified=sebi_verified_bool,

        fingerprint=parsed_fingerprint,

        status=(
            "created"
            if tickers
            else "no_ticker_identified"
        ),

        parser=str(
            parsed.get(
                "parser",
                "project",
            )
        ),
    )

    save_record(record)

    return record


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------

def save_record(
    record: InvestigationRecord,
) -> None:

    TIP_STORE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with TIP_STORE_FILE.open(
        "a",
        encoding="utf-8",
    ) as handle:

        handle.write(
            json.dumps(
                record.to_dict(),
                ensure_ascii=False,
            )
            + "\n"
        )


def load_records(
    limit: int = 50,
) -> list[dict[str, Any]]:

    if not TIP_STORE_FILE.exists():
        return []

    lines = TIP_STORE_FILE.read_text(
        encoding="utf-8"
    ).splitlines()

    result: list[
        dict[str, Any]
    ] = []

    for line in lines[-limit:]:

        try:
            result.append(
                json.loads(line)
            )
        except json.JSONDecodeError:
            continue

    return result


# --------------------------------------------------------------------------
# Manual test
# --------------------------------------------------------------------------

if __name__ == "__main__":

    sample = (
        "URGENT $CDSL target 1500 tomorrow. "
        "Guaranteed breakout, assured profit. "
        "Join our VIP group https://t.me/fakevip "
        "call +91 98765 43210 "
        "pay to scam@ybl "
        "mail boss@example.com "
        "@tipsguru"
    )

    record = intake_tip(
        sample,
        source="telegram",
    )

    print(
        json.dumps(
            record.to_dict(),
            indent=2,
            ensure_ascii=False,
        )
    )

    print(
        "\nStored at:",
        TIP_STORE_FILE,
    )