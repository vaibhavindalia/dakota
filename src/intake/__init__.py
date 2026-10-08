"""
Dakota — Tip Intake Layer
=========================

Telegram / WhatsApp / X / manual tip
        -> privacy scrub
        -> parse
        -> investigation record
        -> persisted (no raw text, no PII)

This module is deliberately source-agnostic. The Telegram bot is just one
caller; the FastAPI /api/investigate route can call the same function.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# --------------------------------------------------------------------------
# Storage location
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
# Privacy scrub — use the project scrubber if present, else local fallback
# --------------------------------------------------------------------------

_PHONE = re.compile(r"(?:\+?\d[\d\-\s()]{7,}\d)")
_EMAIL = re.compile(r"[\w.\-+]+@[\w\-]+\.[\w.\-]+")
_HANDLE = re.compile(r"(?<!\w)@\w{2,}")
_URL = re.compile(r"(?:https?://|www\.|t\.me/)\S+", re.IGNORECASE)
_UPI = re.compile(r"\b[\w.\-]{2,}@(?:ybl|oksbi|okaxis|paytm|upi|ibl|axl)\b", re.I)


def _fallback_scrub(text: str) -> str:
    out = text
    out = _URL.sub("[link]", out)
    out = _EMAIL.sub("[email]", out)
    out = _UPI.sub("[upi]", out)
    out = _PHONE.sub("[phone]", out)
    out = _HANDLE.sub("[handle]", out)
    return re.sub(r"[ \t]+", " ", out).strip()


def scrub(text: str) -> str:
    """Strip PII. Prefers src.tipcheck.privacy if it exposes a scrubber."""
    try:
        from src.tipcheck import privacy as _privacy  # type: ignore

        for name in ("scrub", "scrub_text", "strip_pii", "sanitize", "clean"):
            fn = getattr(_privacy, name, None)
            if callable(fn):
                result = fn(text)
                if isinstance(result, str):
                    return result
                # some implementations return (clean_text, meta)
                if isinstance(result, (tuple, list)) and result and isinstance(result[0], str):
                    return result[0]
    except Exception:
        pass
    return _fallback_scrub(text)


# --------------------------------------------------------------------------
# Parser bridge
# --------------------------------------------------------------------------

_TICKER_CASHTAG = re.compile(r"[\$#]([A-Z][A-Z0-9&\-]{1,14})")


def _parse_with_project_parser(clean_text: str) -> Optional[Dict[str, Any]]:
    """Call src.tipcheck.parser, tolerating different function names."""
    try:
        from src.tipcheck import parser as _parser  # type: ignore
    except Exception:
        return None

    for name in ("parse_tip", "parse", "ParsedTip"):
        fn = getattr(_parser, name, None)
        if fn is None:
            continue
        try:
            parsed = fn(clean_text) if name != "ParsedTip" else None
        except Exception:
            parsed = None
        if parsed is None:
            continue
        if hasattr(parsed, "__dict__"):
            return dict(vars(parsed))
        if isinstance(parsed, dict):
            return parsed
    return None


def _fallback_parse(clean_text: str) -> Dict[str, Any]:
    tickers = sorted(set(_TICKER_CASHTAG.findall(clean_text.upper())))
    target = None
    m = re.search(
        r"(?:target|tgt|tp)\s*[:=]?\s*(?:rs\.?|inr|₹)?\s*([0-9][0-9,]*(?:\.\d+)?)",
        clean_text,
        re.IGNORECASE,
    )
    if m:
        try:
            target = float(m.group(1).replace(",", ""))
        except ValueError:
            target = None
    urgency = bool(
        re.search(
            r"\b(urgent|hurry|today only|last chance|don'?t miss|buy now|fast|immediately)\b",
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
        "sebi_reg_claimed": bool(re.search(r"sebi", clean_text, re.IGNORECASE)),
        "sebi_reg_number": None,
        "sebi_reg_verified": False,
        "fingerprint": fingerprint(clean_text),
        "parser": "fallback",
    }


def fingerprint(text: str) -> str:
    """Normalized hash for near-duplicate / coordination detection."""
    norm = re.sub(r"[^a-z0-9 ]", " ", text.lower())
    norm = re.sub(r"\s+", " ", norm).strip()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------
# Investigation record
# --------------------------------------------------------------------------


@dataclass
class InvestigationRecord:
    investigation_id: str
    created_at: str
    source: str
    tickers: List[str]
    primary_ticker: Optional[str]
    price_target: Optional[float]
    urgency: bool
    n_scam_markers: int
    markers_found: List[str] = field(default_factory=list)
    sebi_reg_claimed: bool = False
    sebi_reg_verified: bool = False
    fingerprint: str = ""
    status: str = "created"
    parser: str = "project"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _coerce_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(v) for v in value]
    return [str(value)]


def intake_tip(raw_text: str, source: str = "unknown") -> InvestigationRecord:
    """
    Entry point for every tip Dakota receives.

    Raw text is scrubbed, parsed, turned into a record, and persisted.
    The raw message is never returned or stored.
    """
    source = source.lower().strip()
    if source not in ALLOWED_SOURCES:
        source = "unknown"

    clean_text = scrub(raw_text or "")

    parsed = _parse_with_project_parser(clean_text)
    if not parsed:
        parsed = _fallback_parse(clean_text)

    tickers = _coerce_list(parsed.get("tickers"))
    markers = _coerce_list(parsed.get("markers_found"))

    record = InvestigationRecord(
        investigation_id=uuid.uuid4().hex[:12],
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        source=source,
        tickers=tickers,
        primary_ticker=tickers[0] if tickers else None,
        price_target=parsed.get("price_target"),
        urgency=bool(parsed.get("urgency")),
        n_scam_markers=int(parsed.get("n_scam_markers") or len(markers)),
        markers_found=markers,
        sebi_reg_claimed=bool(parsed.get("sebi_reg_claimed")),
        sebi_reg_verified=bool(parsed.get("sebi_reg_verified")),
        fingerprint=str(parsed.get("fingerprint") or fingerprint(clean_text)),
        status="created" if tickers else "no_ticker_identified",
        parser=str(parsed.get("parser", "project")),
    )

    save_record(record)
    return record


def save_record(record: InvestigationRecord) -> None:
    TIP_STORE_DIR.mkdir(parents=True, exist_ok=True)
    with TIP_STORE_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")


def load_records(limit: int = 50) -> List[Dict[str, Any]]:
    if not TIP_STORE_FILE.exists():
        return []
    lines = TIP_STORE_FILE.read_text(encoding="utf-8").splitlines()
    out: List[Dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


# --------------------------------------------------------------------------
# Manual test
# --------------------------------------------------------------------------

if __name__ == "__main__":
    sample = (
        "URGENT $CDSL target 1500 tomorrow. Guaranteed breakout, assured profit. "
        "Join our VIP group https://t.me/fakevip call +91 98765 43210 "
        "pay to scam@ybl, mail boss@example.com @tipsguru"
    )
    rec = intake_tip(sample, source="telegram")
    print(json.dumps(rec.to_dict(), indent=2))
    print("\nstored at:", TIP_STORE_FILE)
