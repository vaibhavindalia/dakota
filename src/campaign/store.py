"""Persistent SQLite storage layer for Dakota's Campaign & Syndicate Correlation Engine.

Manages tip events, cross-scrip campaign records, forensic event timelines,
and investigator review states in `data/dakota.db`.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.campaign.models import (
    CampaignEvent,
    CampaignRecord,
    CampaignStatus,
    CampaignSummary,
    CampaignTier,
)
from src.tipcheck.privacy import fingerprint

logger = logging.getLogger("dakota.campaign.store")

BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = BASE_DIR / "data" / "dakota.db"


class TipStore:
    """Privacy-preserving tip store. Retained for backwards compatibility."""

    def __init__(self, path: str | Path = DB_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tip_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    ts TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    source_label TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tip_ticker_ts ON tip_events(ticker, ts)"
            )
            conn.commit()

    def add(self, ticker: str, clean_text: str, source_label: str) -> dict[str, Any]:
        fp = fingerprint(clean_text)
        ts = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO tip_events (ticker, ts, fingerprint, source_label) VALUES (?, ?, ?, ?)",
                (ticker.upper().strip(), ts, fp, source_label[:64]),
            )
            conn.commit()
        return {"ticker": ticker.upper().strip(), "ts": ts, "fingerprint": fp, "source_label": source_label[:64]}

    def recent(self, ticker: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT ticker, ts, fingerprint, source_label FROM tip_events WHERE ticker = ? ORDER BY id DESC LIMIT ?",
                (ticker.upper().strip(), int(limit)),
            ).fetchall()
        return [dict(row) for row in rows]

    def fingerprint_count(self, ticker: str, fp: str, limit: int = 100) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM tip_events WHERE ticker = ? AND fingerprint = ?",
                (ticker.upper().strip(), fp),
            ).fetchone()
        return int(row["c"] if row else 0)


class CampaignStore:
    """Thread-safe persistent store for multi-scrip campaigns and investigation events."""

    _lock = threading.Lock()

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        """Initialize campaigns, campaign_events, and tip_events tables."""
        with self._lock:
            with self._connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tip_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ticker TEXT NOT NULL,
                        ts TEXT NOT NULL,
                        fingerprint TEXT NOT NULL,
                        source_label TEXT NOT NULL
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tip_ticker_ts ON tip_events(ticker, ts)"
                )

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS campaigns (
                        campaign_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'active',
                        tier TEXT NOT NULL DEFAULT 'CANDIDATE',
                        confidence_score REAL NOT NULL DEFAULT 0.5,
                        securities TEXT NOT NULL,
                        actors TEXT NOT NULL,
                        relationship_types TEXT NOT NULL,
                        relationship_explanations TEXT NOT NULL,
                        evidence_ids TEXT NOT NULL,
                        alert_ids TEXT NOT NULL,
                        shared_urls TEXT NOT NULL,
                        shared_fingerprints TEXT NOT NULL,
                        time_window_hours INTEGER NOT NULL DEFAULT 24,
                        first_seen TEXT,
                        last_seen TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        notes TEXT DEFAULT '',
                        acknowledged_at TEXT,
                        resolved_at TEXT,
                        dismissed_at TEXT,
                        jev_assessment TEXT,
                        contradictions TEXT
                    )
                    """
                )

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS campaign_events (
                        event_id TEXT PRIMARY KEY,
                        campaign_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        ticker TEXT NOT NULL,
                        source_label TEXT NOT NULL,
                        event_timestamp TEXT NOT NULL,
                        retrieved_at TEXT NOT NULL,
                        data_freshness TEXT DEFAULT 'LIVE',
                        summary TEXT NOT NULL,
                        metadata TEXT,
                        FOREIGN KEY(campaign_id) REFERENCES campaigns(campaign_id)
                    )
                    """
                )

                # Indices
                cur.execute("CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns(status)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_campaigns_tier ON campaigns(tier)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_campaigns_updated ON campaigns(updated_at)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_campaign_events_cid ON campaign_events(campaign_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_campaign_events_ts ON campaign_events(event_timestamp)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_campaign_events_ticker ON campaign_events(ticker)")
                conn.commit()

    def _row_to_campaign(self, row: sqlite3.Row, include_events: bool = False) -> CampaignRecord:
        d = dict(row)
        return CampaignRecord(
            campaign_id=d["campaign_id"],
            name=d["name"],
            status=CampaignStatus(d["status"]),
            tier=CampaignTier(d["tier"]),
            confidence_score=float(d["confidence_score"]),
            securities=json.loads(d["securities"]) if d["securities"] else [],
            actors=json.loads(d["actors"]) if d["actors"] else [],
            relationship_types=json.loads(d["relationship_types"]) if d["relationship_types"] else [],
            relationship_explanations=json.loads(d["relationship_explanations"]) if d["relationship_explanations"] else {},
            evidence_ids=json.loads(d["evidence_ids"]) if d["evidence_ids"] else [],
            alert_ids=json.loads(d["alert_ids"]) if d["alert_ids"] else [],
            shared_urls=json.loads(d["shared_urls"]) if d["shared_urls"] else [],
            shared_fingerprints=json.loads(d["shared_fingerprints"]) if d["shared_fingerprints"] else [],
            time_window_hours=int(d["time_window_hours"] or 24),
            first_seen=d["first_seen"],
            last_seen=d["last_seen"],
            created_at=d["created_at"],
            updated_at=d["updated_at"],
            notes=d.get("notes") or "",
            acknowledged_at=d.get("acknowledged_at"),
            resolved_at=d.get("resolved_at"),
            dismissed_at=d.get("dismissed_at"),
            jev_assessment=json.loads(d["jev_assessment"]) if d.get("jev_assessment") else None,
            contradictions=json.loads(d["contradictions"]) if d.get("contradictions") else [],
            events=self.get_events_for_campaign(d["campaign_id"]) if include_events else [],
        )

    def _row_to_event(self, row: sqlite3.Row) -> CampaignEvent:
        d = dict(row)
        return CampaignEvent(
            event_id=d["event_id"],
            campaign_id=d["campaign_id"],
            event_type=d["event_type"],
            ticker=d["ticker"],
            source_label=d["source_label"],
            event_timestamp=d["event_timestamp"],
            retrieved_at=d["retrieved_at"],
            data_freshness=d.get("data_freshness") or "LIVE",
            summary=d["summary"],
            metadata=json.loads(d["metadata"]) if d.get("metadata") else {},
        )

    def save_campaign(self, campaign: CampaignRecord) -> CampaignRecord:
        """Insert or update a campaign record."""
        now_iso = datetime.now(timezone.utc).isoformat()
        campaign.updated_at = now_iso

        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO campaigns (
                        campaign_id, name, status, tier, confidence_score,
                        securities, actors, relationship_types, relationship_explanations,
                        evidence_ids, alert_ids, shared_urls, shared_fingerprints,
                        time_window_hours, first_seen, last_seen, created_at, updated_at,
                        notes, acknowledged_at, resolved_at, dismissed_at,
                        jev_assessment, contradictions
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(campaign_id) DO UPDATE SET
                        name=excluded.name,
                        status=excluded.status,
                        tier=excluded.tier,
                        confidence_score=excluded.confidence_score,
                        securities=excluded.securities,
                        actors=excluded.actors,
                        relationship_types=excluded.relationship_types,
                        relationship_explanations=excluded.relationship_explanations,
                        evidence_ids=excluded.evidence_ids,
                        alert_ids=excluded.alert_ids,
                        shared_urls=excluded.shared_urls,
                        shared_fingerprints=excluded.shared_fingerprints,
                        time_window_hours=excluded.time_window_hours,
                        first_seen=excluded.first_seen,
                        last_seen=excluded.last_seen,
                        updated_at=excluded.updated_at,
                        notes=excluded.notes,
                        acknowledged_at=excluded.acknowledged_at,
                        resolved_at=excluded.resolved_at,
                        dismissed_at=excluded.dismissed_at,
                        jev_assessment=excluded.jev_assessment,
                        contradictions=excluded.contradictions
                    """,
                    (
                        campaign.campaign_id,
                        campaign.name,
                        campaign.status.value,
                        campaign.tier.value,
                        campaign.confidence_score,
                        json.dumps(sorted(list(set(campaign.securities)))),
                        json.dumps(sorted(list(set(campaign.actors)))),
                        json.dumps(campaign.relationship_types),
                        json.dumps(campaign.relationship_explanations),
                        json.dumps(campaign.evidence_ids),
                        json.dumps(campaign.alert_ids),
                        json.dumps(campaign.shared_urls),
                        json.dumps(campaign.shared_fingerprints),
                        campaign.time_window_hours,
                        campaign.first_seen,
                        campaign.last_seen,
                        campaign.created_at,
                        campaign.updated_at,
                        campaign.notes,
                        campaign.acknowledged_at,
                        campaign.resolved_at,
                        campaign.dismissed_at,
                        json.dumps(campaign.jev_assessment) if campaign.jev_assessment else None,
                        json.dumps(campaign.contradictions),
                    ),
                )
                conn.commit()

        # Save any unpersisted events attached to this record
        if campaign.events:
            for ev in campaign.events:
                self.add_event(ev)

        return campaign

    def get_campaign(self, campaign_id: str, include_events: bool = True) -> CampaignRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM campaigns WHERE campaign_id = ?", (campaign_id,)).fetchone()
            if not row:
                return None
            return self._row_to_campaign(row, include_events=include_events)

    def list_campaigns(
        self,
        status: str | None = None,
        tier: str | None = None,
        ticker: str | None = None,
        limit: int = 50,
    ) -> list[CampaignRecord]:
        query = "SELECT * FROM campaigns WHERE 1=1"
        params: list[Any] = []

        if status:
            query += " AND status = ?"
            params.append(status.lower().strip())
        if tier:
            query += " AND tier = ?"
            params.append(tier.upper().strip())
        if ticker:
            clean_ticker = ticker.upper().strip()
            query += " AND (securities LIKE ? OR securities LIKE ?)"
            params.append(f'%"{clean_ticker}"%')
            params.append(f"%{clean_ticker}%")

        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(int(limit))

        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            return [self._row_to_campaign(r, include_events=False) for r in rows]

    def add_event(self, event: CampaignEvent) -> bool:
        """Add an event to the campaign timeline. Idempotent based on event_id."""
        with self._lock:
            with self._connect() as conn:
                try:
                    conn.execute(
                        """
                        INSERT INTO campaign_events (
                            event_id, campaign_id, event_type, ticker, source_label,
                            event_timestamp, retrieved_at, data_freshness, summary, metadata
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(event_id) DO NOTHING
                        """,
                        (
                            event.event_id,
                            event.campaign_id,
                            event.event_type,
                            event.ticker.upper().strip(),
                            event.source_label,
                            event.event_timestamp,
                            event.retrieved_at,
                            event.data_freshness,
                            event.summary,
                            json.dumps(event.metadata),
                        ),
                    )
                    conn.commit()
                    return True
                except Exception as exc:
                    logger.debug("Failed adding campaign event %s: %s", event.event_id, exc)
                    return False

    def get_events_for_campaign(self, campaign_id: str, limit: int = 100) -> list[CampaignEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM campaign_events
                WHERE campaign_id = ?
                ORDER BY event_timestamp ASC
                LIMIT ?
                """,
                (campaign_id, int(limit)),
            ).fetchall()
            return [self._row_to_event(r) for r in rows]

    def update_status(self, campaign_id: str, status: CampaignStatus, note: str = "") -> bool:
        """Update campaign status with timestamp tracking."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT * FROM campaigns WHERE campaign_id = ?", (campaign_id,)).fetchone()
                if not row:
                    return False

                updates = ["status = ?", "updated_at = ?"]
                params: list[Any] = [status.value, now_iso]

                if status == CampaignStatus.ACTIVE and not row["acknowledged_at"]:
                    updates.append("acknowledged_at = ?")
                    params.append(now_iso)
                elif status == CampaignStatus.RESOLVED:
                    updates.append("resolved_at = ?")
                    params.append(now_iso)
                elif status == CampaignStatus.DISMISSED:
                    updates.append("dismissed_at = ?")
                    params.append(now_iso)

                if note:
                    existing_notes = row["notes"] or ""
                    new_notes = f"{existing_notes}\n[{now_iso}] {note}".strip() if existing_notes else f"[{now_iso}] {note}"
                    updates.append("notes = ?")
                    params.append(new_notes)

                params.append(campaign_id)
                query = f"UPDATE campaigns SET {', '.join(updates)} WHERE campaign_id = ?"
                conn.execute(query, tuple(params))

                # Append action event
                conn.execute(
                    """
                    INSERT INTO campaign_events (
                        event_id, campaign_id, event_type, ticker, source_label,
                        event_timestamp, retrieved_at, data_freshness, summary, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"act_{campaign_id[:8]}_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:6]}",
                        campaign_id,
                        "action",
                        "ALL",
                        "investigator",
                        now_iso,
                        now_iso,
                        "LIVE",
                        f"Campaign status updated to {status.value.upper()}" + (f": {note}" if note else ""),
                        json.dumps({"status": status.value, "note": note}),
                    ),
                )
                conn.commit()
                return True

    def add_note(self, campaign_id: str, note: str) -> bool:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT notes FROM campaigns WHERE campaign_id = ?", (campaign_id,)).fetchone()
                if not row:
                    return False
                existing = row["notes"] or ""
                new_note = f"{existing}\n[{now_iso}] {note}".strip() if existing else f"[{now_iso}] {note}"
                conn.execute(
                    "UPDATE campaigns SET notes = ?, updated_at = ? WHERE campaign_id = ?",
                    (new_note, now_iso, campaign_id),
                )
                conn.commit()
                return True

    def get_summary(self) -> CampaignSummary:
        """Compute operational summary metrics across campaigns."""
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT status, tier, securities, actors, updated_at FROM campaigns")
            rows = cur.fetchall()

            total = len(rows)
            active = sum(1 for r in rows if r["status"] == "active")
            monitoring = sum(1 for r in rows if r["status"] == "monitoring")
            resolved = sum(1 for r in rows if r["status"] == "resolved")
            dismissed = sum(1 for r in rows if r["status"] == "dismissed")
            high = sum(1 for r in rows if r["tier"] == "HIGH")
            moderate = sum(1 for r in rows if r["tier"] == "MODERATE")
            candidate = sum(1 for r in rows if r["tier"] == "CANDIDATE")

            all_securities: set[str] = set()
            all_actors: set[str] = set()
            latest_update: str | None = None

            for r in rows:
                if r["securities"]:
                    try:
                        all_securities.update(json.loads(r["securities"]))
                    except Exception:
                        pass
                if r["actors"]:
                    try:
                        all_actors.update(json.loads(r["actors"]))
                    except Exception:
                        pass
                if r["updated_at"]:
                    if not latest_update or r["updated_at"] > latest_update:
                        latest_update = r["updated_at"]

            return CampaignSummary(
                total_campaigns=total,
                active_count=active,
                monitoring_count=monitoring,
                resolved_count=resolved,
                dismissed_count=dismissed,
                high_tier_count=high,
                moderate_tier_count=moderate,
                candidate_tier_count=candidate,
                total_securities_involved=len(all_securities),
                total_actors_tracked=len(all_actors),
                last_updated=latest_update,
            )


campaign_store = CampaignStore()
