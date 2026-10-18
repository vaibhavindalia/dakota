"""Instagram Graph API hashtag connector for Dakota.

Credentials:
    INSTAGRAM_ACCESS_TOKEN
    INSTAGRAM_USER_ID
    META_GRAPH_VERSION

The API path used here is the public hashtag discovery flow exposed through
Meta's Graph API. Availability depends on the Instagram/Meta account, app
permissions, and provider-side review/limits.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from src.connectors.config import env

BASE = "https://graph.facebook.com"

HYPE_TERMS = {
    "multibagger",
    "multibag",
    "guaranteed",
    "target",
    "upper circuit",
    "buy now",
    "rocket",
    "breakout",
    "operator",
    "sure shot",
    "sure-shot",
}



DEFAULT_META_GRAPH_VERSION = "v21.0"


def _get_api_version() -> str:
    """Normalize Meta Graph API version, defaulting to v21.0."""
    raw = env("META_GRAPH_VERSION") or ""
    raw = raw.strip().lstrip("/")
    if not raw:
        return DEFAULT_META_GRAPH_VERSION
    if not raw.startswith("v"):
        raw = f"v{raw}"
    return raw


def normalize_graph_version(raw: str | None) -> str:
    """Normalize Meta Graph API version, defaulting to v21.0."""
    val = (raw or "").strip().lstrip("/")
    if not val:
        return DEFAULT_META_GRAPH_VERSION
    if not val.startswith("v"):
        val = f"v{val}"
    return val


def _sanitize_string(text: str, token: str | None = None) -> str:
    """Sanitize string by redacting secret access tokens."""
    if not text:
        return ""
    res = str(text)
    if token and len(token) > 4:
        res = res.replace(token, "[REDACTED_ACCESS_TOKEN]")
    import re
    res = re.sub(r"access_token=[A-Za-z0-9_\-]+", "access_token=[REDACTED]", res)
    return res


def _parse_meta_error(resp: requests.Response, token: str | None = None) -> tuple[str, str]:
    """Parse structured Meta Graph API JSON error and return normalized status and message."""
    status_code = resp.status_code
    status = "error"
    try:
        body = resp.json()
        err = body.get("error") if isinstance(body, dict) else {}
        code = err.get("code")
        subcode = err.get("error_subcode")
        msg = err.get("message", "")
        err_type = err.get("type", "")

        # OAuth token issues
        if code == 190 or err_type == "OAuthException" or subcode in {463, 467}:
            status = "token_expired"
            return status, _sanitize_string(
                f"Meta OAuth token has expired or is invalid (Code {code}, Subcode {subcode}): Please regenerate a new access token.",
                token,
            )

        # Permission or capability issues
        if code in {10, 200}:
            status = "insufficient_permissions"
            return status, _sanitize_string(
                f"Application does not have the required permissions (e.g. instagram_basic, pages_show_list): {msg}",
                token,
            )

        # Invalid account ID
        if code == 100:
            status = "invalid_account_id"
            return status, _sanitize_string(
                f"Invalid Instagram Account ID. Ensure this is an Instagram Professional (Business or Creator) account ID connected to a Facebook page: {msg}",
                token,
            )

        # Rate limit
        if code in {4, 17, 32, 613} or status_code == 429:
            status = "rate_limited"
            return status, _sanitize_string(f"Meta Graph API rate limit reached: {msg}", token)

        if msg:
            return status, _sanitize_string(f"Meta error (Code {code}): {msg}", token)
    except Exception:
        pass

    safe_text = resp.text[:200].replace("\n", " ").strip()
    return status, _sanitize_string(f"HTTP {status_code}: {safe_text or resp.reason}", token)


def parse_meta_api_error(resp: requests.Response) -> tuple[str, str]:
    """Backward-compatible alias for _parse_meta_error."""
    return _parse_meta_error(resp)


def validate_instagram_credentials(timeout: int = 10) -> dict[str, Any]:
    """Validate Instagram credentials by querying Meta Graph API for account metadata."""
    token = env("INSTAGRAM_ACCESS_TOKEN")
    user_id = env("INSTAGRAM_USER_ID")
    version = _get_api_version()

    missing: list[str] = []
    if not token:
        missing.append("INSTAGRAM_ACCESS_TOKEN")
    if not user_id:
        missing.append("INSTAGRAM_USER_ID")

    if missing:
        return {
            "status": "missing_credentials",
            "configured": False,
            "missing_fields": missing,
            "setup_guide": (
                "Add INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_USER_ID to your environment or .env file. "
                "See NEWS_SOCIAL_INTEGRATION.md for step-by-step setup instructions."
            ),
        }

    url = f"{BASE}/{version}/{user_id}"
    params = {"fields": "id,username,name", "access_token": token}
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "status": "connected",
                "configured": True,
                "username": data.get("username", "verified_user"),
                "account_id": str(data.get("id", user_id)),
                "name": data.get("name"),
            }
        status, err_msg = _parse_meta_error(resp, token)
        return {
            "status": status,
            "configured": False,
            "error": err_msg,
            "status_code": resp.status_code,
        }
    except Exception as exc:
        return {
            "status": "error",
            "configured": False,
            "error": _sanitize_string(str(exc), token),
        }


def get_instagram_config_status() -> dict[str, Any]:
    """Return sanitized Instagram configuration status without exposing tokens."""
    token = env("INSTAGRAM_ACCESS_TOKEN")
    user_id = env("INSTAGRAM_USER_ID")
    version = _get_api_version()

    missing: list[str] = []
    if not token:
        missing.append("INSTAGRAM_ACCESS_TOKEN")
    if not user_id:
        missing.append("INSTAGRAM_USER_ID")

    is_configured = len(missing) == 0

    return {
        "status": "configured" if is_configured else "testing_phases",
        "provider": "Instagram",
        "configured": is_configured,
        "has_access_token": bool(token),
        "has_user_id": bool(user_id),
        "graph_version": version,
        "missing_fields": missing,
        "account_type_required": "Instagram Professional (Business or Creator) connected to a Meta Facebook Page",
        "required_permissions": ["instagram_basic", "pages_show_list"],
        "help": (
            "Ready for hashtag discovery."
            if is_configured
            else "Instagram hashtag discovery adapter is active in testing phase."
        ),
    }


def search_instagram(
    ticker: str,
    *,
    limit: int = 25,
    timeout: float = 12.0,
) -> dict[str, Any]:
    ticker = ticker.upper().strip().split(".")[0]
    fetched_at = datetime.now(timezone.utc).isoformat()

    token = env("INSTAGRAM_ACCESS_TOKEN")
    user_id = env("INSTAGRAM_USER_ID")
    version = _get_api_version()

    missing: list[str] = []
    if not token:
        missing.append("INSTAGRAM_ACCESS_TOKEN")
    if not user_id:
        missing.append("INSTAGRAM_USER_ID")

    if missing:
        return {
            "status": "missing_credentials",
            "provider": "Instagram",
            "query": f"#{ticker}",
            "results": [],
            "result_count": 0,
            "hype_result_count": 0,
            "observations": [
                {
                    "signal": "instagram_testing",
                    "severity": "low",
                    "text": "Instagram hashtag discovery adapter is active in testing phase.",
                }
            ],
            "error": f"Instagram credentials not configured (missing: {', '.join(missing)}). Using Meta Graph API {version}.",
            "missing_fields": missing,
            "graph_version": version,
            "fetched_at": fetched_at,
        }

    try:
        search = requests.get(
            f"{BASE}/{version}/ig_hashtag_search",
            params={
                "user_id": user_id,
                "q": ticker.lower().lstrip("#"),
                "access_token": token,
            },
            timeout=timeout,
        )
        if search.status_code != 200:
            err_status, err_msg = parse_meta_api_error(search)
            return {
                "status": err_status,
                "provider": "Instagram",
                "query": f"#{ticker}",
                "results": [],
                "result_count": 0,
                "hype_result_count": 0,
                "observations": [],
                "error": err_msg,
                "fetched_at": fetched_at,
            }

        hashtag_items = search.json().get("data") or []
        if not hashtag_items:
            return {
                "status": "connected",
                "provider": "Instagram",
                "query": f"#{ticker}",
                "results": [],
                "result_count": 0,
                "hype_result_count": 0,
                "observations": [],
                "error": None,
                "fetched_at": fetched_at,
                "hashtag_found": False,
            }

        hashtag_id = str(hashtag_items[0].get("id") or "")
        media = requests.get(
            f"{BASE}/{version}/{hashtag_id}/recent_media",
            params={
                "user_id": user_id,
                "fields": "id,caption,media_type,permalink,timestamp,like_count,comments_count",
                "access_token": token,
                "limit": max(1, min(int(limit), 50)),
            },
            timeout=timeout,
        )
        if media.status_code != 200:
            err_status, err_msg = parse_meta_api_error(media)
            return {
                "status": err_status,
                "provider": "Instagram",
                "query": f"#{ticker}",
                "results": [],
                "result_count": 0,
                "hype_result_count": 0,
                "observations": [],
                "error": err_msg,
                "fetched_at": fetched_at,
                "hashtag_found": True,
            }

        items = media.json().get("data") or []
        results: list[dict[str, Any]] = []
        hype_count = 0

        for item in items:
            if not isinstance(item, dict):
                continue
            caption = str(item.get("caption") or "").strip()
            if any(term in caption.lower() for term in HYPE_TERMS):
                hype_count += 1
            results.append(
                {
                    "id": str(item.get("id") or ""),
                    "caption": caption[:1200],
                    "media_type": item.get("media_type"),
                    "permalink": item.get("permalink"),
                    "timestamp": item.get("timestamp"),
                    "like_count": item.get("like_count", 0),
                    "comments_count": item.get("comments_count", 0),
                }
            )

        observations: list[dict[str, Any]] = []
        if len(results) >= 10:
            observations.append(
                {
                    "signal": "instagram_volume",
                    "severity": "medium",
                    "text": f"Instagram hashtag search returned {len(results)} public media item(s).",
                }
            )
        elif results:
            observations.append(
                {
                    "signal": "instagram_presence",
                    "severity": "low",
                    "text": f"Instagram hashtag search found {len(results)} public media item(s).",
                }
            )

        if hype_count >= 3:
            observations.append(
                {
                    "signal": "instagram_hype_language",
                    "severity": "medium",
                    "text": f"{hype_count} Instagram caption(s) contain hype-style keywords.",
                }
            )

        return {
            "status": "connected",
            "provider": "Instagram",
            "query": f"#{ticker}",
            "fetched_at": fetched_at,
            "results": results,
            "result_count": len(results),
            "hype_result_count": hype_count,
            "observations": observations,
            "error": None,
            "hashtag_found": True,
        }
    except requests.Timeout:
        return {
            "status": "timeout",
            "provider": "Instagram",
            "query": f"#{ticker}",
            "results": [],
            "result_count": 0,
            "hype_result_count": 0,
            "observations": [],
            "error": f"Instagram request timed out after {timeout}s",
            "fetched_at": fetched_at,
        }
    except Exception as exc:
        return {
            "status": "error",
            "provider": "Instagram",
            "query": f"#{ticker}",
            "results": [],
            "result_count": 0,
            "hype_result_count": 0,
            "observations": [],
            "error": str(exc),
            "fetched_at": fetched_at,
        }
