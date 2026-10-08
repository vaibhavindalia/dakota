"""Social-source orchestration for Dakota."""
from __future__ import annotations

from typing import Any

from src.connectors.instagram import search_instagram
from src.connectors.reddit_api import search_reddit_real
from src.connectors.x_api import search_x


def collect_social_evidence(ticker: str) -> dict[str, Any]:
    return {
        "reddit": search_reddit_real(ticker),
        "x": search_x(ticker),
        "instagram": search_instagram(ticker),
        "telegram": {
            "status": "ingestion_connector",
            "results": [],
            "observations": [],
            "error": None,
        },
    }
