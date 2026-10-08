"""
Dakota — Single Pipeline Entry Point
====================================

ONE function that Telegram bot, channel reader and FastAPI all call,
so the three transports can never drift apart.

    raw text + source
        -> intake_tip()            scrub + parse + persist (no raw text)
        -> classify_message()      rules first, local ML fallback
        -> map_impact()            exact entity + investigation status
        -> non-financial?          log only, NO investigation
        -> universal_investigator  market / news / reddit / social evidence
        -> risk result             score 0-100 + band + reasons
        -> save_live_investigation()
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from src.intake.tip_intake import intake_tip, scrub
from src.intake.live_store import save_live_investigation
from src.classification.local_classifier import classify_message
from src.investigation.impact_mapper import map_impact
from src.investigation import universal_investigator as investigator

log = logging.getLogger("dakota.pipeline")

NON_FINANCIAL_STATUSES = {
    "classified_non_financial",
    "non_financial",
    "ignored",
}


# ---------------------------------------------------------------------------
# tolerant helpers (removed once exact signatures are confirmed)
# ---------------------------------------------------------------------------


def _as_dict(obj: Any) -> Dict[str, Any]:
    """Normalize dataclass / object / dict into a plain dict."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if is_dataclass(obj):
        return asdict(obj)
    if hasattr(obj, "to_dict"):
        try:
            return dict(obj.to_dict())
        except Exception:
            pass
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in vars(obj).items() if not k.startswith("_")}
    return {"value": obj}


def _try_calls(fn: Callable, attempts: List[tuple]) -> Any:
    """Try several (args, kwargs) conventions; return first success."""
    last_error: Optional[Exception] = None
    for args, kwargs in attempts:
        try:
            return fn(*args, **kwargs)
        except TypeError as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    return None


def _pick(data: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    """First present, non-empty key — tolerates field-name drift."""
    for key in keys:
        if key in data and data[key] not in (None, "", [], {}):
            return data[key]
    return default


# ---------------------------------------------------------------------------
# stages
# ---------------------------------------------------------------------------


def _stage_intake(raw_text: str, source: str) -> Dict[str, Any]:
    record = _try_calls(
        intake_tip,
        [
            ((raw_text,), {"source": source}),
            ((raw_text, source), {}),
            ((raw_text,), {}),
        ],
    )
    return _as_dict(record)


def _stage_classify(clean_text: str) -> Dict[str, Any]:
    return _as_dict(classify_message(clean_text))


def _stage_impact(classification: Dict[str, Any], clean_text: str) -> Dict[str, Any]:
    result = _try_calls(
        map_impact,
        [
            ((classification,), {}),
            ((classification,), {"text": clean_text}),
            ((classification, clean_text), {}),
        ],
    )
    return _as_dict(result)


def _stage_investigate(
    clean_text: str,
    entity: Optional[str],
    domain: Optional[str],
) -> Dict[str, Any]:
    """
    universal_investigator already owns evidence collection + scoring.
    Prefer investigate_message (full text), fall back to investigate_tip.
    """
    errors: List[str] = []

    for name in ("investigate_message", "investigate_tip"):
        fn = getattr(investigator, name, None)
        if not callable(fn):
            continue
        try:
            result = _try_calls(
                fn,
                [
                    ((clean_text,), {}),
                    ((clean_text,), {"entity": entity}),
                    ((clean_text,), {"entity": entity, "domain": domain}),
                    ((entity,), {}) if entity else ((clean_text,), {}),
                ],
            )
            out = _as_dict(result)
            if out:
                out.setdefault("investigator", name)
                return out
        except Exception as exc:  # one dead provider must not kill the run
            errors.append(f"{name}: {exc}")
            log.warning("%s failed: %s", name, exc)

    return {
        "investigator": "unavailable",
        "evidence_status": "unavailable",
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------


def run_pipeline(
    raw_text: str,
    source: str = "unknown",
    persist_live: bool = True,
) -> Dict[str, Any]:
    """Run the full Dakota path. Never raises on provider failure."""
    clean_text = scrub(raw_text or "")

    tip = _stage_intake(raw_text, source)

    try:
        classification = _stage_classify(clean_text)
    except Exception as exc:
        log.exception("classification failed")
        classification = {"error": str(exc), "method": "failed"}

    try:
        impact = _stage_impact(classification, clean_text)
    except Exception as exc:
        log.exception("impact mapping failed")
        impact = {"error": str(exc), "status": "impact_mapping_failed"}

    status = str(_pick(impact, "status", "investigation_status", default="unknown"))
    domain = _pick(impact, "domain", "market_domain")
    entity = _pick(impact, "entity", "exact_topic", "topic")

    if not entity:
        tickers = _pick(tip, "tickers", default=[]) or []
        entity = tickers[0] if tickers else None

    record: Dict[str, Any] = {
        "investigation_id": _pick(tip, "investigation_id", "id"),
        "created_at": _pick(
            tip,
            "created_at",
            default=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ),
        "source": source,
        "entity": entity,
        "domain": domain,
        "status": status,
        "tip": tip,
        "classification": classification,
        "impact": impact,
    }

    # --- non-financial: log only, no investigation -------------------------
    if status in NON_FINANCIAL_STATUSES:
        record["status"] = "classified_non_financial"
        record["risk"] = {
            "score": None,
            "band": "Not assessed",
            "reasons": ["Message is not a financial tip — no investigation run."],
        }
        record["evidence"] = []
        record["coverage"] = {"investigated": False, "reason": "non_financial"}
        if persist_live:
            _persist(record)
        return record

    # --- investigate -------------------------------------------------------
    investigation = _stage_investigate(clean_text, entity, domain)

    risk = _pick(investigation, "risk", "risk_result", default=None)
    risk = _as_dict(risk) if risk else {}
    if not risk:
        score = _pick(investigation, "score")
        if score is not None:
            risk = {
                "score": score,
                "band": _pick(investigation, "band", default=""),
                "verdict": _pick(investigation, "verdict", "headline", default=""),
                "reasons": _pick(investigation, "reasons", default=[]),
                "contributions": _pick(investigation, "contributions", default={}),
                "next_steps": _pick(investigation, "next_steps", default=[]),
            }

    if not risk:
        risk = {
            "score": None,
            "band": "Pending",
            "reasons": ["Investigation returned no score — evidence incomplete."],
        }
        record["status"] = "partial"
    else:
        record["status"] = "complete"

    record["investigation"] = investigation
    record["risk"] = risk
    record["evidence"] = _pick(investigation, "evidence", default=[])
    record["coverage"] = _pick(
        investigation,
        "coverage",
        "connector_status",
        default={"investigated": True},
    )

    if persist_live:
        _persist(record)
    return record


def _persist(record: Dict[str, Any]) -> None:
    try:
        _try_calls(
            save_live_investigation,
            [((record,), {}), ((), {"record": record}), ((), {"data": record})],
        )
    except Exception as exc:
        log.warning("live_store persist failed: %s", exc)


# ---------------------------------------------------------------------------
# CLI harness — debug here, never through Telegram
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Dakota pipeline on one message.")
    parser.add_argument("--text", required=True, help="the tip text")
    parser.add_argument("--source", default="manual", help="telegram | whatsapp | x | manual")
    parser.add_argument("--no-persist", action="store_true", help="skip live_store write")
    parser.add_argument("--quiet", action="store_true", help="summary only")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO)

    result = run_pipeline(args.text, source=args.source, persist_live=not args.no_persist)

    if args.quiet:
        risk = result.get("risk") or {}
        print(
            f"{result.get('status')} | entity={result.get('entity')} "
            f"| domain={result.get('domain')} | score={risk.get('score')} "
            f"({risk.get('band')})"
        )
    else:
        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
