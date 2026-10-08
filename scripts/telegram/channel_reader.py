"""Dakota Telegram public-channel investigation reader."""
from __future__ import annotations

import logging
import os
import sys
from datetime import timezone
from pathlib import Path
from typing import Any

from telethon import TelegramClient, events

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.classification.local_classifier import classify_message
from src.intake.live_store import save_live_investigation
from src.intake.tip_intake import intake_tip
from src.investigation.impact_mapper import map_impact
from src.investigation.universal_investigator import investigate_message

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("dakota.telegram_reader")

API_ID_RAW = os.environ.get("TELEGRAM_API_ID", "").strip()
API_HASH = os.environ.get("TELEGRAM_API_HASH", "").strip()
SESSION_PATH = ROOT / "data" / "telegram" / "dakota_reader"
MONITORED_CHANNELS = [
    "Stock_Burner_Offixal",
    "Growx_intraday_groww",
    "NIFTY50STOCKSSEBI",
    "Mystocksin",
    "MINISH_FAST",
    "mastertrustresearch",
    "markemahakelpredictions",
]

if not API_ID_RAW:
    raise SystemExit("TELEGRAM_API_ID is not set.")
if not API_HASH:
    raise SystemExit("TELEGRAM_API_HASH is not set.")
try:
    API_ID = int(API_ID_RAW)
except ValueError as exc:
    raise SystemExit("TELEGRAM_API_ID must be a number.") from exc

SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
client = TelegramClient(str(SESSION_PATH), API_ID, API_HASH)


def _risk_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if getattr(value, "tzinfo", None) is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.isoformat(timespec="seconds")
    except Exception:
        return None


def _source_label(username: str | None) -> str:
    return f"telegram:{username}" if username else "telegram"


@client.on(events.NewMessage(chats=MONITORED_CHANNELS))
async def on_new_message(event) -> None:
    message = event.message
    if message is None or not message.post:
        return

    text = (message.raw_text or "").strip()
    if not text:
        return

    chat = await event.get_chat()
    channel_name = getattr(chat, "title", None) or getattr(chat, "username", None) or str(getattr(chat, "id", "unknown"))
    channel_username = getattr(chat, "username", None)
    channel_id = getattr(chat, "id", None)

    log.info(
        "TELEGRAM POST | channel=%s | username=%s | id=%s | message_id=%s",
        channel_name,
        f"@{channel_username}" if channel_username else "-",
        channel_id or "-",
        message.id,
    )

    record = intake_tip(text, source="telegram")
    risk_timestamp = _risk_timestamp(message.date)

    log.info(
        "INTAKE | investigation_id=%s | ticker=%s | target=%s | markers=%s",
        record.investigation_id,
        record.primary_ticker or "-",
        record.price_target if record.price_target is not None else "-",
        record.n_scam_markers,
    )

    classification = classify_message(text)
    impact = map_impact(text, classification)

    log.info(
        "CLASSIFICATION | type=%s | domain=%s | topic=%s | tickers=%s | confidence=%s",
        classification.get("message_type") or classification.get("type") or "-",
        classification.get("market_domain") or classification.get("domain") or "-",
        classification.get("topic") or "-",
        classification.get("tickers") or "-",
        classification.get("confidence") or "-",
    )

    log.info(
        "IMPACT | status=%s | domain=%s | entity=%s | targets=%s",
        impact.get("status") or "-",
        impact.get("domain") or "-",
        impact.get("entity") or "-",
        impact.get("investigation_targets") or "-",
    )

    investigation = investigate_message(
        text,
        classification,
        data_root=str(ROOT / "data" / "raw"),
        source_label=_source_label(channel_username),
        timestamp=risk_timestamp,
    )

    # Store only derived data — never raw Telegram text.
    live = {
        "investigation_id": record.investigation_id,
        "captured_at": record.created_at,
        "channel": channel_name,
        "channel_username": f"@{channel_username}" if channel_username else None,
        "channel_id": channel_id,
        "message_id": message.id,
        "telegram_timestamp": risk_timestamp,
        "ticker": record.primary_ticker,
        "tickers": record.tickers,
        "price_target": record.price_target,
        "urgency": record.urgency,
        "n_scam_markers": record.n_scam_markers,
        "markers_found": record.markers_found,
        "fingerprint": record.fingerprint,
        "classification": classification,
        "impact": impact,
        "investigation": investigation,
        "status": investigation.get("status") or impact.get("status") or "classified",
        "risk": investigation.get("risk"),
        "disclaimer": investigation.get("disclaimer") or "Dakota reports risk indicators only. Not investment advice.",
    }
    save_live_investigation(live)

    risk = investigation.get("risk") or {}
    log.info(
        "INVESTIGATION COMPLETE | status=%s | entity=%s | score=%s | band=%s",
        live["status"],
        impact.get("entity") or record.primary_ticker or "-",
        risk.get("score", "-"),
        risk.get("band", "-"),
    )


async def main() -> None:
    log.info("Starting Dakota Telegram investigation collector...")
    log.info("Monitoring %d Telegram channels", len(MONITORED_CHANNELS))
    await client.start()
    me = await client.get_me()
    log.info(
        "Telegram account connected | username=%s | id=%s",
        f"@{getattr(me, 'username', '')}" if getattr(me, "username", None) else "-",
        getattr(me, "id", "-"),
    )
    log.info("Waiting for new posts...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    with client:
        client.loop.run_until_complete(main())
