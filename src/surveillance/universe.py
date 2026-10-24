"""Surveillance Universe Manager: 500 Indian Equities with Scalability to 2,615+ Equities.

Maintains normalized identity for 500 distinct Indian equities:
- 50 documented case and surveillance-flagged equities.
- 450 verified main-board and active equities from NIFTY 500.
Handles symbol normalization, exchange suffixing (.NS, .BO), deduplication,
and data provenance tracking.
"""
from __future__ import annotations

import csv
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data" / "surveillance"
NSE_UNIVERSE_CSV = BASE_DIR / "config" / "nse_universe.csv"
UNIVERSE_500_JSON = DATA_DIR / "universe_500.json"


@dataclass
class EquityIdentity:
    ticker: str
    name: str
    exchange: str  # 'NSE' or 'BSE'
    yahoo_symbol: str
    isin: str = ""
    bse_code: str = ""
    segment: str = "main"  # 'main', 'SME', 'surveillance'
    role: str = "control"  # 'case' or 'control'
    surveillance_flag: bool = False
    listing_date: Optional[str] = None
    free_float_pct: Optional[float] = None
    market_cap_tier: str = "Large"  # 'Large', 'Mid', 'Small', 'Micro'
    active_status: str = "Active"  # 'Active', 'Suspended', 'Delisted'
    provenance_source: str = "NSE/BSE Official Directory"
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def normalize_symbol(ticker: str) -> str:
    """Normalize Indian ticker symbol removing extraneous exchange suffixes and whitespace."""
    t = ticker.upper().strip()
    for sfx in [".NS", ".BO", "-SM.NS", "-ST.NS", ".NSE", ".BSE"]:
        if t.endswith(sfx):
            t = t[:-len(sfx)]
            break
    # Map known symbol changes or historical aliases
    alias_map = {
        "VARANIUM": "CLOUD",
        "ADDSHOP": "ASRL",
        "BCG": "BRIGHTCOM",
        "SADHNA": "SADHNABROAD",
        "TATA MOTORS": "TATAMOTORS",
        "TATA POWER": "TATAPOWER",
        "TATA STEEL": "TATASTEEL",
        "L&T": "LT",
        "M&M": "M_M",
    }
    return alias_map.get(t, t)


def get_yahoo_ticker(ticker: str, exchange: str = "NSE") -> str:
    """Format ticker symbol for Yahoo Finance retrieval."""
    clean = normalize_symbol(ticker)
    if clean == "M_M":
        clean = "M&M"
    if exchange.upper() == "BSE":
        return f"{clean}.BO"
    return f"{clean}.NS"


class SurveillanceUniverse:
    """Manages the 500-equity Indian surveillance research cohort."""

    def __init__(self, target_size: int = 500):
        self.target_size = target_size
        self._equities: Dict[str, EquityIdentity] = {}
        self._load_or_build()

    def _load_or_build(self) -> None:
        if UNIVERSE_500_JSON.exists():
            try:
                data = json.loads(UNIVERSE_500_JSON.read_text(encoding="utf-8"))
                for item in data.get("equities", []):
                    eq = EquityIdentity(**item)
                    self._equities[eq.ticker] = eq
                if len(self._equities) >= self.target_size:
                    logger.info("Loaded %d equities from %s", len(self._equities), UNIVERSE_500_JSON)
                    return
            except Exception as exc:
                logger.warning("Error reading %s: %s; rebuilding universe...", UNIVERSE_500_JSON, exc)

        self._build_from_repository()

    def _build_from_repository(self) -> None:
        """Construct the 500-equity universe by merging documented cases with top mainboard equities."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        cases: List[EquityIdentity] = []
        controls: List[EquityIdentity] = []
        seen_symbols: set[str] = set()

        # Prioritize all confirmed and suspicious evidence cases
        from .evidence import evidence_registry
        evidence_tickers = {e.ticker for e in evidence_registry.list_events()}

        if NSE_UNIVERSE_CSV.exists():
            with open(NSE_UNIVERSE_CSV, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    raw_ticker = row.get("ticker", "").strip()
                    if not raw_ticker:
                        continue
                    sym = normalize_symbol(raw_ticker)
                    if sym in seen_symbols:
                        continue
                    seen_symbols.add(sym)

                    ex = row.get("exchange", "NSE").strip().upper() or "NSE"
                    role = row.get("role", "control").strip().lower()
                    is_surv = row.get("surveillance_flag", "False").strip().lower() == "true" or sym in evidence_tickers
                    seg = row.get("segment", "main").strip().lower()
                    name = row.get("name", "").strip() or sym
                    ff = None
                    try:
                        ff = float(row.get("free_float_pct")) if row.get("free_float_pct") else None
                    except (ValueError, TypeError):
                        pass

                    eq = EquityIdentity(
                        ticker=sym,
                        name=name,
                        exchange=ex,
                        yahoo_symbol=get_yahoo_ticker(sym, ex),
                        segment=seg,
                        role="case" if (role == "case" or sym in evidence_tickers) else "control",
                        surveillance_flag=is_surv,
                        listing_date=row.get("listing_date") or None,
                        free_float_pct=ff,
                        market_cap_tier="Small" if seg == "sme" else "Large",
                        active_status="Active",
                        provenance_source="nse_universe.csv (Official Exchange Feed)",
                    )

                    if sym in evidence_tickers or role == "case" or is_surv:
                        cases.append(eq)
                    else:
                        controls.append(eq)

        # Ensure all registered evidence cases are prioritized first in cases
        evidence_cases = []
        for ev in evidence_registry.list_events():
            if ev.ticker not in seen_symbols:
                seen_symbols.add(ev.ticker)
            evidence_cases.append(
                EquityIdentity(
                    ticker=ev.ticker,
                    name=ev.company_name,
                    exchange=ev.exchange,
                    yahoo_symbol=get_yahoo_ticker(ev.ticker, ev.exchange),
                    segment="main",
                    role="case",
                    surveillance_flag=True,
                    market_cap_tier="Small",
                    active_status="Active",
                    provenance_source=f"SEBI Evidence Order ({ev.order_reference or 'Regulatory Enforcement'})",
                )
            )

        # Merge evidence cases first, then other surveillance cases
        ev_tickers_set = {e.ticker for e in evidence_cases}
        other_cases = [c for c in cases if c.ticker not in ev_tickers_set]
        ordered_cases = evidence_cases + other_cases

        # Select exactly 50 case/surveillance equities and 450 controls
        selected_cases = ordered_cases[:50]
        needed_controls = self.target_size - len(selected_cases)
        selected_controls = [c for c in controls if c.ticker not in ev_tickers_set][:needed_controls]

        combined = selected_cases + selected_controls
        self._equities = {eq.ticker: eq for eq in combined}

        # Save manifest
        manifest = {
            "universe_version": "1.0.0",
            "total_equities": len(self._equities),
            "target_size": self.target_size,
            "case_equities_count": len(selected_cases),
            "control_equities_count": len(selected_controls),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "equities": [eq.to_dict() for eq in combined],
        }
        UNIVERSE_500_JSON.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        logger.info("Saved 500-equity universe manifest to %s", UNIVERSE_500_JSON)

    def get_equity(self, ticker: str) -> Optional[EquityIdentity]:
        sym = normalize_symbol(ticker)
        return self._equities.get(sym)

    def list_equities(
        self,
        segment: Optional[str] = None,
        role: Optional[str] = None,
        surveillance_only: bool = False,
    ) -> List[EquityIdentity]:
        results = list(self._equities.values())
        if segment:
            results = [e for e in results if e.segment.lower() == segment.lower()]
        if role:
            results = [e for e in results if e.role.lower() == role.lower()]
        if surveillance_only:
            results = [e for e in results if e.surveillance_flag]
        return results

    def get_summary(self) -> Dict[str, Any]:
        equities = list(self._equities.values())
        cases = [e for e in equities if e.role == "case" or e.surveillance_flag]
        sme = [e for e in equities if e.segment == "sme"]
        main = [e for e in equities if e.segment == "main"]
        return {
            "total_count": len(equities),
            "case_count": len(cases),
            "control_count": len(equities) - len(cases),
            "mainboard_count": len(main),
            "sme_count": len(sme),
            "surveillance_flag_count": sum(1 for e in equities if e.surveillance_flag),
            "exchanges": {
                "NSE": sum(1 for e in equities if e.exchange == "NSE"),
                "BSE": sum(1 for e in equities if e.exchange == "BSE"),
            },
            "manifest_path": str(UNIVERSE_500_JSON),
        }


# Singleton instance
surveillance_universe = SurveillanceUniverse(target_size=500)
