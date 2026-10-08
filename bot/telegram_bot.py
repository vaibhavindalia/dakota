"""
Dakota — Telegram Tip Intake Bot
=================================

Two intake paths:

1. Direct/private message
2. Automatic Telegram channel post

Current phase:
Telegram channel
    -> receive post
    -> privacy scrub
    -> parse
    -> investigation record

The investigation/evidence pipeline will be connected later.

IMPORTANT:
The bot only receives channel posts from channels that Telegram
makes available to the bot. It does not scrape arbitrary Telegram.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# Project path
# --------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# --------------------------------------------------------------------------
# Telegram
# --------------------------------------------------------------------------

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


# --------------------------------------------------------------------------
# Dakota intake
# --------------------------------------------------------------------------

from src.intake.tip_intake import (
    intake_tip,
    load_records,
)


# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

logging.getLogger("httpx").setLevel(logging.WARNING)

log = logging.getLogger("dakota.bot")


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

TOKEN = os.environ.get(
    "DAKOTA_BOT_TOKEN",
    "",
).strip()

MIN_TIP_LENGTH = 12


# --------------------------------------------------------------------------
# Messages
# --------------------------------------------------------------------------

WELCOME = (
    "*Dakota*\n\n"
    "Forward or paste a stock tip here and Dakota will "
    "create an investigation record.\n\n"
    "Dakota can also receive new posts automatically "
    "from monitored Telegram channels."
)

DISCLAIMER = (
    "_Dakota reports risk indicators only. "
    "Not investment advice, not an accusation of fraud._"
)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _extract_message_text(
    message,
) -> str:

    if message is None:
        return ""

    return (
        message.text
        or message.caption
        or ""
    ).strip()


def _channel_name(
    message,
) -> str:

    if message is None:
        return "unknown"

    chat = message.chat

    if chat is None:
        return "unknown"

    if chat.title:
        return chat.title

    if chat.username:
        return f"@{chat.username}"

    return str(chat.id)


def _channel_id(
    message,
) -> int | None:

    if message is None:
        return None

    if message.chat is None:
        return None

    return message.chat.id


# --------------------------------------------------------------------------
# Intake
# --------------------------------------------------------------------------

async def process_tip(
    text: str,
    source: str,
    channel_name: str | None = None,
    channel_id: int | None = None,
) -> None:

    if len(text.strip()) < MIN_TIP_LENGTH:

        log.info(
            "ignored short message | source=%s | channel=%s",
            source,
            channel_name or "-",
        )

        return

    record = intake_tip(
        text,
        source=source,
    )

    log.info(
        "TIP RECEIVED | source=%s | channel=%s | channel_id=%s | "
        "investigation_id=%s | ticker=%s | target=%s | markers=%s",
        source,
        channel_name or "-",
        channel_id if channel_id is not None else "-",
        record.investigation_id,
        record.primary_ticker or "-",
        record.price_target
        if record.price_target is not None
        else "-",
        record.n_scam_markers,
    )


# --------------------------------------------------------------------------
# Direct/private Telegram messages
# --------------------------------------------------------------------------

async def on_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    message = update.effective_message

    if message is None:
        return

    text = _extract_message_text(
        message
    )

    if len(text) < MIN_TIP_LENGTH:

        await message.reply_text(
            "Forward me a stock tip and "
            "I'll create an investigation record."
        )

        return

    await process_tip(
        text=text,
        source="telegram",
    )

    await message.reply_text(
        "Tip received. Dakota created an "
        "investigation record.\n\n"
        + DISCLAIMER
    )


# --------------------------------------------------------------------------
# Automatic channel posts
# --------------------------------------------------------------------------

async def on_channel_post(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    message = update.channel_post

    if message is None:
        return

    text = _extract_message_text(
        message
    )

    channel_name = _channel_name(
        message
    )

    channel_id = _channel_id(
        message
    )

    log.info(
        "CHANNEL POST RECEIVED | channel=%s | channel_id=%s | "
        "message_id=%s",
        channel_name,
        channel_id,
        message.message_id,
    )

    if len(text) < MIN_TIP_LENGTH:

        log.info(
            "channel post ignored because it is too short | "
            "channel=%s | message_id=%s",
            channel_name,
            message.message_id,
        )

        return

    await process_tip(
        text=text,
        source="telegram",
        channel_name=channel_name,
        channel_id=channel_id,
    )


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

async def cmd_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    if update.message is None:
        return

    await update.message.reply_text(
        WELCOME
    )


async def cmd_help(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    if update.message is None:
        return

    await update.message.reply_text(
        (
            "Dakota currently accepts:\n\n"
            "1. stock tips sent directly to the bot\n"
            "2. automatic posts from Telegram channels "
            "available to the bot\n\n"
            "Each tip is scrubbed, parsed and stored as "
            "an investigation record.\n\n"
            + DISCLAIMER
        )
    )


async def cmd_recent(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    if update.message is None:
        return

    records = load_records(
        limit=10
    )

    if not records:

        await update.message.reply_text(
            "No tips received yet."
        )

        return

    lines = [
        "Recent Dakota tips:",
        "",
    ]

    for record in reversed(records):

        investigation_id = record.get(
            "investigation_id",
            "unknown",
        )

        ticker = record.get(
            "primary_ticker"
        ) or "unknown"

        source = record.get(
            "source",
            "unknown",
        )

        created_at = record.get(
            "created_at",
            "",
        )

        lines.append(
            f"{investigation_id} | "
            f"{ticker} | "
            f"{source} | "
            f"{created_at[:16]}"
        )

    await update.message.reply_text(
        "\n".join(lines)
    )


# --------------------------------------------------------------------------
# Error handler
# --------------------------------------------------------------------------

async def on_error(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    log.error(
        "handler error",
        exc_info=context.error,
    )


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def main() -> None:

    if not TOKEN:

        print(
            "DAKOTA_BOT_TOKEN is not set."
        )

        print(
            'Set it with: '
            '$env:DAKOTA_BOT_TOKEN="your_token_here"'
        )

        raise SystemExit(1)

    app = (
        Application
        .builder()
        .token(TOKEN)
        .build()
    )

    # Commands
    app.add_handler(
        CommandHandler(
            "start",
            cmd_start,
        )
    )

    app.add_handler(
        CommandHandler(
            "help",
            cmd_help,
        )
    )

    app.add_handler(
        CommandHandler(
            "recent",
            cmd_recent,
        )
    )

    # Direct/private messages
    app.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            on_message,
        )
    )

    # Automatic Telegram channel posts
    app.add_handler(
        MessageHandler(
            filters.UpdateType.CHANNEL_POST,
            on_channel_post,
        )
    )

    app.add_error_handler(
        on_error
    )

    log.info(
        "Dakota Telegram collector starting..."
    )

    log.info(
        "Waiting for direct messages and channel posts."
    )

    app.run_polling(
        allowed_updates=[
            "message",
            "channel_post",
        ]
    )


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

if __name__ == "__main__":
    main()