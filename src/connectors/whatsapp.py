"""Meta WhatsApp Cloud API webhook helpers."""
from __future__ import annotations

import hashlib
import hmac
from typing import Any

import requests

from src.connectors.config import env


def verify_signature(raw_body: bytes, header: str | None) -> bool:
    secret = env("WHATSAPP_APP_SECRET")
    if not secret:
        return True
    if not header or not header.startswith("sha256="):
        return False
    supplied = header.split("=", 1)[1]
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(supplied, expected)


def verify_webhook(mode: str, token: str, challenge: str) -> str | None:
    if mode != "subscribe":
        return None
    if token != env("WHATSAPP_VERIFY_TOKEN"):
        return None
    return challenge


def send_text(to: str, text: str, *, timeout: float = 10.0) -> dict[str, Any]:
    access_token = env("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = env("WHATSAPP_PHONE_NUMBER_ID")
    version = env("META_GRAPH_VERSION")

    if not access_token or not phone_number_id or not version:
        return {
            "status": "missing_credentials",
            "error": "Set WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID and META_GRAPH_VERSION",
        }

    response = requests.post(
        f"https://graph.facebook.com/{version}/{phone_number_id}/messages",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text[:4096]},
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def extract_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for message in value.get("messages") or []:
                if message.get("type") != "text":
                    continue
                text = str((message.get("text") or {}).get("body") or "").strip()
                sender = str(message.get("from") or "")
                if text:
                    messages.append({"tip": text, "sender": sender})
    return messages
