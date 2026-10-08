"""Dakota FastAPI backend — real-data investigation build.

Core flow:
    tip -> parser -> NSE/BSE -> indicators -> news -> social -> company -> index
         -> coordination -> explainable available-evidence score

External integrations are credential-gated. Missing credentials are surfaced as
coverage gaps and are never treated as clean evidence.
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any

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

app = FastAPI(title="Dakota API", version="0.4.0")

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
    exchange: str = Field(default="NSE", min_length=3, max_length=4)
    ticker: str = Field(min_length=1, max_length=30)
    bse_code: str | None = None
    quantity: float = Field(gt=0)
    avg_buy_price: float = Field(gt=0)


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
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _save_portfolio(items: list[dict[str, Any]]) -> None:
    PORTFOLIO_FILE.parent.mkdir(parents=True, exist_ok=True)
    PORTFOLIO_FILE.write_text(json.dumps(items, indent=2), encoding="utf-8")


def _holding_value(item: dict[str, Any]) -> float:
    return float(item.get("quantity", 0)) * float(item.get("avg_buy_price", 0))


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
    try:
        result = check_tip(request.tip)
        result["source"] = request.source
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
def stocks() -> list[dict[str, Any]]:
    rows = _load_universe_rows()
    result: list[dict[str, Any]] = []
    for row in rows:
        ticker = str(row.get("ticker") or row.get("Ticker") or "").upper().strip()
        if not ticker:
            continue
        try:
            risk = assess(ticker)
        except Exception:
            risk = {"score": None, "band": "Unavailable", "verdict": ""}
        result.append({**row, **risk, "ticker": ticker})
    return result


@app.get("/api/stocks/{ticker}")
def stock_detail(ticker: str) -> dict[str, Any]:
    ticker = ticker.upper().strip()
    rows = _load_universe_rows()
    match = next((r for r in rows if str(r.get("ticker", "")).upper() == ticker), {})
    try:
        risk = assess(ticker)
    except Exception as exc:
        risk = {"score": None, "band": "Unavailable", "verdict": str(exc)}
    return {"ticker": ticker, "meta": match, "risk": risk}


@app.get("/api/portfolio")
def portfolio() -> dict[str, Any]:
    holdings = _load_portfolio()
    enriched: list[dict[str, Any]] = []
    total_invested = 0.0
    for item in holdings:
        record = dict(item)
        record["invested_value"] = _holding_value(record)
        try:
            record["risk"] = assess(str(record["ticker"]).upper())
        except Exception:
            record["risk"] = {"score": None, "band": "Unavailable", "verdict": ""}
        total_invested += record["invested_value"]
        enriched.append(record)

    return {
        "holdings": enriched,
        "count": len(enriched),
        "total_invested": round(total_invested, 2),
    }


@app.post("/api/portfolio/holdings")
def add_holding(request: HoldingRequest) -> dict[str, Any]:
    items = _load_portfolio()
    ticker = request.ticker.upper().strip()
    exchange = request.exchange.upper().strip()
    item = {
        "exchange": exchange,
        "ticker": ticker,
        "bse_code": request.bse_code,
        "quantity": request.quantity,
        "avg_buy_price": request.avg_buy_price,
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
    return item


@app.delete("/api/portfolio/holdings/{ticker}")
def delete_holding(ticker: str) -> dict[str, Any]:
    ticker = ticker.upper().strip()
    items = _load_portfolio()
    new_items = [item for item in items if str(item.get("ticker", "")).upper() != ticker]
    if len(new_items) == len(items):
        raise HTTPException(status_code=404, detail="Holding not found")
    _save_portfolio(new_items)
    return {"deleted": ticker}
