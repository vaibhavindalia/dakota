"""Persistent SQLite storage layer for Dakota's Alert Engine."""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.alerts.models import AlertRecord, AlertRule, AlertRuleType, AlertSeverity, AlertStatus, AlertSummary

logger = logging.getLogger("dakota.alerts.store")

BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = BASE_DIR / "data" / "dakota.db"


class AlertStore:
    """Thread-safe persistent store for alert rules, generated alerts, and delivery receipts."""

    _lock = threading.Lock()

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        """Initialize database tables and default rules."""
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("""
                CREATE TABLE IF NOT EXISTS alert_rules (
                    rule_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    rule_type TEXT NOT NULL,
                    condition TEXT NOT NULL,
                    threshold REAL,
                    threshold_str TEXT,
                    severity TEXT NOT NULL DEFAULT 'warning',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    cooldown_seconds INTEGER NOT NULL DEFAULT 300,
                    notify_terminal INTEGER NOT NULL DEFAULT 1,
                    notify_telegram INTEGER NOT NULL DEFAULT 0,
                    auto_investigate INTEGER NOT NULL DEFAULT 0,
                    last_triggered_at TEXT,
                    last_evaluated_at TEXT,
                    trigger_count INTEGER NOT NULL DEFAULT 0,
                    is_triggered INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """)

                cur.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    alert_id TEXT PRIMARY KEY,
                    rule_id TEXT NOT NULL,
                    rule_name TEXT NOT NULL,
                    rule_type TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    trigger_value REAL,
                    trigger_value_str TEXT,
                    threshold_value REAL,
                    threshold_value_str TEXT,
                    observation_timestamp TEXT,
                    retrieved_at TEXT,
                    data_freshness TEXT,
                    feed_type TEXT,
                    dedup_key TEXT UNIQUE,
                    evidence_context TEXT,
                    jev_assessment TEXT,
                    created_at TEXT NOT NULL,
                    acknowledged_at TEXT,
                    dismissed_at TEXT,
                    resolved_at TEXT,
                    telegram_delivery_status TEXT DEFAULT 'not_configured',
                    telegram_message_id TEXT,
                    telegram_error TEXT
                );
                """)

                cur.execute("""
                CREATE TABLE IF NOT EXISTS alert_deliveries (
                    delivery_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alert_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt_timestamp TEXT NOT NULL,
                    payload TEXT,
                    response_or_error TEXT
                );
                """)

                # Indices for fast queries
                cur.execute("CREATE INDEX IF NOT EXISTS idx_alerts_ticker ON alerts(ticker);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_alert_rules_enabled ON alert_rules(enabled);")
                conn.commit()

                # Seed default rules if table is empty
                cur.execute("SELECT COUNT(*) FROM alert_rules;")
                count = cur.fetchone()[0]
                if count == 0:
                    self._seed_default_rules(cur)
                    conn.commit()
            finally:
                conn.close()

    def _seed_default_rules(self, cur: sqlite3.Cursor) -> None:
        """Seed established forensic alert rules for Indian market monitoring."""
        now_iso = datetime.now(timezone.utc).isoformat()
        default_rules = [
            (
                "rule_portfolio_risk_high",
                "High Risk Score Threshold (Portfolio)",
                "*",
                "portfolio",
                "risk_threshold",
                ">=",
                70.0,
                None,
                "critical",
                1,
                300,
                1,
                0,
                1,
                None,
                None,
                0,
                0,
                now_iso,
                now_iso,
            ),
            (
                "rule_portfolio_risk_elevated",
                "Elevated Risk Score Threshold (Portfolio)",
                "*",
                "portfolio",
                "risk_threshold",
                ">=",
                40.0,
                None,
                "warning",
                1,
                600,
                1,
                0,
                0,
                None,
                None,
                0,
                0,
                now_iso,
                now_iso,
            ),
            (
                "rule_portfolio_drawdown",
                "Severe Single-Session Drawdown (<= -5%)",
                "*",
                "portfolio",
                "price_change_pct",
                "<=",
                -5.0,
                None,
                "warning",
                1,
                300,
                1,
                0,
                0,
                None,
                None,
                0,
                0,
                now_iso,
                now_iso,
            ),
            (
                "rule_universe_volume_surge",
                "Abnormal Volume Spike (>= 2.5x 20d Average)",
                "*",
                "universe",
                "abnormal_volume",
                ">=",
                2.5,
                None,
                "info",
                1,
                900,
                1,
                0,
                0,
                None,
                None,
                0,
                0,
                now_iso,
                now_iso,
            ),
            (
                "rule_universe_low_delivery",
                "Low Delivery Surge / Pump Marker (<= 20% Delivery)",
                "*",
                "universe",
                "delivery_volume_drop",
                "<=",
                20.0,
                None,
                "critical",
                1,
                600,
                1,
                0,
                1,
                None,
                None,
                0,
                0,
                now_iso,
                now_iso,
            ),
            (
                "rule_universe_surveillance",
                "Exchange Surveillance Action (GSM/ASM/ESM)",
                "*",
                "universe",
                "surveillance_event",
                "==",
                None,
                "active",
                "critical",
                1,
                1800,
                1,
                0,
                1,
                None,
                None,
                0,
                0,
                now_iso,
                now_iso,
            ),
            (
                "rule_portfolio_staleness",
                "Market Telemetry Feed Stale (>= 10 Minutes)",
                "*",
                "portfolio",
                "data_staleness",
                ">=",
                600.0,
                None,
                "warning",
                1,
                900,
                1,
                0,
                0,
                None,
                None,
                0,
                0,
                now_iso,
                now_iso,
            ),
        ]

        cur.executemany("""
        INSERT INTO alert_rules (
            rule_id, name, ticker, scope, rule_type, condition, threshold, threshold_str,
            severity, enabled, cooldown_seconds, notify_terminal, notify_telegram, auto_investigate,
            last_triggered_at, last_evaluated_at, trigger_count, is_triggered, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, default_rules)
        logger.info("Seeded %d default forensic alert rules.", len(default_rules))

    # --------------------------------------------------------------------------
    # Rule Management Methods
    # --------------------------------------------------------------------------

    def get_rules(self, enabled_only: bool = False) -> list[AlertRule]:
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                if enabled_only:
                    cur.execute("SELECT * FROM alert_rules WHERE enabled = 1 ORDER BY created_at ASC;")
                else:
                    cur.execute("SELECT * FROM alert_rules ORDER BY created_at ASC;")
                rows = cur.fetchall()
                return [self._row_to_rule(r) for r in rows]
            finally:
                conn.close()

    def get_rule(self, rule_id: str) -> AlertRule | None:
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("SELECT * FROM alert_rules WHERE rule_id = ?;", (rule_id,))
                row = cur.fetchone()
                return self._row_to_rule(row) if row else None
            finally:
                conn.close()

    def save_rule(self, rule: AlertRule) -> None:
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("""
                INSERT INTO alert_rules (
                    rule_id, name, ticker, scope, rule_type, condition, threshold, threshold_str,
                    severity, enabled, cooldown_seconds, notify_terminal, notify_telegram, auto_investigate,
                    last_triggered_at, last_evaluated_at, trigger_count, is_triggered, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(rule_id) DO UPDATE SET
                    name = excluded.name,
                    ticker = excluded.ticker,
                    scope = excluded.scope,
                    rule_type = excluded.rule_type,
                    condition = excluded.condition,
                    threshold = excluded.threshold,
                    threshold_str = excluded.threshold_str,
                    severity = excluded.severity,
                    enabled = excluded.enabled,
                    cooldown_seconds = excluded.cooldown_seconds,
                    notify_terminal = excluded.notify_terminal,
                    notify_telegram = excluded.notify_telegram,
                    auto_investigate = excluded.auto_investigate,
                    last_triggered_at = excluded.last_triggered_at,
                    last_evaluated_at = excluded.last_evaluated_at,
                    trigger_count = excluded.trigger_count,
                    is_triggered = excluded.is_triggered,
                    updated_at = excluded.updated_at;
                """, (
                    rule.rule_id, rule.name, rule.ticker.upper().strip(), rule.scope,
                    rule.rule_type.value if hasattr(rule.rule_type, "value") else str(rule.rule_type),
                    rule.condition, rule.threshold, rule.threshold_str,
                    rule.severity.value if hasattr(rule.severity, "value") else str(rule.severity),
                    1 if rule.enabled else 0, rule.cooldown_seconds,
                    1 if rule.notify_terminal else 0, 1 if rule.notify_telegram else 0,
                    1 if rule.auto_investigate else 0,
                    rule.last_triggered_at, rule.last_evaluated_at, rule.trigger_count,
                    1 if rule.is_triggered else 0, rule.created_at, rule.updated_at,
                ))
                conn.commit()
            finally:
                conn.close()

    def delete_rule(self, rule_id: str) -> bool:
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("DELETE FROM alert_rules WHERE rule_id = ?;", (rule_id,))
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def update_rule_evaluation_state(
        self,
        rule_id: str,
        last_evaluated_at: str,
        is_triggered: bool | None = None,
        last_triggered_at: str | None = None,
        increment_trigger: bool = False,
    ) -> None:
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                sql = "UPDATE alert_rules SET last_evaluated_at = ?"
                params: list[Any] = [last_evaluated_at]

                if is_triggered is not None:
                    sql += ", is_triggered = ?"
                    params.append(1 if is_triggered else 0)

                if last_triggered_at is not None:
                    sql += ", last_triggered_at = ?"
                    params.append(last_triggered_at)

                if increment_trigger:
                    sql += ", trigger_count = trigger_count + 1"

                sql += " WHERE rule_id = ?;"
                params.append(rule_id)
                cur.execute(sql, params)
                conn.commit()
            finally:
                conn.close()

    # --------------------------------------------------------------------------
    # Alert Record Management Methods
    # --------------------------------------------------------------------------

    def save_alert(self, alert: AlertRecord) -> bool:
        """Insert a newly fired alert into database. Returns True if inserted, False if deduped."""
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("""
                INSERT OR IGNORE INTO alerts (
                    alert_id, rule_id, rule_name, rule_type, ticker, severity, status,
                    title, message, trigger_value, trigger_value_str, threshold_value,
                    threshold_value_str, observation_timestamp, retrieved_at, data_freshness,
                    feed_type, dedup_key, evidence_context, jev_assessment, created_at,
                    acknowledged_at, dismissed_at, resolved_at, telegram_delivery_status,
                    telegram_message_id, telegram_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    alert.alert_id, alert.rule_id, alert.rule_name, alert.rule_type,
                    alert.ticker.upper().strip(),
                    alert.severity.value if hasattr(alert.severity, "value") else str(alert.severity),
                    alert.status.value if hasattr(alert.status, "value") else str(alert.status),
                    alert.title, alert.message, alert.trigger_value, alert.trigger_value_str,
                    alert.threshold_value, alert.threshold_value_str,
                    alert.observation_timestamp, alert.retrieved_at, alert.data_freshness,
                    alert.feed_type, alert.dedup_key,
                    json.dumps(alert.evidence_context),
                    json.dumps(alert.jev_assessment) if alert.jev_assessment else None,
                    alert.created_at, alert.acknowledged_at, alert.dismissed_at, alert.resolved_at,
                    alert.telegram_delivery_status, alert.telegram_message_id, alert.telegram_error,
                ))
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def is_dedup_key_present(self, dedup_key: str) -> bool:
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("SELECT 1 FROM alerts WHERE dedup_key = ? LIMIT 1;", (dedup_key,))
                return cur.fetchone() is not None
            finally:
                conn.close()

    def get_alert(self, alert_id: str) -> AlertRecord | None:
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("SELECT * FROM alerts WHERE alert_id = ?;", (alert_id,))
                row = cur.fetchone()
                return self._row_to_alert(row) if row else None
            finally:
                conn.close()

    def get_alerts(
        self,
        status: str | None = None,
        severity: str | None = None,
        ticker: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AlertRecord]:
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                clauses = []
                params: list[Any] = []

                if status and status.lower() != "all":
                    clauses.append("status = ?")
                    params.append(status.lower())

                if severity and severity.lower() != "all":
                    clauses.append("severity = ?")
                    params.append(severity.lower())

                if ticker and ticker.strip():
                    clauses.append("ticker = ?")
                    params.append(ticker.upper().strip())

                where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
                sql = f"SELECT * FROM alerts {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?;"
                params.extend([limit, offset])

                cur.execute(sql, params)
                rows = cur.fetchall()
                return [self._row_to_alert(r) for r in rows]
            finally:
                conn.close()

    def update_alert_status(self, alert_id: str, new_status: AlertStatus) -> bool:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                if new_status == AlertStatus.ACKNOWLEDGED:
                    cur.execute(
                        "UPDATE alerts SET status = ?, acknowledged_at = ? WHERE alert_id = ?;",
                        (new_status.value, now_iso, alert_id),
                    )
                elif new_status == AlertStatus.DISMISSED:
                    cur.execute(
                        "UPDATE alerts SET status = ?, dismissed_at = ? WHERE alert_id = ?;",
                        (new_status.value, now_iso, alert_id),
                    )
                elif new_status == AlertStatus.RESOLVED:
                    cur.execute(
                        "UPDATE alerts SET status = ?, resolved_at = ? WHERE alert_id = ?;",
                        (new_status.value, now_iso, alert_id),
                    )
                else:
                    cur.execute(
                        "UPDATE alerts SET status = ? WHERE alert_id = ?;",
                        (new_status.value, alert_id),
                    )
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def update_alert_telegram_status(
        self,
        alert_id: str,
        status: str,
        message_id: str | None = None,
        error: str | None = None,
    ) -> None:
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("""
                UPDATE alerts SET
                    telegram_delivery_status = ?,
                    telegram_message_id = ?,
                    telegram_error = ?
                WHERE alert_id = ?;
                """, (status, message_id, error, alert_id))

                cur.execute("""
                INSERT INTO alert_deliveries (
                    alert_id, channel, status, attempt_timestamp, payload, response_or_error
                ) VALUES (?, ?, ?, ?, ?, ?);
                """, (
                    alert_id,
                    "telegram",
                    status,
                    datetime.now(timezone.utc).isoformat(),
                    None,
                    message_id or error,
                ))
                conn.commit()
            finally:
                conn.close()

    def get_summary(self) -> AlertSummary:
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM alerts;")
                total = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM alerts WHERE status = 'active';")
                active = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM alerts WHERE status = 'active' AND severity = 'critical';")
                critical = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM alerts WHERE status = 'active' AND severity = 'warning';")
                warning = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM alerts WHERE status = 'active' AND severity = 'info';")
                info = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM alert_rules WHERE enabled = 1;")
                active_rules = cur.fetchone()[0]

                cur.execute("SELECT MAX(created_at) FROM alerts;")
                last_time = cur.fetchone()[0]

                return AlertSummary(
                    total_alerts=total,
                    active_alerts=active,
                    unread_alerts=active,
                    critical_count=critical,
                    warning_count=warning,
                    info_count=info,
                    active_rules=active_rules,
                    last_evaluation_time=last_time,
                    engine_status="running",
                )
            finally:
                conn.close()

    # --------------------------------------------------------------------------
    # Row Helpers
    # --------------------------------------------------------------------------

    def _row_to_rule(self, row: sqlite3.Row) -> AlertRule:
        return AlertRule(
            rule_id=row["rule_id"],
            name=row["name"],
            ticker=row["ticker"],
            scope=row["scope"],
            rule_type=AlertRuleType(row["rule_type"]),
            condition=row["condition"],
            threshold=row["threshold"],
            threshold_str=row["threshold_str"],
            severity=AlertSeverity(row["severity"]),
            enabled=bool(row["enabled"]),
            cooldown_seconds=row["cooldown_seconds"],
            notify_terminal=bool(row["notify_terminal"]),
            notify_telegram=bool(row["notify_telegram"]),
            auto_investigate=bool(row["auto_investigate"]),
            last_triggered_at=row["last_triggered_at"],
            last_evaluated_at=row["last_evaluated_at"],
            trigger_count=row["trigger_count"],
            is_triggered=bool(row["is_triggered"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_alert(self, row: sqlite3.Row) -> AlertRecord:
        ctx_raw = row["evidence_context"]
        evidence_ctx = json.loads(ctx_raw) if ctx_raw else {}
        jev_raw = row["jev_assessment"]
        jev_ctx = json.loads(jev_raw) if jev_raw else None

        return AlertRecord(
            alert_id=row["alert_id"],
            rule_id=row["rule_id"],
            rule_name=row["rule_name"],
            rule_type=row["rule_type"],
            ticker=row["ticker"],
            severity=AlertSeverity(row["severity"]),
            status=AlertStatus(row["status"]),
            title=row["title"],
            message=row["message"],
            trigger_value=row["trigger_value"],
            trigger_value_str=row["trigger_value_str"],
            threshold_value=row["threshold_value"],
            threshold_value_str=row["threshold_value_str"],
            observation_timestamp=row["observation_timestamp"],
            retrieved_at=row["retrieved_at"],
            data_freshness=row["data_freshness"] or "cached",
            feed_type=row["feed_type"] or "intraday_snapshot_5m",
            dedup_key=row["dedup_key"],
            evidence_context=evidence_ctx,
            jev_assessment=jev_ctx,
            created_at=row["created_at"],
            acknowledged_at=row["acknowledged_at"],
            dismissed_at=row["dismissed_at"],
            resolved_at=row["resolved_at"],
            telegram_delivery_status=row["telegram_delivery_status"] or "not_configured",
            telegram_message_id=row["telegram_message_id"],
            telegram_error=row["telegram_error"],
        )


alert_store = AlertStore()
