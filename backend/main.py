"""Dakota FastAPI backend — real-data investigation build.

Core flow:
    tip -> parser -> NSE/BSE -> indicators -> news -> social -> company -> index
         -> coordination -> explainable available-evidence score

External integrations are credential-gated. Missing credentials are surfaced as
coverage gaps and are never treated as clean evidence.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import date
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

import pandas as pd
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from src.connectors.config import public_status
from src.connectors.telegram import extract_tip_update, send_message, set_webhook
from src.connectors.whatsapp import extract_messages, send_text, verify_signature, verify_webhook
from src.investigation.tip_investigator import investigate_tip
from src.investigation.universal_investigator import investigate_message
from src.classification.local_classifier import classify_message
from src.intake.live_store import load_live_investigations, get_live_investigation
from src.market.exchange_sync import sync_date
from src.market.exchange_sync import latest_weekday
from src.engine.risk_engine import assess
from src.tipcheck.parser import check_tip

BASE_DIR = Path(__file__).resolve().parents[1]
PORTFOLIO_FILE = BASE_DIR / "data" / "portfolio.json"
UNIVERSE_FILE = BASE_DIR / "config" / "universe.csv"
RAW_DATA_ROOT = BASE_DIR / "data" / "raw"

from contextlib import asynccontextmanager

_bg_monitor_task: asyncio.Task | None = None


async def _background_risk_monitor_loop() -> None:
    logger.info("Dakota background live risk monitor loop initialized.")
    while True:
        try:
            await asyncio.sleep(20)
            if _ACTIVE_MONITORED_TICKERS:
                from src.ingest.market_data import is_indian_market_open
                is_open, _, _ = is_indian_market_open()
                for sym in list(_ACTIVE_MONITORED_TICKERS)[:15]:
                    try:
                        from src.market.universe_manager import get_or_assess_stock
                        ttl = 60 if is_open else 900
                        await asyncio.to_thread(get_or_assess_stock, sym, False, ttl)
                    except Exception as err:
                        logger.debug("Background assessment tick error for %s: %s", sym, err)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.debug("Background monitor loop tick exception: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _bg_monitor_task
    try:
        from src.market.universe_manager import _ensure_schema
        _ensure_schema()
    except Exception as exc:
        logger.warning("Could not pre-init database schema: %s", exc)
    _bg_monitor_task = asyncio.create_task(_background_risk_monitor_loop())
    try:
        yield
    finally:
        if _bg_monitor_task and not _bg_monitor_task.done():
            _bg_monitor_task.cancel()
            try:
                await _bg_monitor_task
            except asyncio.CancelledError:
                pass


app = FastAPI(title="Dakota API", version="0.4.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TipRequest(BaseModel):
    tip: str = Field(min_length=1, max_length=12000)
    source: str = Field(default="manual", max_length=64)


class HoldingRequest(BaseModel):
    exchange: str = Field(default="NSE", min_length=2, max_length=10)
    ticker: str = Field(min_length=1, max_length=30)
    bse_code: str | None = None
    quantity: float = Field(gt=0)
    average_buy_price: float | None = None
    avg_buy_price: float | None = None
    averagePrice: float | None = None


class TelegramWebhookRequest(BaseModel):
    update_id: int | None = None
    message: dict[str, Any] | None = None
    edited_message: dict[str, Any] | None = None
    channel_post: dict[str, Any] | None = None
    edited_channel_post: dict[str, Any] | None = None
    business_message: dict[str, Any] | None = None


def _load_universe_rows() -> list[dict[str, Any]]:
    if not UNIVERSE_FILE.exists():
        return []
    import pandas as pd

    df = pd.read_csv(UNIVERSE_FILE)
    return df.fillna("").to_dict(orient="records")


def _load_portfolio() -> list[dict[str, Any]]:
    if not PORTFOLIO_FILE.exists():
        return []
    try:
        data = json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            return data.get("holdings", [])
        return []
    except (OSError, json.JSONDecodeError):
        return []


def _save_portfolio(items: list[dict[str, Any]]) -> None:
    PORTFOLIO_FILE.parent.mkdir(parents=True, exist_ok=True)
    PORTFOLIO_FILE.write_text(json.dumps(items, indent=2), encoding="utf-8")


def _holding_value(item: dict[str, Any]) -> float:
    qty = float(item.get("quantity", 0) or 0)
    p = item.get("average_buy_price")
    if p is None:
        p = item.get("avg_buy_price", item.get("averagePrice", 0))
    return round(qty * float(p or 0), 2)


def _telegram_secret_valid(header: str | None) -> bool:
    expected = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    if not expected:
        return True
    return header == expected


def _telegram_reply(result: dict[str, Any]) -> str:
    investigations = result.get("investigations") or []
    if not investigations:
        return str(result.get("message") or "Dakota could not identify a stock ticker in the tip.")

    parts: list[str] = ["DAKOTA INVESTIGATION"]
    for item in investigations[:3]:
        ticker = item.get("ticker", "?")
        risk = item.get("risk") or {}
        score = risk.get("score", "—")
        band = risk.get("band", "Unknown")
        parts.append(f"{ticker}: {score}/100 — {band}")

        reasons = risk.get("reasons") or []
        for reason in reasons[:3]:
            parts.append(f"• {reason}")

    parts.append("Risk indicators only. Not a fraud determination or buy/sell advice.")
    return "\n".join(parts)


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "Dakota API", "status": "ok", "version": "0.4.0"}


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "raw_data_root_exists": RAW_DATA_ROOT.exists(),
        "universe_exists": UNIVERSE_FILE.exists(),
        "connectors": public_status(),
    }


@app.get("/api/connectors/status")
def connector_status() -> dict[str, Any]:
    return {
        "status": "ok",
        "connectors": public_status(),
        "notes": {
            "nse_bse": "Uses cached exchange reports; run /api/market/sync or scripts/sync_market.py to refresh.",
            "telegram": "Authorized bot ingestion only.",
            "whatsapp": "WhatsApp Cloud API webhook only.",
            "reddit": "Official OAuth when credentials exist; RSS fallback otherwise.",
        },
    }


@app.post("/api/market/sync")
def market_sync(trade_date: str | None = None) -> dict[str, Any]:
    try:
        selected = date.fromisoformat(trade_date) if trade_date else latest_weekday()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="trade_date must be YYYY-MM-DD") from exc

    try:
        return sync_date(selected)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/stock/risk")
def stock_risk(payload: dict[str, Any]) -> dict[str, Any]:
    ticker = str(payload.get("ticker", "")).upper().strip()
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker is required")
    try:
        return assess(ticker)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/tip/check")
def tip_check(request: TipRequest) -> dict[str, Any]:
    import dataclasses as _dc
    try:
        result = check_tip(request.tip)
        result["source"] = request.source
        # Convert ParsedTip dataclass -> dict for JSON serialization
        if "parsed" in result and _dc.is_dataclass(result["parsed"]) and not isinstance(result["parsed"], type):
            result["parsed"] = _dc.asdict(result["parsed"])
        # Convert tip_reports DataFrame -> list of records
        if "tip_reports" in result and hasattr(result["tip_reports"], "to_dict"):
            result["tip_reports"] = result["tip_reports"].to_dict(orient="records")
        # Convert any stock_verdict ParsedTip objects
        if "stock_verdicts" in result:
            for v in result["stock_verdicts"]:
                if isinstance(v, dict) and "parsed" in v and _dc.is_dataclass(v.get("parsed")):
                    v["parsed"] = _dc.asdict(v["parsed"])
        # --- SCAM MARKER SCORE BOOST ---
        # Enforce minimum score based on scam markers detected in tip
        if "parsed" in result and isinstance(result["parsed"], dict):
            _markers = result["parsed"].get("n_scam_markers", 0) or 0
            for _v in result.get("stock_verdicts", []):
                _cur = float(_v.get("score", 0) or 0)
                if _markers >= 4:
                    _v["score"] = max(_cur, 75.0)
                    _v["band"] = "High"
                    _v["verdict"] = "HIGH RISK: Strong scam indicators in tip"
                    _reasons = _v.get("reasons", [])
                    _boost_msg = f"Blatant scam language detected ({int(_markers)} markers: guaranteed returns, VIP funnel, urgency)"
                    if _boost_msg not in _reasons:
                        _v["reasons"] = [_boost_msg] + _reasons
                elif _markers >= 2:
                    _v["score"] = max(_cur, 45.0)
                    _v["band"] = "Elevated"
                    _v["verdict"] = "ELEVATED RISK: Suspicious tip language detected"
                    _reasons = _v.get("reasons", [])
                    _boost_msg = f"Suspicious tip patterns ({int(_markers)} markers)"
                    if _boost_msg not in _reasons:
                        _v["reasons"] = [_boost_msg] + _reasons
        # Attach market snapshot to each verdict
        try:
            from src.market.indicators import latest_indicator_snapshot
            from src.market.history import load_history
            if "stock_verdicts" in result:
                for v in result["stock_verdicts"]:
                    ticker = v.get("ticker", "")
                    try:
                        hist = load_history(ticker)
                        if hist is not None and not hist.empty:
                            snap = latest_indicator_snapshot(hist)
                            if snap:
                                v["market"] = {
                                    "rsi": round(snap.get("rsi", 0), 1) if snap.get("rsi") else None,
                                    "vol_ratio": round(snap.get("vol_ratio", 1), 2) if snap.get("vol_ratio") else None,
                                    "trend": snap.get("trend", "unknown"),
                                    "above_200dma": snap.get("above_200dma", None),
                                    "chart": hist.tail(30)[["date", "close"]].rename(columns={"date": "date", "close": "close"}).to_dict(orient="records") if "date" in hist.columns and "close" in hist.columns else [],
                                }
                    except Exception:
                        pass
        except ImportError:
            pass
        return result
    except Exception as exc:
        import traceback
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}") from exc


@app.post("/api/investigate")
def investigate(request: TipRequest) -> dict[str, Any]:
    try:
        classification = classify_message(request.tip)
        return investigate_message(
            request.tip,
            classification,
            data_root=str(RAW_DATA_ROOT),
            source_label=request.source,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/investigations/live")
def live_investigations(limit: int = 50) -> dict[str, Any]:
    items = load_live_investigations(limit=limit)
    return {
        "status": "ok",
        "count": len(items),
        "items": items,
        "disclaimer": "Dakota reports risk indicators from available evidence. It does not determine fraud and does not provide buy/sell advice.",
    }


@app.get("/api/investigations/live/{investigation_id}")
def live_investigation_detail(investigation_id: str) -> dict[str, Any]:
    item = get_live_investigation(investigation_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return item


@app.get("/api/campaigns")
def campaigns_overview(limit: int = 200) -> dict[str, Any]:
    """Aggregate live investigations into channel/actor campaign cards.
    
    Collapses repeated individual source findings into single actor pattern cards:
    channel name, total tips, entities touched, first-seen/last-seen window, 
    and distinct-text vs copy-paste duplicate ratio.
    """
    from collections import defaultdict
    items = load_live_investigations(limit=limit)

    channel_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        src = (
            item.get("channel_username")
            or item.get("investigation", {}).get("source")
            or item.get("channel")
            or "unknown_source"
        )
        channel_groups[src].append(item)

    channels_data: list[dict[str, Any]] = []
    total_tips_count = 0

    for ch_key, tips in channel_groups.items():
        if not tips:
            continue
        total_tips_count += len(tips)

        entities_set = set()
        for t in tips:
            ticker = t.get("ticker")
            if ticker:
                entities_set.add(ticker.upper())
            tickers = t.get("tickers") or []
            for tk in tickers:
                if tk:
                    entities_set.add(tk.upper())
            entity = t.get("impact", {}).get("entity")
            if entity:
                entities_set.add(entity.upper())

        entities_touched = sorted(list(entities_set))

        ts_list = [
            t.get("telegram_timestamp") or t.get("captured_at") or t.get("stored_at")
            for t in tips
            if t.get("telegram_timestamp") or t.get("captured_at") or t.get("stored_at")
        ]
        first_seen = min(ts_list) if ts_list else None
        last_seen = max(ts_list) if ts_list else None

        fps = [t.get("fingerprint") for t in tips if t.get("fingerprint")]
        distinct_fps_count = len(set(fps)) if fps else len(tips)
        copy_paste_count = len(fps) - distinct_fps_count if fps else 0
        copy_paste_pct = round((copy_paste_count / len(tips)) * 100, 1) if tips else 0.0

        total_scam_markers = sum(int(t.get("n_scam_markers", 0) or 0) for t in tips)
        urgency_count = sum(1 for t in tips if t.get("urgency"))

        sample = tips[0]
        channel_title = sample.get("channel") or ch_key
        channel_username = sample.get("channel_username") or (ch_key if ch_key.startswith("@") else None)

        formatted_tips = []
        for t in tips:
            formatted_tips.append({
                "investigation_id": t.get("investigation_id"),
                "ticker": t.get("ticker") or (t.get("tickers")[0] if t.get("tickers") else None) or t.get("impact", {}).get("entity"),
                "timestamp": t.get("telegram_timestamp") or t.get("captured_at") or t.get("stored_at"),
                "fingerprint": t.get("fingerprint"),
                "message_type": t.get("classification", {}).get("message_type") or t.get("classification", {}).get("type"),
                "urgency": bool(t.get("urgency")),
                "n_scam_markers": int(t.get("n_scam_markers", 0) or 0),
                "risk": t.get("risk"),
            })

        channels_data.append({
            "channel_id": ch_key,
            "channel_name": ch_key,
            "channel_title": channel_title,
            "channel_username": channel_username,
            "platform": "telegram" if "telegram" in ch_key.lower() or str(ch_key).startswith("@") else "intake",
            "total_tips": len(tips),
            "entities_touched": entities_touched,
            "entities_count": len(entities_touched),
            "first_seen": first_seen,
            "last_seen": last_seen,
            "distinct_text_count": distinct_fps_count,
            "copy_paste_count": copy_paste_count,
            "copy_paste_percentage": copy_paste_pct,
            "distinct_ratio_str": f"{distinct_fps_count} distinct / {len(tips)} tips",
            "scam_markers_total": total_scam_markers,
            "urgency_tips_count": urgency_count,
            "tips": formatted_tips,
        })

    channels_data.sort(key=lambda x: x["total_tips"], reverse=True)
    most_active = channels_data[0]["channel_name"] if channels_data else None

    return {
        "status": "ok",
        "total_campaign_channels": len(channels_data),
        "total_tips_analyzed": total_tips_count,
        "most_active_channel": most_active,
        "channels": channels_data,
    }


@app.post("/api/connectors/telegram/set-webhook")
def telegram_set_webhook(webhook_url: str) -> dict[str, Any]:
    try:
        return set_webhook(webhook_url)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/connectors/telegram/webhook")
async def telegram_webhook(
    payload: TelegramWebhookRequest,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, Any]:
    if not _telegram_secret_valid(x_telegram_bot_api_secret_token):
        raise HTTPException(status_code=401, detail="invalid Telegram webhook secret")

    update = payload.model_dump(exclude_none=True)
    incoming = extract_tip_update(update)
    if not incoming:
        return {"status": "ignored", "reason": "no text message"}

    result = investigate_tip(
        incoming["tip"],
        data_root=RAW_DATA_ROOT,
        source_label="telegram_bot",
    )

    chat_id = incoming.get("chat_id")
    reply = _telegram_reply(result)
    if chat_id is not None:
        try:
            send_message(chat_id, reply)
        except Exception as exc:
            return {"status": "investigated_reply_failed", "error": str(exc), "investigation": result}

    return {"status": "investigated", "investigation": result}


@app.get("/api/connectors/whatsapp/webhook", response_class=PlainTextResponse)
def whatsapp_verify(
    hub_mode: str | None = None,
    hub_verify_token: str | None = None,
    hub_challenge: str | None = None,
) -> PlainTextResponse:
    challenge = verify_webhook(
        hub_mode or "",
        hub_verify_token or "",
        hub_challenge or "",
    )
    if challenge is None:
        raise HTTPException(status_code=403, detail="WhatsApp verification failed")
    return PlainTextResponse(challenge)


@app.post("/api/connectors/whatsapp/webhook")
async def whatsapp_webhook(request: Request) -> dict[str, Any]:
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    if not verify_signature(raw_body, signature):
        raise HTTPException(status_code=401, detail="invalid WhatsApp signature")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="invalid JSON") from exc

    messages = extract_messages(payload)
    responses: list[dict[str, Any]] = []
    for item in messages:
        result = investigate_tip(
            item["tip"],
            data_root=RAW_DATA_ROOT,
            source_label="whatsapp_cloud",
        )
        sender = item.get("sender")
        send_result: dict[str, Any] = {"status": "not_sent"}
        if sender:
            try:
                send_result = send_text(sender, _telegram_reply(result))
            except Exception as exc:
                send_result = {"status": "send_error", "error": str(exc)}
        responses.append({"sender": sender, "investigation": result, "reply": send_result})

    return {"status": "received", "messages": len(messages), "responses": responses}


@app.get("/api/market/{exchange}/{ticker}/analysis")
def market_analysis(exchange: str, ticker: str) -> dict[str, Any]:
    from src.market.history import load_history
    from src.market.indicators import add_indicators, latest_indicator_snapshot, market_signal_reasons
    from src.investigation.tip_investigator import _series_for_chart

    history = load_history(ticker.upper(), exchange.upper(), data_root=RAW_DATA_ROOT)
    if history.empty:
        raise HTTPException(status_code=404, detail="No local market history found for this ticker/exchange")

    enriched = add_indicators(history)
    snapshot = latest_indicator_snapshot(enriched)
    observations = market_signal_reasons(snapshot)
    return {
        "ticker": ticker.upper(),
        "exchange": exchange.upper(),
        "data_points": int(len(enriched)),
        "first_date": enriched["date"].min().strftime("%Y-%m-%d"),
        "last_date": enriched["date"].max().strftime("%Y-%m-%d"),
        "snapshot": snapshot,
        "observations": observations,
        "chart": _series_for_chart(enriched),
        "disclaimer": "Market observations are indicators, not a fraud determination or trading advice.",
    }


@app.get("/api/stocks")
def stocks(
    search: str = "",
    segment: str = "",
    band: str = "",
    page: int = 1,
    limit: int = 50,
    sort: str = "score_desc",
) -> dict[str, Any]:
    from src.market.universe_manager import query_stocks
    return query_stocks(search=search, segment=segment, band=band, page=page, limit=limit, sort_by=sort)


_ACTIVE_MONITORED_TICKERS: set[str] = set()


@app.get("/api/stocks/{ticker}")
def stock_detail(
    ticker: str,
    force_refresh: bool = False,
    max_age_seconds: int | None = None,
) -> dict[str, Any]:
    ticker_clean = ticker.upper().strip()
    _ACTIVE_MONITORED_TICKERS.add(ticker_clean)

    from src.market.universe_manager import get_or_assess_stock
    data = get_or_assess_stock(
        ticker_clean,
        force_refresh=force_refresh,
        max_age_seconds=max_age_seconds,
    )
    meta = {
        "name": data.get("name", ""),
        "exchange": data.get("exchange", "NSE"),
        "segment": data.get("segment", "main"),
        "role": data.get("role", "control"),
    }
    from src.engine.risk_engine import WEIGHTS, GROUP_LABELS

    contributions = data.get("contributions", {})
    reasons = data.get("reasons", [])

    # If contributions or score not in DB dict, assess once
    if not contributions or data.get("score") is None:
        try:
            from src.engine.risk_engine import assess
            assessed = assess(ticker_clean)
            contributions = assessed.get("contributions", {})
            reasons = assessed.get("reasons", reasons)
            if data.get("score") is None:
                data["score"] = assessed.get("score")
                data["band"] = assessed.get("band", "Unavailable")
                data["verdict"] = assessed.get("verdict", "")
        except Exception:
            contributions = {}

    risk = {
        "score": data.get("score"),
        "band": data.get("band", "Unavailable"),
        "verdict": data.get("verdict", ""),
        "reasons": reasons,
        "contributions": contributions,
        "contribution_labels": GROUP_LABELS,
        "weights": WEIGHTS,
        "calculated_at": data.get("calculated_at"),
        "market_data_as_of": data.get("market_data_as_of"),
        "data_freshness": data.get("data_freshness", "cached"),
        "previous_score": data.get("previous_score"),
        "score_change": data.get("score_change", 0.0),
        "change_reason": data.get("change_reason", ""),
    }

    decision = None
    try:
        from src.market.decision_engine import evaluate_investment_stance
        decision = evaluate_investment_stance(ticker_clean, risk_data=risk)
    except Exception:
        pass

    return {
        "ticker": ticker_clean,
        "meta": meta,
        "risk": risk,
        "decision": decision,
        **data,
    }


@app.get("/api/stocks/{ticker}/risk")
def stock_risk_status(
    ticker: str,
    force_refresh: bool = False,
    max_age_seconds: int | None = None,
) -> dict[str, Any]:
    """Dedicated lightweight endpoint for frontend live risk auto-polling."""
    ticker_clean = ticker.upper().strip()
    _ACTIVE_MONITORED_TICKERS.add(ticker_clean)

    from src.market.universe_manager import get_or_assess_stock
    data = get_or_assess_stock(
        ticker_clean,
        force_refresh=force_refresh,
        max_age_seconds=max_age_seconds,
    )
    if data.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"Stock {ticker_clean} not found")

    from src.engine.risk_engine import WEIGHTS, GROUP_LABELS

    contributions = data.get("contributions", {})
    reasons = data.get("reasons", [])

    if not contributions:
        try:
            from src.engine.risk_engine import assess
            assessed = assess(ticker_clean)
            contributions = assessed.get("contributions", {})
            reasons = assessed.get("reasons", reasons)
        except Exception:
            contributions = {}

    return {
        "ticker": ticker_clean,
        "score": data.get("score"),
        "band": data.get("band", "Unavailable"),
        "verdict": data.get("verdict", ""),
        "reasons": reasons,
        "contributions": contributions,
        "contribution_labels": GROUP_LABELS,
        "weights": WEIGHTS,
        "calculated_at": data.get("calculated_at"),
        "market_data_as_of": data.get("market_data_as_of"),
        "data_freshness": data.get("data_freshness", "cached"),
        "previous_score": data.get("previous_score"),
        "score_change": data.get("score_change", 0.0),
        "change_reason": data.get("change_reason", ""),
        "status": data.get("status", "completed"),
    }


@app.get("/api/stocks/{ticker}/risk/history")
def stock_risk_history_endpoint(ticker: str, limit: int = 20) -> dict[str, Any]:
    """Retrieve historical risk assessments and score change timeline."""
    ticker_clean = ticker.upper().strip()
    from src.market.universe_manager import get_stock_risk_history
    history = get_stock_risk_history(ticker_clean, limit=limit)
    return {
        "ticker": ticker_clean,
        "count": len(history),
        "history": history,
    }


@app.get("/api/stocks/{ticker}/decision")
def stock_decision(ticker: str) -> dict[str, Any]:
    ticker = ticker.upper().strip()
    try:
        from src.market.decision_engine import evaluate_investment_stance
        return evaluate_investment_stance(ticker)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/stocks/sync-batch")
def sync_stock_batch(limit: int = 10) -> dict[str, Any]:
    from src.market.universe_manager import sync_pending_batch, query_stocks
    updated = sync_pending_batch(batch_size=limit)
    stats = query_stocks(limit=1)
    return {
        "updated": updated,
        "global_total": stats.get("global_total", 0),
        "global_assessed": stats.get("global_assessed", 0),
    }


@app.get("/api/stocks/{ticker}/chart")
def stock_chart(ticker: str, period: str = "3m", interval: str = "5m") -> dict[str, Any]:
    ticker = ticker.upper().strip()
    is_intraday = period.lower() in ("1d", "today", "live")

    if is_intraday:
        try:
            from src.ingest.market_data import load_intraday_ohlcv, load_ohlcv
            df, meta = load_intraday_ohlcv(ticker, interval=interval, allow_synthetic=True)
            if df is not None and not df.empty:
                df = df.sort_values("datetime").reset_index(drop=True)
                # Compute indicator overlays for intraday chart
                df["ema_20"] = df["close"].ewm(span=20, adjust=False).mean()
                df["sma_50"] = df["close"].rolling(50, min_periods=1).mean()
                df["sma_200"] = df["close"].rolling(200, min_periods=1).mean()

                # Bollinger Bands (20, 2)
                df["bb_mid"] = df["close"].rolling(20, min_periods=1).mean()
                bb_std = df["close"].rolling(20, min_periods=1).std(ddof=0)
                df["bb_upper"] = df["bb_mid"] + 2 * bb_std
                df["bb_lower"] = df["bb_mid"] - 2 * bb_std

                # Supertrend (10, 3)
                from src.market.technical_analyzer import compute_supertrend
                st_vals, st_dirs = compute_supertrend(df, length=10, mult=3.0)
                df["supertrend"] = st_vals
                df["supertrend_dir"] = st_dirs

                points = []
                for _, row in df.iterrows():
                    time_str = str(row.get("date", ""))
                    c = round(float(row["close"]), 2) if row.get("close") is not None else 0.0
                    o = round(float(row.get("open", c)), 2)
                    h = round(float(row.get("high", c)), 2)
                    l = round(float(row.get("low", c)), 2)
                    v = int(row.get("volume", 0)) if row.get("volume") is not None else 0
                    ema20_val = round(float(row["ema_20"]), 2) if pd.notna(row.get("ema_20")) else None
                    sma50_val = round(float(row["sma_50"]), 2) if pd.notna(row.get("sma_50")) else None
                    sma200_val = round(float(row["sma_200"]), 2) if pd.notna(row.get("sma_200")) else None
                    bb_up_val = round(float(row["bb_upper"]), 2) if pd.notna(row.get("bb_upper")) else None
                    bb_mid_val = round(float(row["bb_mid"]), 2) if pd.notna(row.get("bb_mid")) else None
                    bb_low_val = round(float(row["bb_lower"]), 2) if pd.notna(row.get("bb_lower")) else None
                    st_val = round(float(row["supertrend"]), 2) if pd.notna(row.get("supertrend")) else None
                    st_dir = int(row["supertrend_dir"]) if pd.notna(row.get("supertrend_dir")) else 1

                    points.append({
                        "date": time_str,
                        "timestamp": str(row.get("timestamp", "")),
                        "close": c,
                        "open": o,
                        "high": h,
                        "low": l,
                        "volume": v,
                        "is_up": c >= o,
                        "ema_20": ema20_val,
                        "sma_50": sma50_val,
                        "sma_200": sma200_val,
                        "bb_upper": bb_up_val,
                        "bb_mid": bb_mid_val,
                        "bb_lower": bb_low_val,
                        "supertrend": st_val,
                        "supertrend_dir": st_dir,
                        "supertrend_bull": st_val if st_dir == 1 else None,
                        "supertrend_bear": st_val if st_dir == -1 else None,
                    })

                latest = points[-1] if points else None
                first_pt = points[0] if points else None
                prev_close = meta.get("previous_close")
                if not prev_close or prev_close <= 0:
                    prev_close = first_pt["open"] if first_pt else (latest["close"] if latest else 1.0)

                change = round(latest["close"] - prev_close, 2) if latest else 0.0
                change_pct = round((change / prev_close) * 100, 2) if prev_close else 0.0

                day_high = round(float(meta.get("day_high") or df["high"].max()), 2) if not df.empty else None
                day_low = round(float(meta.get("day_low") or df["low"].min()), 2) if not df.empty else None
                day_vol = int(meta.get("day_volume") or df["volume"].sum()) if not df.empty else 0
                day_open = round(float(meta.get("day_open") or (first_pt["open"] if first_pt else 0)), 2) if first_pt else None

                high_52w, low_52w, avg_vol = None, None, 0
                try:
                    daily_df = load_ohlcv(ticker, start="2023-01-01")
                    if daily_df is not None and not daily_df.empty:
                        year_df = daily_df.tail(252)
                        high_52w = round(float(year_df["high"].max()), 2) if "high" in year_df else None
                        low_52w = round(float(year_df["low"].min()), 2) if "low" in year_df else None
                        avg_vol = int(year_df["volume"].mean()) if "volume" in year_df else 0
                except Exception:
                    pass

                overlays_latest = {
                    "ema_20": latest.get("ema_20") if latest else None,
                    "sma_50": latest.get("sma_50") if latest else None,
                    "sma_200": latest.get("sma_200") if latest else None,
                    "bb_upper": latest.get("bb_upper") if latest else None,
                    "bb_mid": latest.get("bb_mid") if latest else None,
                    "bb_lower": latest.get("bb_lower") if latest else None,
                    "supertrend": latest.get("supertrend") if latest else None,
                    "supertrend_dir": latest.get("supertrend_dir") if latest else 1,
                }

                return {
                    "ticker": ticker,
                    "period": "1d",
                    "interval": interval,
                    "is_intraday": True,
                    "is_market_open": meta.get("is_market_open", False),
                    "session_status": meta.get("session_status", ""),
                    "market_time_ist": meta.get("market_time_ist", ""),
                    "last_traded_at": meta.get("last_traded_at", "Oct 09, 2026 at 03:30 PM IST"),
                    "session_date": meta.get("session_date", "Friday, Oct 09, 2026"),
                    "latest_price": latest["close"] if latest else None,
                    "prev_close": round(prev_close, 2) if prev_close else None,
                    "day_open": day_open,
                    "day_high": day_high,
                    "day_low": day_low,
                    "day_volume": day_vol,
                    "change": change,
                    "change_pct": change_pct,
                    "high_52w": high_52w,
                    "low_52w": low_52w,
                    "avg_volume": avg_vol,
                    "overlays_latest": overlays_latest,
                    "points": points,
                }
        except Exception as exc:
            logger.error("Error generating intraday chart for %s: %s", ticker, exc)

    try:
        from src.ingest.market_data import load_ohlcv
        df = load_ohlcv(ticker, start="2023-01-01")
        if df is None or df.empty:
            return {
                "ticker": ticker,
                "points": [],
                "latest_price": None,
                "change": 0.0,
                "change_pct": 0.0,
                "high_52w": None,
                "low_52w": None,
                "volume": 0,
            }

        df = df.sort_values("date").reset_index(drop=True)
        # Compute indicator overlays for chart on full history
        df["ema_20"] = df["close"].ewm(span=20, adjust=False).mean()
        df["sma_50"] = df["close"].rolling(50, min_periods=1).mean()
        df["sma_200"] = df["close"].rolling(200, min_periods=1).mean()

        # Bollinger Bands (20, 2)
        df["bb_mid"] = df["close"].rolling(20, min_periods=1).mean()
        bb_std = df["close"].rolling(20, min_periods=1).std(ddof=0)
        df["bb_upper"] = df["bb_mid"] + 2 * bb_std
        df["bb_lower"] = df["bb_mid"] - 2 * bb_std

        # Supertrend (10, 3)
        from src.market.technical_analyzer import compute_supertrend
        st_vals, st_dirs = compute_supertrend(df, length=10, mult=3.0)
        df["supertrend"] = st_vals
        df["supertrend_dir"] = st_dirs

        period_days = {"1m": 30, "3m": 90, "6m": 180, "1y": 365, "all": len(df)}
        limit = period_days.get(period.lower(), 90)
        sliced = df.tail(limit)

        points = []
        for _, row in sliced.iterrows():
            d_str = str(row["date"])[:10]
            c = round(float(row["close"]), 2) if row.get("close") is not None else 0.0
            o = round(float(row.get("open", c)), 2)
            h = round(float(row.get("high", c)), 2)
            l = round(float(row.get("low", c)), 2)
            v = int(row.get("volume", 0)) if row.get("volume") is not None else 0
            ema20_val = round(float(row["ema_20"]), 2) if pd.notna(row.get("ema_20")) else None
            sma50_val = round(float(row["sma_50"]), 2) if pd.notna(row.get("sma_50")) else None
            sma200_val = round(float(row["sma_200"]), 2) if pd.notna(row.get("sma_200")) else None
            bb_up_val = round(float(row["bb_upper"]), 2) if pd.notna(row.get("bb_upper")) else None
            bb_mid_val = round(float(row["bb_mid"]), 2) if pd.notna(row.get("bb_mid")) else None
            bb_low_val = round(float(row["bb_lower"]), 2) if pd.notna(row.get("bb_lower")) else None
            st_val = round(float(row["supertrend"]), 2) if pd.notna(row.get("supertrend")) else None
            st_dir = int(row["supertrend_dir"]) if pd.notna(row.get("supertrend_dir")) else 1

            points.append({
                "date": d_str,
                "close": c,
                "open": o,
                "high": h,
                "low": l,
                "volume": v,
                "is_up": c >= o,
                "ema_20": ema20_val,
                "sma_50": sma50_val,
                "sma_200": sma200_val,
                "bb_upper": bb_up_val,
                "bb_mid": bb_mid_val,
                "bb_lower": bb_low_val,
                "supertrend": st_val,
                "supertrend_dir": st_dir,
                "supertrend_bull": st_val if st_dir == 1 else None,
                "supertrend_bear": st_val if st_dir == -1 else None,
            })

        latest = points[-1] if points else None
        prev = points[-2] if len(points) >= 2 else latest
        change = round(latest["close"] - prev["close"], 2) if latest and prev else 0.0
        change_pct = round((change / prev["close"]) * 100, 2) if prev and prev["close"] else 0.0

        year_df = df.tail(252)
        high_52w = round(float(year_df["high"].max()), 2) if not year_df.empty and "high" in year_df else None
        low_52w = round(float(year_df["low"].min()), 2) if not year_df.empty and "low" in year_df else None
        avg_vol = int(year_df["volume"].mean()) if not year_df.empty and "volume" in year_df else 0

        overlays_latest = {
            "ema_20": latest.get("ema_20") if latest else None,
            "sma_50": latest.get("sma_50") if latest else None,
            "sma_200": latest.get("sma_200") if latest else None,
            "bb_upper": latest.get("bb_upper") if latest else None,
            "bb_mid": latest.get("bb_mid") if latest else None,
            "bb_lower": latest.get("bb_lower") if latest else None,
            "supertrend": latest.get("supertrend") if latest else None,
            "supertrend_dir": latest.get("supertrend_dir") if latest else 1,
        }

        return {
            "ticker": ticker,
            "period": period,
            "is_intraday": False,
            "session_status": "Historical Daily Sessions",
            "last_traded_at": f"{latest['date']} at 03:30 PM IST" if latest else "",
            "session_date": latest["date"] if latest else "",
            "latest_price": latest["close"] if latest else None,
            "change": change,
            "change_pct": change_pct,
            "high_52w": high_52w,
            "low_52w": low_52w,
            "avg_volume": avg_vol,
            "overlays_latest": overlays_latest,
            "points": points,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/stocks/{ticker}/technicals")
def stock_technicals(ticker: str, tip_markers: int = 0) -> dict[str, Any]:
    ticker = ticker.upper().strip()
    try:
        from src.ingest.market_data import load_ohlcv
        from src.market.technical_analyzer import analyze_technicals, evaluate_tip_divergence
        df = load_ohlcv(ticker, start="2023-01-01")
        analysis = analyze_technicals(df, ticker)
        divergence = evaluate_tip_divergence(ticker, analysis, tip_markers=tip_markers)
        return {**analysis, "divergence": divergence}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/portfolio")
def portfolio(refresh: bool = False) -> dict[str, Any]:
    holdings = _load_portfolio()
    try:
        from src.portfolio.valuation import enrich_and_value_portfolio
        return enrich_and_value_portfolio(holdings, risk_assessor=assess, force_refresh=refresh)
    except Exception as exc:
        logger.error("Error valuing portfolio: %s", exc)
        # Fallback to safe structure if error occurs
        enriched: list[dict[str, Any]] = []
        for item in holdings:
            rec = dict(item)
            rec["invested_value"] = _holding_value(rec)
            try:
                rec["risk"] = assess(str(rec.get("ticker", "")).upper())
            except Exception:
                rec["risk"] = {"score": None, "band": "Unavailable", "verdict": ""}
            enriched.append(rec)
        return {
            "holdings": enriched,
            "count": len(enriched),
            "total_positions": len(enriched),
            "total_invested": sum(h.get("invested_value", 0.0) for h in enriched),
            "total_actual_cost": sum(h.get("invested_value", 0.0) for h in enriched),
            "total_estimated_cost": 0.0,
            "total_market_value": 0.0,
            "total_unrealized_pnl": None,
            "total_unrealized_return_pct": None,
            "unpriced_count": len(enriched),
            "is_partial_valuation": True,
        }


@app.post("/api/portfolio/holdings")
def add_holding(request: HoldingRequest) -> dict[str, Any]:
    items = _load_portfolio()
    ticker = request.ticker.upper().strip()
    exchange = request.exchange.upper().strip()

    buy_price: float | None = None
    for cand in [request.average_buy_price, request.avg_buy_price, request.averagePrice]:
        if cand is not None:
            try:
                val = float(cand)
                if val > 0:
                    buy_price = round(val, 2)
            except (ValueError, TypeError):
                pass
            break

    item = {
        "exchange": exchange,
        "ticker": ticker,
        "bse_code": request.bse_code,
        "quantity": float(request.quantity),
        "average_buy_price": buy_price,
        "avg_buy_price": buy_price,
    }
    replaced = False
    for idx, existing in enumerate(items):
        if str(existing.get("ticker", "")).upper() == ticker and str(existing.get("exchange", "")).upper() == exchange:
            items[idx] = item
            replaced = True
            break
    if not replaced:
        items.append(item)
    _save_portfolio(items)

    try:
        from src.portfolio.valuation import enrich_and_value_portfolio
        enriched = enrich_and_value_portfolio([item], risk_assessor=assess, force_refresh=True)
        if enriched.get("holdings"):
            return enriched["holdings"][0]
    except Exception as exc:
        logger.debug("Failed enriching newly added holding: %s", exc)

    return item


@app.delete("/api/portfolio/holdings/{ticker}")
def delete_holding(ticker: str) -> dict[str, Any]:
    clean_ticker = ticker.upper().strip()
    items = _load_portfolio()
    new_items = [item for item in items if str(item.get("ticker", "")).upper() != clean_ticker]
    if len(new_items) == len(items):
        raise HTTPException(status_code=404, detail="Holding not found")
    _save_portfolio(new_items)
    return {"deleted": clean_ticker, "count": len(new_items)}


# ==============================================================================
# DAKOTA INTELLIGENCE CORE API ROUTES
# ==============================================================================

from starlette.responses import StreamingResponse, HTMLResponse
from src.intelligence.engine import IntelligenceEngine
from src.intelligence.models import IntelligenceQuery, SearchFilter, FeedbackItem
from src.intelligence.search import search_cross_module
from src.intelligence.reporter import ReportGenerator
from src.intelligence.conversations import (
    create_conversation,
    list_conversations,
    get_conversation_history,
    delete_conversation,
    record_feedback,
)
from src.intelligence.provider import get_ai_provider, test_provider_connectivity

_intelligence_engine = IntelligenceEngine()
_report_generator = ReportGenerator()


@app.get("/api/intelligence/status")
def intelligence_status() -> dict[str, Any]:
    """Return Intelligence Core provider, model, and operational status."""
    provider = get_ai_provider()
    return {
        "status": "online",
        "provider": provider.get_status(),
        "capabilities": [
            "grounded_retrieval",
            "citation_attribution",
            "cross_module_search",
            "multi_format_reports",
            "streaming_copilot",
            "prompt_injection_guard",
        ],
    }


@app.get("/api/intelligence/test-provider")
def intelligence_test_provider() -> dict[str, Any]:
    """Run real-time diagnostics on Mesh API router and Google Gemini providers."""
    return test_provider_connectivity()


@app.post("/api/intelligence/query")
def intelligence_query(request: IntelligenceQuery) -> dict[str, Any]:
    """Execute grounded question-answering with citation binding."""
    try:
        answer = _intelligence_engine.process_query(request)
        return answer.model_dump()
    except Exception as exc:
        logger.error("Intelligence query failure: %s", exc)
        raise HTTPException(status_code=500, detail=f"Intelligence Core error: {exc}") from exc


@app.get("/api/intelligence/query/stream")
def intelligence_query_stream(
    query: str,
    conversation_id: str | None = None,
    ticker: str | None = None,
    investigation_id: str | None = None,
) -> StreamingResponse:
    """Stream AI Copilot response using Server-Sent Events (SSE)."""
    if not query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    ctx = {}
    if ticker:
        ctx["ticker"] = ticker.upper().strip()
    if investigation_id:
        ctx["investigation_id"] = investigation_id.strip()

    req = IntelligenceQuery(
        query=query,
        conversation_id=conversation_id,
        active_context=ctx,
        stream=True,
    )

    def event_stream():
        try:
            for event_chunk in _intelligence_engine.stream_query(req):
                yield event_chunk
        except Exception as exc:
            logger.error("SSE stream error: %s", exc)
            yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/intelligence/search")
def intelligence_search(
    search: str = "",
    entity: str = "",
    band: str = "",
    types: str = "",
    page: int = 1,
    limit: int = 20,
) -> dict[str, Any]:
    """Unified search across Stocks, Live Investigations, Campaigns, and Portfolio."""
    source_list = [t.strip().lower() for t in types.split(",") if t.strip()] if types else []
    filters = SearchFilter(
        search=search,
        entity=entity,
        risk_band=band,
        source_types=source_list,
        page=page,
        limit=limit,
    )
    return search_cross_module(filters)


@app.get("/api/intelligence/conversations")
def intelligence_list_conversations(limit: int = 30) -> dict[str, Any]:
    """List recent conversation sessions."""
    return {"conversations": list_conversations(limit=limit)}


@app.post("/api/intelligence/conversations")
def intelligence_create_conversation(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a new conversational intelligence session."""
    payload = payload or {}
    title = str(payload.get("title") or "New Investigation Session")
    context = payload.get("context")
    return create_conversation(title=title, context=context)


@app.get("/api/intelligence/conversations/{conversation_id}")
def intelligence_get_conversation(conversation_id: str) -> dict[str, Any]:
    """Get full message history and citations for a conversation."""
    history = get_conversation_history(conversation_id)
    return {"conversation_id": conversation_id, "messages": history}


@app.delete("/api/intelligence/conversations/{conversation_id}")
def intelligence_delete_conversation(conversation_id: str) -> dict[str, Any]:
    """Delete a conversation session."""
    deleted = delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"deleted": conversation_id}


@app.post("/api/intelligence/report")
def intelligence_generate_report(payload: dict[str, Any]) -> dict[str, Any]:
    """Generate structured intelligence brief."""
    ticker = payload.get("ticker")
    inv_id = payload.get("investigation_id")
    rep_type = str(payload.get("report_type") or "company_brief")
    custom_title = payload.get("title")

    rep = _report_generator.generate_report(
        report_type=rep_type,
        ticker=ticker,
        investigation_id=inv_id,
        custom_title=custom_title,
    )
    md_content = _report_generator.render_markdown(rep)
    html_content = _report_generator.render_html(rep)

    return {
        "report": rep.model_dump(),
        "markdown": md_content,
        "html": html_content,
    }


@app.get("/api/intelligence/report/{report_id}/export")
def intelligence_export_report(
    report_id: str,
    ticker: str | None = None,
    format: str = "html",
) -> Any:
    """Export report as printable HTML or Markdown."""
    rep = _report_generator.generate_report(ticker=ticker or report_id)
    if format.lower() == "markdown":
        return PlainTextResponse(_report_generator.render_markdown(rep), media_type="text/markdown")
    return HTMLResponse(_report_generator.render_html(rep))


@app.post("/api/intelligence/feedback")
def intelligence_submit_feedback(request: FeedbackItem) -> dict[str, Any]:
    """Submit user feedback or flag citation inaccuracies."""
    record_feedback(
        answer_id=request.answer_id,
        query=request.query,
        feedback_type=request.feedback_type,
        notes=request.notes,
    )
    return {"status": "recorded"}


# --- JEV Financial Intelligence Subsystem ---
try:
    from src.intelligence.jev.api import router as jev_router
    app.include_router(jev_router)
    logger.info("Mounted JEV intelligence subsystem router at /api/intelligence/jev")
except Exception as exc:
    logger.warning("Could not mount JEV intelligence router: %s", exc)


