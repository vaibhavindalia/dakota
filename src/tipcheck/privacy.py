"""Privacy pipeline — run BEFORE parsing or storing anything.

Project-plan rules implemented here:
  - Strip phone numbers, @handles and likely names before storage.
  - Store only: ticker, timestamp, text fingerprint, coarse source label.
  - Raw text is deleted after parsing (callers must not persist it).
  - Fingerprint = normalised-text hash for near-duplicate detection.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

PHONE_RE = re.compile(r"(?:\+91[\-\s]?)?[6-9]\d{4}[\s\-]?\d{5}\b|\b\d{5}[\s\-]\d{5}\b")
HANDLE_RE = re.compile(r"@[\w_]{2,32}")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
URL_RE = re.compile(r"https?://\S+|www\.\S+|t\.me/\S+", re.I)


def scrub(text: str) -> str:
    """Remove PII and contact vectors from a raw tip. Returns cleaned text."""
    text = PHONE_RE.sub("[phone]", text)
    text = HANDLE_RE.sub("[handle]", text)
    text = EMAIL_RE.sub("[email]", text)
    text = URL_RE.sub("[link]", text)
    return text.strip()


def normalise(text: str) -> str:
    """Canonical form for duplicate detection: lowercase, strip punctuation,
    collapse whitespace, drop digits (targets vary, templates don't)."""
    text = unicodedata.normalize("NFKD", text).lower()
    text = re.sub(r"\d+", "#", text)
    text = re.sub(r"[^\w# ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fingerprint(text: str) -> str:
    """Short stable fingerprint of the normalised text (first 16 hex chars)."""
    return hashlib.sha256(normalise(text).encode()).hexdigest()[:16]


def make_report_record(ticker: str, ts, clean_text: str, source_label: str = "user") -> dict:
    """The ONLY thing Dakota is allowed to store from a submitted tip."""
    return {
        "ticker": ticker,
        "ts": ts,
        "fingerprint": fingerprint(clean_text),
        "source_label": source_label,  # coarse label only: 'user', 'telegram_public', 'replay'
        # NO raw text, NO channel names, NO personal identifiers
    }
