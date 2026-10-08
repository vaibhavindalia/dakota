"""Telegram Bot API connector for authorized tip ingestion."""
from __future__ import annotations

from typing import Any

import requests

from src.connectors.config import env


def _url(method: str) -> str:
    token = env("TELEGRAM_BOT_TOKEN")
    return f"https://api.telegram.org/bot{token}/{method}"


def send_message(chat_id: int | str, text: str, *, timeout: float = 8.0) -> dict[str, Any]:
    if not env("TELEGRAM_BOT_TOKEN"):
        return {"status": "missing_credentials", "error": "TELEGRAM_BOT_TOKEN is not configured"}

    response = requests.post(
        _url("sendMessage"),
        json={"chat_id": chat_id, "text": text[:4096]},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def set_webhook(webhook_url: str, *, timeout: float = 8.0) -> dict[str, Any]:
    if not env("TELEGRAM_BOT_TOKEN"):
        return {"status": "missing_credentials", "error": "TELEGRAM_BOT_TOKEN is not configured"}
    response = requests.post(
        _url("setWebhook"),
        json={"url": webhook_url},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def extract_tip_update(update: dict[str, Any]) -> dict[str, Any] | None:
    message = (
        update.get("message")
        or update.get("edited_message")
        or update.get("channel_post")
        or update.get("edited_channel_post")
        or update.get("business_message")
    )
    if not isinstance(message, dict):
        return None

    text = str(message.get("text") or "").strip()
    if not text:
        return None

    chat = message.get("chat") or {}
    return {
        "tip": text,
        "chat_id": chat.get("id"),
        "chat_type": chat.get("type"),
        "source": "telegram_bot",
    }
