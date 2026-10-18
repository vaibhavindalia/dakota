"""Central connector configuration for Dakota.

Credentials are read from environment variables (or a local .env file when
python-dotenv is installed). Secrets are never returned by the API.
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

BASE_DIR = Path(__file__).resolve().parents[2]

if load_dotenv is not None:
    load_dotenv(BASE_DIR / ".env")


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def enabled(name: str) -> bool:
    return bool(env(name))


def public_status() -> dict[str, str]:
    return {
        "x": "configured" if enabled("X_BEARER_TOKEN") else "missing_credentials",
        "reddit": (
            "configured"
            if env("REDDIT_CLIENT_ID") and env("REDDIT_CLIENT_SECRET")
            else "rss_fallback"
        ),
        "instagram": (
            "configured"
            if env("INSTAGRAM_ACCESS_TOKEN") and env("INSTAGRAM_USER_ID")
            else "missing_credentials"
        ),
        "telegram": (
            "configured"
            if enabled("TELEGRAM_BOT_TOKEN") or enabled("DAKOTA_BOT_TOKEN")
            else "missing_credentials"
        ),
        "whatsapp": (
            "configured"
            if env("WHATSAPP_ACCESS_TOKEN") and env("WHATSAPP_PHONE_NUMBER_ID")
            else "missing_credentials"
        ),
        "nse": "local_package_or_cached",
        "bse": "local_package_or_cached",
        "news": "gdelt_public",
    }
