"""Universal Dakota investigation pipeline for stock and non-stock topics.

Stock investigations use Dakota's real five-group risk engine. Public web
evidence is attached to the investigation for explanation and review; it does
not directly change the numeric risk score.

For stock news, Pulkit's News analyzer is used:
    Yahoo Finance RSS (NSE symbols translated to .NS)
    Google News RSS
    optional LLM analysis when configured

Missing or unavailable evidence remains explicitly visible.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from src.evidence.aggregate import aggregate_scores
from src.evidence.news import search_news
from src.evidence.social import collect_social_evidence
from src.investigation.impact_mapper import map_impact
from src.investigation.tip_investigator import investigate_tip


def _label(topic: str) -> str:
    return topic.replace("_", " ").strip()


def _flatten_social(social: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for value in social.values():
        if isinstance(value, dict):
            out.extend(value.get("observations") or [])
    return out


def _market_topic_observations(impact: dict[str, Any]) -> list[dict[str, Any]]:
    areas = impact.get("potentially_affected_areas") or []
    if not areas:
        return []
    return [{
        "signal": "impact_mapping",
        "severity": "low",
        "text": (
            "Potentially affected areas identified: "
            + ", ".join(str(a).replace("_", " ") for a in areas[:6])
            + ". This is an investigation scope, not a claimed causal relationship."
        ),
    }]


def _as_of_timestamp(timestamp: str | None) -> pd.Timestamp:
    """Return a timezone-naive UTC timestamp suitable for the risk engine."""
    if timestamp:
        try:
            ts = pd.Timestamp(timestamp)
            if ts.tzinfo is not None:
                ts = ts.tz_convert("UTC").tz_localize(None)
            return ts
        except Exception:
            pass
    return pd.Timestamp(datetime.now(timezone.utc)).tz_localize(None)


def _record_value(record: Any, key: str, default: Any = None) -> Any:
    if isinstance(record, dict):
        return record.get(key, default)
    return getattr(record, key, default)


def _load_tip_reports(
    *,
    current_result: dict[str, Any],
    raw_text: str,
    source_label: str,
    timestamp: str | None,
) -> pd.DataFrame:
    """Build the anonymised tip-report frame expected by risk_engine.assess()."""
    rows: list[dict[str, Any]] = []

    # Historical intake records already persist only de-identified tip metadata.
    try:
        from src.intake.tip_intake import load_records

        for record in load_records(limit=500):
            tickers = _record_value(record, "tickers", []) or []
            primary = _record_value(record, "primary_ticker")
            ticker = str(primary or (tickers[0] if tickers else "")).upper().strip()
            if not ticker:
                continue

            created_at = _record_value(record, "created_at")
            try:
                ts = pd.Timestamp(created_at)
                if ts.tzinfo is not None:
                    ts = ts.tz_convert("UTC").tz_localize(None)
            except Exception:
                continue

            rows.append({
                "ticker": ticker,
                "ts": ts,
                "fingerprint": str(_record_value(record, "fingerprint", "")),
                "n_scam_markers": int(
                    _record_value(record, "n_scam_markers", 0) or 0
                ),
                "source_label": str(
                    _record_value(record, "source", "unknown")
                ),
            })
    except Exception:
        # Historical tip storage is optional; a live investigation must still run.
        pass

    # Ensure the current investigation itself is represented, without persisting
    # raw message text. The fingerprint is computed only in memory when needed.
    tip = current_result.get("tip") or {}
    tickers = tip.get("tickers") or []
    if not tickers:
        tickers = current_result.get("classification", {}).get("tickers") or []

    current_ticker = str(tickers[0] if tickers else "").upper().strip()
    if current_ticker:
        fingerprint_value = str(tip.get("fingerprint") or "")
        if not fingerprint_value:
            try:
                from src.tipcheck.privacy import fingerprint

                fingerprint_value = str(fingerprint(raw_text))
            except Exception:
                fingerprint_value = ""

        current_row = {
            "ticker": current_ticker,
            "ts": _as_of_timestamp(timestamp),
            "fingerprint": fingerprint_value,
            "n_scam_markers": int(tip.get("n_scam_markers") or 0),
            "source_label": str(source_label or "unknown"),
        }

        already_present = any(
            r.get("ticker") == current_row["ticker"]
            and r.get("fingerprint")
            and current_row["fingerprint"]
            and r.get("fingerprint") == current_row["fingerprint"]
            for r in rows
        )
        if not already_present:
            rows.append(current_row)

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

    return pd.DataFrame(rows)


def _stock_news_evidence(
    ticker: str,
    *,
    web_enabled: bool,
) -> dict[str, Any]:
    """Run Pulkit's Yahoo + Google News analyzer and normalize its output."""
    if not web_enabled:
        return {
            "status": "disabled",
            "provider": "Pulkit News analyzer",
            "query": ticker,
            "provider_status": {
                "yahoo": "disabled",
                "google": "disabled",
            },
            "yahoo_count": 0,
            "google_count": 0,
            "result_count": 0,
            "has_recent_news": False,
            "news_events": [],
            "articles": [],
            "observations": [],
            "llm_analysis": None,
            "error": None,
        }

    try:
        from src.evidence.news_analyzer import verify_news_for_ticker

        analyzed = verify_news_for_ticker(ticker)

        events = analyzed.get("news_events") or []
        provider_status = analyzed.get("provider_status") or {}

        observations: list[dict[str, Any]] = []

        yahoo_count = int(analyzed.get("yahoo_count") or 0)
        google_count = int(analyzed.get("google_count") or 0)
        result_count = len(events)

        if yahoo_count:
            observations.append({
                "signal": "news_yahoo_volume",
                "severity": "low",
                "text": (
                    f"Yahoo Finance RSS returned {yahoo_count} "
                    f"public news result(s) for {ticker}."
                ),
            })

        if google_count:
            observations.append({
                "signal": "news_google_volume",
                "severity": "low",
                "text": (
                    f"Google News RSS returned {google_count} "
                    f"public result(s) for {ticker}."
                ),
            })

        if result_count:
            observations.append({
                "signal": "news_context_available",
                "severity": "low",
                "text": (
                    f"{result_count} combined public news event(s) were "
                    f"available for {ticker}."
                ),
            })

        llm_analysis = analyzed.get("llm_analysis")

        if isinstance(llm_analysis, dict):
            explanation = str(llm_analysis.get("explanation") or "").strip()
            llm_status = str(llm_analysis.get("llm_status") or "").strip()
            if (explanation
                    and not explanation.startswith("[Mock LLM")
                    and not explanation.startswith("[LLM Unavailable]")
                    and llm_status != "unavailable"):
                observations.append({
                    "signal": "news_llm_context",
                    "severity": "low",
                    "text": explanation,
                })

        status = str(analyzed.get("status") or "unknown")
        error = analyzed.get("error")

        if status == "success":
            normalized_status = "connected"
        elif status in {"no_results", "empty"}:
            normalized_status = "no_results"
        else:
            normalized_status = status

        return {
            "status": normalized_status,
            "provider": "Pulkit News analyzer",
            "query": ticker,
            "provider_status": provider_status,
            "yahoo_count": yahoo_count,
            "google_count": google_count,
            "result_count": result_count,
            "has_recent_news": bool(analyzed.get("has_recent_news")),
            "news_events": events,
            "articles": events,
            "observations": observations,
            "llm_analysis": llm_analysis,
            "error": str(error) if error else None,
        }

    except Exception as exc:
        return {
            "status": "error",
            "provider": "Pulkit News analyzer",
            "query": ticker,
            "provider_status": {
                "yahoo": "error",
                "google": "unknown",
            },
            "yahoo_count": 0,
            "google_count": 0,
            "result_count": 0,
            "has_recent_news": False,
            "news_events": [],
            "articles": [],
            "observations": [],
            "llm_analysis": None,
            "error": str(exc),
        }


def _attach_stock_news_evidence(
    result: dict[str, Any],
    *,
    web_enabled: bool,
) -> dict[str, Any]:
    """Attach News while preserving the existing social/company evidence tree.

    The frontend reads the top-level ``evidence`` object for manual results.
    Older stock investigations may already keep the full evidence tree inside
    ``investigations[0].evidence``. In that case, promote that tree rather than
    replacing it with a News-only object.
    """
    investigations = result.get("investigations")
    first_investigation: dict[str, Any] | None = None

    if isinstance(investigations, list):
        for investigation in investigations:
            if isinstance(investigation, dict):
                first_investigation = investigation
                break

    # Preserve the canonical existing evidence tree when the stock investigator
    # already populated it inside the first investigation.
    top_evidence = result.get("evidence")
    if not isinstance(top_evidence, dict):
        top_evidence = {}

    if first_investigation is not None:
        nested_evidence = first_investigation.get("evidence")
        if isinstance(nested_evidence, dict):
            merged = dict(nested_evidence)
            merged.update(top_evidence)
            top_evidence = merged
            result["evidence"] = top_evidence

            # Keep the nested object aligned so detail views see the same data.
            first_investigation["evidence"] = top_evidence

    result["evidence"] = top_evidence

    ticker_candidates = (
        (result.get("classification") or {}).get("tickers")
        or []
    )
    fallback_ticker = str(
        result.get("ticker")
        or result.get("entity")
        or (ticker_candidates[0] if ticker_candidates else "")
        or (
            first_investigation.get("ticker", "")
            if first_investigation is not None
            else ""
        )
    ).upper().strip()

    if fallback_ticker:
        news = _stock_news_evidence(
            fallback_ticker,
            web_enabled=web_enabled,
        )
        top_evidence["news"] = news

        if first_investigation is not None:
            first_investigation["evidence"] = top_evidence

            source_status = first_investigation.get("source_status")
            if not isinstance(source_status, dict):
                source_status = {}
                first_investigation["source_status"] = source_status
            source_status["news"] = news["status"]

    result["evidence"] = top_evidence

    # Keep the top-level source_status compatible with the frontend when the
    # underlying stock investigator already supplied one.
    if first_investigation is not None:
        nested_status = first_investigation.get("source_status")
        if isinstance(nested_status, dict):
            top_status = result.get("source_status")
            if not isinstance(top_status, dict):
                top_status = {}
            merged_status = dict(nested_status)
            merged_status.update(top_status)
            result["source_status"] = merged_status

    return result


def _replace_stock_risk_with_real_engine(
    result: dict[str, Any],
    *,
    raw_text: str,
    source_label: str,
    timestamp: str | None,
) -> dict[str, Any]:
    """Replace the prototype evidence score with the real explainable risk engine.

    News/social evidence remains attached to the investigation as evidence. It is
    not allowed to directly change the five-group Dakota score unless the risk
    engine itself explicitly consumes it in a future version.
    """
    try:
        from src.engine.risk_engine import assess
    except Exception as exc:
        result["risk_engine_status"] = {
            "status": "unavailable",
            "error": str(exc),
        }
        return result

    tip_reports = _load_tip_reports(
        current_result=result,
        raw_text=raw_text,
        source_label=source_label,
        timestamp=timestamp,
    )
    as_of = _as_of_timestamp(timestamp)

    def score_one(ticker: str) -> dict[str, Any] | None:
        ticker = str(ticker or "").upper().strip()
        if not ticker:
            return None
        try:
            return assess(ticker, as_of=as_of, tip_reports=tip_reports)
        except Exception as exc:
            return {
                "ticker": ticker,
                "status": "error",
                "error": str(exc),
            }

    scored_tickers: list[str] = []

    investigations = result.get("investigations")
    if isinstance(investigations, list):
        for investigation in investigations:
            if not isinstance(investigation, dict):
                continue
            ticker = str(investigation.get("ticker") or "").upper().strip()
            if not ticker:
                continue
            scored = score_one(ticker)
            if scored is not None:
                legacy = investigation.get("risk")
                if isinstance(legacy, dict) and legacy.get("method"):
                    investigation.setdefault("legacy_evidence_risk", legacy)
                investigation["risk"] = scored
                scored_tickers.append(ticker)

    stock_verdicts = result.get("stock_verdicts")
    if isinstance(stock_verdicts, list) and stock_verdicts:
        rebuilt: list[dict[str, Any]] = []
        for verdict in stock_verdicts:
            if not isinstance(verdict, dict):
                continue
            ticker = str(verdict.get("ticker") or "").upper().strip()
            scored = score_one(ticker)
            rebuilt.append(scored if scored is not None else verdict)
            if scored is not None:
                scored_tickers.append(ticker)
        result["stock_verdicts"] = rebuilt

    if not scored_tickers:
        ticker = str(
            result.get("ticker")
            or result.get("entity")
            or ((result.get("classification") or {}).get("tickers") or [""])[0]
        ).upper().strip()
        scored = score_one(ticker)
        if scored is not None:
            legacy = result.get("risk")
            if isinstance(legacy, dict) and legacy.get("method"):
                result.setdefault("legacy_evidence_risk", legacy)
            result["risk"] = scored
            scored_tickers.append(ticker)

    result["risk_engine_status"] = {
        "status": "connected" if scored_tickers else "no_ticker",
        "tickers_scored": sorted(set(scored_tickers)),
        "as_of": as_of.isoformat(timespec="seconds"),
        "method": "src.engine.risk_engine.assess",
        "news_social_direct_score_input": False,
        "note": (
            "News and social remain evidence attached to the investigation. "
            "The final numeric score comes from the existing explainable "
            "five-group Dakota risk engine."
        ),
    }

    return result


def _attach_jev_assessment(
    result: dict[str, Any],
    *,
    raw_text: str,
    source_label: str,
    timestamp: str | None,
) -> dict[str, Any]:
    """Execute structured Simple JEV + Qwen sentiment divergence and factual analysis.

    Connects real market indicators, technical snapshots, news headlines, and risk scores
    with the official answer-token logit scoring adapter.
    """
    try:
        from src.intelligence.jev.api import get_active_adapter
        from src.intelligence.jev.tasks.sentiment import SentimentDivergenceTask
        from src.intelligence.jev.analysis_layer import EvidenceGroundedAnalyzer

        adapter = get_active_adapter()
        task = SentimentDivergenceTask()
        analyzer = EvidenceGroundedAnalyzer()

        # Resolve primary ticker or entity
        investigations = result.get("investigations") or []
        first_inv = investigations[0] if (investigations and isinstance(investigations[0], dict)) else {}

        ticker = (
            first_inv.get("ticker")
            or result.get("ticker")
            or result.get("entity")
            or ((result.get("classification") or {}).get("tickers") or [""])[0]
            or "MARKET"
        )
        ticker = str(ticker).upper().strip()

        # Extract market telemetry
        market = first_inv.get("market") or {}
        snapshot = market.get("snapshot") or {}
        risk = result.get("risk") or first_inv.get("risk") or {}

        # Extract news headlines
        news_obj = result.get("evidence", {}).get("news", {})
        raw_articles = news_obj.get("articles") or news_obj.get("news_events") or []
        headlines = []
        for art in raw_articles:
            if isinstance(art, dict):
                h = art.get("title") or art.get("headline")
                if h:
                    headlines.append(str(h).strip())
            elif isinstance(art, str):
                headlines.append(art.strip())

        technicals = {
            "trend_vs_ema20": snapshot.get("trend_vs_ema20", "flat"),
            "rsi": snapshot.get("rsi_14"),
            "volume_status": snapshot.get("volume_status", "normal"),
            "above_200dma": snapshot.get("above_200dma"),
        }

        # Build verified evidence IDs
        evidence_ids = [f"E_MKT_{ticker}"]
        if headlines:
            evidence_ids.append(f"E_NEWS_{ticker}")
        evidence_ids.append(f"E_SOC_{source_label.upper()}")

        sample_context = {
            "ticker": ticker,
            "as_of": timestamp or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "latest_price": snapshot.get("close"),
            "change_pct": snapshot.get("return_1d_pct"),
            "volume": snapshot.get("volume"),
            "delivery_pct": snapshot.get("delivery_pct"),
            "technicals": technicals,
            "risk_score": risk.get("score") if isinstance(risk, dict) else None,
            "risk_band": risk.get("band", "Unknown") if isinstance(risk, dict) else "Unknown",
            "is_surveillance": bool(isinstance(risk, dict) and (risk.get("band") == "High" or (risk.get("score") or 0) >= 70)),
            "news_headlines": headlines[:6],
            "social_signals": [raw_text],
            "evidence_ids": evidence_ids,
        }

        pred = task.classify(adapter, sample_context)
        report = analyzer.analyze(pred, sample_context)

        is_real = adapter.__class__.__name__ == "OfficialSimpleJEVAdapter"
        jev_payload = {
            "status": "completed",
            "is_real_model": is_real,
            "model_id": pred.model_id,
            "backend": "official_simple_jev_transformers" if is_real else "mock_adapter",
            "prediction": pred.model_dump(),
            "analysis": report.model_dump(),
        }
    except Exception as exc:
        jev_payload = {
            "status": "error",
            "error": str(exc),
            "is_real_model": False,
            "model_id": "unavailable",
            "prediction": None,
            "analysis": None,
        }

    result["jev"] = jev_payload
    if first_inv:
        first_inv["jev"] = jev_payload
    return result


def investigate_message(
    raw_text: str,
    classification: dict[str, Any],
    *,
    data_root: str = "data/raw",
    source_label: str = "telegram",
    timestamp: str | None = None,
) -> dict[str, Any]:
    impact = map_impact(raw_text, classification)

    if impact["status"] == "investigate_stock":
        result = investigate_tip(
            raw_text,
            data_root=data_root,
            source_label=source_label,
        )
        result["classification"] = classification
        result["impact"] = impact
        result["investigation_mode"] = "stock"
        result["investigated_at"] = datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        )
        result["source"] = source_label
        result["timestamp"] = timestamp

        web_enabled = os.getenv(
            "DAKOTA_WEB_EVIDENCE",
            "1",
        ).strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }

        result = _attach_stock_news_evidence(
            result,
            web_enabled=web_enabled,
        )

        result = _replace_stock_risk_with_real_engine(
            result,
            raw_text=raw_text,
            source_label=source_label,
            timestamp=timestamp,
        )

        # The website/backend also expects a simple top-level risk object for
        # the common single-stock investigation case. The canonical score is
        # still the exact object produced by risk_engine.assess().
        if not isinstance(result.get("risk"), dict):
            investigations = result.get("investigations")
            if isinstance(investigations, list):
                for investigation in investigations:
                    if not isinstance(investigation, dict):
                        continue
                    investigation_risk = investigation.get("risk")
                    if isinstance(investigation_risk, dict):
                        result["risk"] = investigation_risk
                        break

        if not isinstance(result.get("risk"), dict):
            stock_verdicts = result.get("stock_verdicts")
            if isinstance(stock_verdicts, list):
                for verdict in stock_verdicts:
                    if not isinstance(verdict, dict):
                        continue
                    if isinstance(verdict.get("risk"), dict):
                        result["risk"] = verdict["risk"]
                        break

        result = _attach_jev_assessment(
            result,
            raw_text=raw_text,
            source_label=source_label,
            timestamp=timestamp,
        )

        if not result.get("investigation_id"):
            result["investigation_id"] = f"inv-{int(datetime.now(timezone.utc).timestamp())}-{uuid.uuid4().hex[:6]}"

        try:
            from src.intake.live_store import save_live_investigation
            save_live_investigation(result)
        except Exception:
            pass

        return result

    if impact["status"] == "classified_non_financial":
        res = {
            "status": "classified_non_financial",
            "investigation_id": f"inv-{int(datetime.now(timezone.utc).timestamp())}-{uuid.uuid4().hex[:6]}",
            "source": source_label,
            "timestamp": timestamp,
            "classification": classification,
            "impact": impact,
            "investigation_mode": "none",
            "investigated_at": datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            ),
            "risk": None,
            "evidence": {},
        }
        try:
            from src.intake.live_store import save_live_investigation
            save_live_investigation(res)
        except Exception:
            pass
        return res

    if impact["status"] == "needs_entity_resolution":
        res = {
            "status": "needs_entity_resolution",
            "investigation_id": f"inv-{int(datetime.now(timezone.utc).timestamp())}-{uuid.uuid4().hex[:6]}",
            "source": source_label,
            "timestamp": timestamp,
            "classification": classification,
            "impact": impact,
            "investigation_mode": "unresolved",
            "investigated_at": datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            ),
            "risk": None,
            "evidence": {},
        }
        try:
            from src.intake.live_store import save_live_investigation
            save_live_investigation(res)
        except Exception:
            pass
        return res

    entity = str(impact.get("entity") or "").strip()
    label = _label(entity)
    web_enabled = os.getenv(
        "DAKOTA_WEB_EVIDENCE",
        "1",
    ).strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }

    if web_enabled:
        news = search_news(label)
        social = collect_social_evidence(label)
    else:
        news = {
            "status": "disabled",
            "query": label,
            "articles": [],
            "observations": [],
            "error": None,
        }
        social = {"status": "disabled"}

    tip_observations = _market_topic_observations(impact)
    news_observations = news.get("observations") or []
    social_observations = _flatten_social(social)

    risk = aggregate_scores(
        tip_observations=tip_observations,
        market_observations=[],
        news_observations=news_observations,
        social_observations=social_observations,
    )

    coverage = {
        "market": "not_applicable_topic",
        "news": str(news.get("status") or "unknown"),
        "reddit": str(
            (social.get("reddit") or {}).get("status") or "unknown"
        ),
        "x": str(
            (social.get("x") or {}).get("status") or "unknown"
        ),
        "instagram": str(
            (social.get("instagram") or {}).get("status") or "unknown"
        ),
        "stocktwits": str(
            (social.get("stocktwits") or {}).get("status") or "unknown"
        ),
        "telegram": "ingestion_source",
    }

    topic_result = {
        "status": "ok",
        "investigation_id": f"inv-{int(datetime.now(timezone.utc).timestamp())}-{uuid.uuid4().hex[:6]}",
        "source": source_label,
        "timestamp": timestamp,
        "classification": classification,
        "impact": impact,
        "investigation_mode": "market_topic",
        "investigated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ),
        "entity": entity,
        "risk": risk,
        "evidence": {
            "news": news,
            "social": social,
            "impact_areas": impact.get(
                "potentially_affected_areas",
                [],
            ),
        },
        "source_status": coverage,
        "next_steps": [
            "Map the resolved topic to concrete affected listed securities.",
            "Check whether the message is repeated across channels or sources.",
            "Collect point-in-time market evidence for the affected securities before increasing confidence.",
        ],
        "disclaimer": (
            "Dakota reports risk indicators from available evidence. "
            "It does not determine fraud and does not provide buy/sell advice."
        ),
    }

    topic_result = _attach_jev_assessment(
        topic_result,
        raw_text=raw_text,
        source_label=source_label,
        timestamp=timestamp,
    )

    try:
        from src.intake.live_store import save_live_investigation
        save_live_investigation(topic_result)
    except Exception:
        pass

    return topic_result
