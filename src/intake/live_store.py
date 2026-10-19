"""Privacy-safe live investigation store for Dakota."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
STORE_DIR = ROOT / "data" / "live"
STORE_FILE = STORE_DIR / "investigations.jsonl"
_LOCK = Lock()


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return str(value)


def save_live_investigation(record: dict[str, Any]) -> dict[str, Any]:
    """Append one derived investigation record. Never stores raw Telegram text."""
    payload = _jsonable(record)
    payload.setdefault(
        "stored_at",
        datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        with STORE_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    try:
        from src.campaign.detector import campaign_detector
        campaign_detector.correlate_tip(payload)
    except Exception:
        pass
    return payload


def load_live_investigations(limit: int = 50) -> list[dict[str, Any]]:
    if not STORE_FILE.exists():
        return []
    limit = max(1, min(int(limit), 200))
    out: list[dict[str, Any]] = []
    try:
        lines = STORE_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines[-limit:]:
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                out.append(item)
        except json.JSONDecodeError:
            continue
    return list(reversed(out))


def get_live_investigation(investigation_id: str) -> dict[str, Any] | None:
    for item in load_live_investigations(limit=200):
        if str(item.get("investigation_id")) == investigation_id:
            return item
    return None
