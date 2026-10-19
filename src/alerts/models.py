"""Data models and schemas for Dakota's Automated Alerting and Intelligent Monitoring Engine."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    DISMISSED = "dismissed"
    RESOLVED = "resolved"


class AlertRuleType(str, Enum):
    RISK_THRESHOLD = "risk_threshold"                  # e.g., forensic risk score >= 70
    PRICE_CHANGE_PCT = "price_change_pct"              # e.g., 1-day/session change >= 5% or <= -5%
    PRICE_LEVEL = "price_level"                        # e.g., price crosses above/below target level
    ABNORMAL_VOLUME = "abnormal_volume"                # e.g., volume >= 2.5x 20d average volume
    DELIVERY_VOLUME_DROP = "delivery_volume_drop"      # e.g., volume surge with delivery pct <= 20% (pump marker)
    SURVEILLANCE_EVENT = "surveillance_event"          # e.g., security entered GSM/ASM/ESM framework
    MATERIAL_DISCLOSURE = "material_disclosure"        # e.g., new SEBI order or material exchange disclosure
    DATA_STALENESS = "data_staleness"                  # e.g., data feed stale for >= 600s


class AlertRule(BaseModel):
    rule_id: str
    name: str
    ticker: str = Field(default="*", description="Ticker symbol or '*' for all portfolio / universe")
    scope: Literal["ticker", "portfolio", "universe"] = "portfolio"
    rule_type: AlertRuleType
    condition: Literal[">=", "<=", "==", "crosses_above", "crosses_below"] = ">="
    threshold: float | None = None
    threshold_str: str | None = None
    severity: AlertSeverity = AlertSeverity.WARNING
    enabled: bool = True
    cooldown_seconds: int = Field(default=300, description="Minimum seconds before re-triggering for same condition")
    notify_terminal: bool = True
    notify_telegram: bool = False
    auto_investigate: bool = Field(default=False, description="Trigger JEV contextual analysis for critical breach")
    last_triggered_at: str | None = None
    last_evaluated_at: str | None = None
    trigger_count: int = 0
    is_triggered: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AlertRecord(BaseModel):
    alert_id: str
    rule_id: str
    rule_name: str
    rule_type: str
    ticker: str
    severity: AlertSeverity = AlertSeverity.WARNING
    status: AlertStatus = AlertStatus.ACTIVE
    title: str
    message: str
    trigger_value: float | None = None
    trigger_value_str: str | None = None
    threshold_value: float | None = None
    threshold_value_str: str | None = None
    observation_timestamp: str | None = None
    retrieved_at: str | None = None
    data_freshness: str = "cached"
    feed_type: str = "intraday_snapshot_5m"
    dedup_key: str
    evidence_context: dict[str, Any] = Field(default_factory=dict)
    jev_assessment: dict[str, Any] | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    acknowledged_at: str | None = None
    dismissed_at: str | None = None
    resolved_at: str | None = None
    telegram_delivery_status: Literal["not_configured", "pending", "sent", "failed", "missing_credentials"] = "not_configured"
    telegram_message_id: str | None = None
    telegram_error: str | None = None


class AlertSummary(BaseModel):
    total_alerts: int = 0
    active_alerts: int = 0
    unread_alerts: int = 0
    critical_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    active_rules: int = 0
    last_evaluation_time: str | None = None
    engine_status: str = "running"
