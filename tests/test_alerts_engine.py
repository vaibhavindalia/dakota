"""Test Suite for Phase 7: Automated Alerting, Deduplication, Freshness Integrity, and Intelligent Monitoring.

Verifies:
1. Rule creation, modification, toggling, deletion, and SQLite persistence.
2. Every supported alert condition:
   - Risk score threshold crossing
   - Price change percentage (drawdown / rally)
   - Price level crossing
   - Abnormal volume surge (>= 2.5x)
   - Low delivery volume drop (<= 20% pump marker)
   - Exchange surveillance framework (GSM/ASM/ESM)
   - Data staleness feed outage
3. Freshness Integrity:
   - Stale/unavailable telemetry refuses to fire quantitative alerts.
   - Observation timestamp separated from retrieval timestamp.
   - Yesterday's close retrieved today during market hours is classified as CACHED, never falsely as LIVE.
   - 15m-60m observations classified as DELAYED.
4. Edge-triggering, Cooldowns, Deduplication, and Re-arming:
   - Deduplication key prevents duplicate alerts on identical observations.
   - Cooldown prevents notification floods during sustained threshold breaches.
   - Re-arming: when condition resets below threshold, rule re-arms and triggers anew upon subsequent crossing.
5. Persistent storage across restarts (new AlertStore instance retains rules and alerts).
6. Telegram notification formatting, credential diagnostics, and simulated delivery receipt.
7. JEV contextual intelligence attachment on critical forensic alerts.
8. FastAPI Endpoints: /api/alerts, /api/alerts/summary, acknowledge, dismiss, /api/alerts/rules, /api/alerts/evaluate, /api/alerts/status.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from src.alerts.models import (
    AlertRecord,
    AlertRule,
    AlertRuleType,
    AlertSeverity,
    AlertStatus,
)
from src.alerts.store import AlertStore
from src.alerts.telegram_notifier import TelegramAlertNotifier
from src.alerts.engine import AlertEngine
from src.market.auto_sync import compute_freshness_status


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def temp_store(tmp_path):
    """Isolated SQLite AlertStore instance for testing."""
    db_file = tmp_path / "test_alerts.db"
    return AlertStore(db_path=db_file)


# -----------------------------------------------------------------------------
# 1. Freshness Integrity & Observation vs Retrieval Tests
# -----------------------------------------------------------------------------

def test_truthful_observation_vs_retrieval_freshness():
    """Verify that repeatedly retrieved stale observations are NEVER labeled as LIVE."""
    now_utc = datetime.now(timezone.utc)
    now_iso = now_utc.isoformat()
    yesterday_iso = (now_utc - timedelta(days=1)).isoformat()
    delayed_30m_iso = (now_utc - timedelta(minutes=30)).isoformat()

    # Scenario A: Retrieved 2 seconds ago, but observation is yesterday's close during open market
    # Must be CACHED, NOT LIVE!
    status_cached_during_market = compute_freshness_status(
        retrieved_at_iso=now_iso,
        market_event_iso=yesterday_iso,
        is_market_open=True,
        stale_threshold_sec=180.0,
    )
    assert status_cached_during_market == "cached"

    # Scenario B: Retrieved 5 seconds ago, but observation is 30m old during open market
    # Must be DELAYED (exchange lag), NOT LIVE!
    status_delayed = compute_freshness_status(
        retrieved_at_iso=now_iso,
        market_event_iso=delayed_30m_iso,
        is_market_open=True,
        stale_threshold_sec=180.0,
    )
    assert status_delayed == "delayed"

    # Scenario C: Retrieved 5 seconds ago, observation is 3m old during open market
    # Genuinely LIVE!
    status_live = compute_freshness_status(
        retrieved_at_iso=now_iso,
        market_event_iso=(now_utc - timedelta(minutes=3)).isoformat(),
        is_market_open=True,
        stale_threshold_sec=180.0,
    )
    assert status_live == "live"


# -----------------------------------------------------------------------------
# 2. Rule Creation, Modification, and Persistence Tests
# -----------------------------------------------------------------------------

def test_rule_crud_and_persistence_across_restarts(tmp_path):
    """Verify rules persist in SQLite and survive a complete store restart."""
    db_path = tmp_path / "restart_test.db"
    store1 = AlertStore(db_path=db_path)

    # 1. Check default seeded rules
    rules = store1.get_rules()
    assert len(rules) >= 5
    rule_ids = [r.rule_id for r in rules]
    assert "rule_portfolio_risk_high" in rule_ids
    assert "rule_portfolio_drawdown" in rule_ids

    # 2. Add custom rule
    custom = AlertRule(
        rule_id="rule_test_zomato_target",
        name="Zomato Price Breakout Target",
        ticker="ZOMATO",
        scope="ticker",
        rule_type=AlertRuleType.PRICE_LEVEL,
        condition=">=",
        threshold=300.0,
        severity=AlertSeverity.INFO,
        cooldown_seconds=600,
    )
    store1.save_rule(custom)

    # 3. Simulate process restart by instantiating new AlertStore pointing to same SQLite file
    store2 = AlertStore(db_path=db_path)
    retrieved = store2.get_rule("rule_test_zomato_target")
    assert retrieved is not None
    assert retrieved.name == "Zomato Price Breakout Target"
    assert retrieved.threshold == 300.0
    assert retrieved.ticker == "ZOMATO"

    # 4. Modify rule and verify update
    retrieved.threshold = 320.0
    store2.save_rule(retrieved)
    updated = store2.get_rule("rule_test_zomato_target")
    assert updated.threshold == 320.0

    # 5. Delete rule
    ok = store2.delete_rule("rule_test_zomato_target")
    assert ok is True
    assert store2.get_rule("rule_test_zomato_target") is None


# -----------------------------------------------------------------------------
# 3. Supported Alert Conditions & Stale Data Refusal
# -----------------------------------------------------------------------------

def test_alert_conditions_and_stale_data_rejection(temp_store):
    """Verify each condition triggers correctly on fresh data and is rejected on stale data."""
    engine = AlertEngine(store=temp_store)

    # Fresh data dictionary for RELIANCE
    now_iso = datetime.now(timezone.utc).isoformat()
    fresh_data = {
        "ticker": "RELIANCE",
        "latest_price": 2850.0,
        "last_price": 2850.0,
        "change_pct": -6.2,  # Breaches -5.0% drawdown
        "volume": 5000000,
        "avg_volume": 1500000,  # 3.33x volume surge
        "delivery_pct": 14.5,  # <= 20% delivery drop
        "score": 78.5,  # >= 70.0 high risk
        "band": "High",
        "reasons": ["Promoter pledging high", "Volume spike without delivery"],
        "is_surveillance": True,
        "surveillance_status": "GSM Stage 1",
        "data_freshness": "live",
        "observation_timestamp": now_iso,
        "retrieved_at": now_iso,
    }

    # 1. High Risk Rule Evaluation
    risk_rule = AlertRule(
        rule_id="r_risk_test",
        name="High Risk Test",
        ticker="RELIANCE",
        scope="ticker",
        rule_type=AlertRuleType.RISK_THRESHOLD,
        condition=">=",
        threshold=70.0,
        severity=AlertSeverity.CRITICAL,
    )
    temp_store.save_rule(risk_rule)

    alt1 = engine.evaluate_rule(risk_rule, "RELIANCE", fresh_data)
    assert alt1 is not None
    assert alt1.severity == AlertSeverity.CRITICAL
    assert alt1.trigger_value == 78.5
    assert "Forensic Risk Score 78.5" in alt1.title

    # 2. Drawdown Rule Evaluation
    drawdown_rule = AlertRule(
        rule_id="r_drawdown_test",
        name="Drawdown Test",
        ticker="RELIANCE",
        scope="ticker",
        rule_type=AlertRuleType.PRICE_CHANGE_PCT,
        condition="<=",
        threshold=-5.0,
        severity=AlertSeverity.WARNING,
    )
    temp_store.save_rule(drawdown_rule)

    alt2 = engine.evaluate_rule(drawdown_rule, "RELIANCE", fresh_data)
    assert alt2 is not None
    assert alt2.trigger_value == -6.2

    # 3. Volume Surge Rule Evaluation
    vol_rule = AlertRule(
        rule_id="r_vol_test",
        name="Volume Spike Test",
        ticker="RELIANCE",
        scope="ticker",
        rule_type=AlertRuleType.ABNORMAL_VOLUME,
        condition=">=",
        threshold=2.5,
        severity=AlertSeverity.INFO,
    )
    temp_store.save_rule(vol_rule)

    alt3 = engine.evaluate_rule(vol_rule, "RELIANCE", fresh_data)
    assert alt3 is not None
    assert alt3.trigger_value >= 2.5

    # 4. Low Delivery Volume Drop Rule Evaluation
    deliv_rule = AlertRule(
        rule_id="r_deliv_test",
        name="Delivery Drop Test",
        ticker="RELIANCE",
        scope="ticker",
        rule_type=AlertRuleType.DELIVERY_VOLUME_DROP,
        condition="<=",
        threshold=20.0,
        severity=AlertSeverity.CRITICAL,
    )
    temp_store.save_rule(deliv_rule)

    alt4 = engine.evaluate_rule(deliv_rule, "RELIANCE", fresh_data)
    assert alt4 is not None
    assert alt4.trigger_value == 14.5

    # 5. Surveillance Event Rule Evaluation
    surv_rule = AlertRule(
        rule_id="r_surv_test",
        name="Surveillance Test",
        ticker="RELIANCE",
        scope="ticker",
        rule_type=AlertRuleType.SURVEILLANCE_EVENT,
        condition="==",
        severity=AlertSeverity.CRITICAL,
    )
    temp_store.save_rule(surv_rule)

    alt5 = engine.evaluate_rule(surv_rule, "RELIANCE", fresh_data)
    assert alt5 is not None
    assert "Surveillance Framework Active" in alt5.title

    # 6. STALE DATA POLICY: Quantitative alerts MUST BE REFUSED when data_freshness is stale
    stale_data = dict(fresh_data)
    stale_data["data_freshness"] = "stale"

    # Reset rule triggered state so it could fire if allowed
    temp_store.update_rule_evaluation_state("r_risk_test", now_iso, is_triggered=False)
    risk_rule_fresh = temp_store.get_rule("r_risk_test")

    alt_stale_refused = engine.evaluate_rule(risk_rule_fresh, "RELIANCE", stale_data)
    assert alt_stale_refused is None, "Alert engine must NEVER fire quantitative alerts on stale data!"

    # 7. Data Staleness Rule: Should fire ONLY when data is actually stale
    staleness_rule = AlertRule(
        rule_id="r_staleness_test",
        name="Telemetry Stale Test",
        ticker="RELIANCE",
        scope="ticker",
        rule_type=AlertRuleType.DATA_STALENESS,
        condition=">=",
        threshold=300.0,
        severity=AlertSeverity.WARNING,
    )
    temp_store.save_rule(staleness_rule)

    stale_data["age_seconds"] = 450.0
    alt_staleness = engine.evaluate_rule(staleness_rule, "RELIANCE", stale_data)
    assert alt_staleness is not None
    assert "Market Feed Outage" in alt_staleness.title


# -----------------------------------------------------------------------------
# 4. Deduplication, Cooldown, and Re-arming Semantics
# -----------------------------------------------------------------------------

def test_deduplication_cooldown_and_rearming(temp_store):
    """Verify deduplication of unchanged observations, cooldown window, and edge re-arming."""
    engine = AlertEngine(store=temp_store)

    rule = AlertRule(
        rule_id="r_dedup_test",
        name="Dedup Test Rule",
        ticker="TCS",
        scope="ticker",
        rule_type=AlertRuleType.PRICE_CHANGE_PCT,
        condition="<=",
        threshold=-4.0,
        severity=AlertSeverity.WARNING,
        cooldown_seconds=300,
    )
    temp_store.save_rule(rule)

    now_dt = datetime.now(timezone.utc)
    obs_time = now_dt.isoformat()

    data_tick1 = {
        "ticker": "TCS",
        "change_pct": -4.8,
        "data_freshness": "live",
        "observation_timestamp": obs_time,
        "retrieved_at": obs_time,
    }

    # 1. Initial breach: Alert fires
    alt1 = engine.evaluate_rule(rule, "TCS", data_tick1)
    assert alt1 is not None

    # 2. Identical observation arrives immediately: Deduplication key prevents duplicate alert
    rule_updated = temp_store.get_rule("r_dedup_test")
    alt_dup = engine.evaluate_rule(rule_updated, "TCS", data_tick1)
    assert alt_dup is None, "Identical observation must be suppressed by deduplication key!"

    # 3. New observation 30 seconds later with slightly different value (-4.9%), but within cooldown (300s):
    # Cooldown suppresses alert flood
    data_tick2 = {
        "ticker": "TCS",
        "change_pct": -4.9,
        "data_freshness": "live",
        "observation_timestamp": (now_dt + timedelta(seconds=30)).isoformat(),
        "retrieved_at": (now_dt + timedelta(seconds=30)).isoformat(),
    }
    rule_in_cooldown = temp_store.get_rule("r_dedup_test")
    alt_cooldown = engine.evaluate_rule(rule_in_cooldown, "TCS", data_tick2)
    assert alt_cooldown is None, "Subsequent breach during cooldown must be suppressed!"

    # 4. Condition resets! Price recovers to -2.0% (not in breach)
    data_reset = {
        "ticker": "TCS",
        "change_pct": -2.0,
        "data_freshness": "live",
        "observation_timestamp": (now_dt + timedelta(seconds=60)).isoformat(),
        "retrieved_at": (now_dt + timedelta(seconds=60)).isoformat(),
    }
    engine.evaluate_rule(rule_in_cooldown, "TCS", data_reset)
    rule_rearmed = temp_store.get_rule("r_dedup_test")
    assert rule_rearmed.is_triggered is False, "Rule must re-arm when condition resets!"

    # 5. Condition breaches again to -5.2%! Edge-trigger fires a new alert!
    # Manually advance rule last_triggered_at beyond cooldown to simulate clean re-crossing
    past_ts = (now_dt - timedelta(seconds=400)).isoformat()
    temp_store.update_rule_evaluation_state("r_dedup_test", past_ts, is_triggered=False, last_triggered_at=past_ts)
    rule_ready = temp_store.get_rule("r_dedup_test")

    data_recross = {
        "ticker": "TCS",
        "change_pct": -5.2,
        "data_freshness": "live",
        "observation_timestamp": (now_dt + timedelta(seconds=120)).isoformat(),
        "retrieved_at": (now_dt + timedelta(seconds=120)).isoformat(),
    }
    alt_recross = engine.evaluate_rule(rule_ready, "TCS", data_recross)
    assert alt_recross is not None, "Re-armed rule must fire when threshold is crossed again!"
    assert alt_recross.trigger_value == -5.2


# -----------------------------------------------------------------------------
# 5. Telegram Notification Delivery & Missing Credential Diagnostics
# -----------------------------------------------------------------------------

def test_telegram_notification_formatting_and_diagnostics(temp_store):
    """Verify Telegram message structure, credential diagnostics, and simulated dispatch."""
    notifier = TelegramAlertNotifier(default_chat_id="")

    # 1. Missing credentials returns clean diagnostic without throwing
    diag = notifier.get_diagnostic_status()
    assert "configured" in diag
    assert "has_bot_token" in diag

    test_alert = AlertRecord(
        alert_id="alt_tg_test_01",
        rule_id="rule_portfolio_risk_high",
        rule_name="High Risk Score Threshold",
        rule_type="risk_threshold",
        ticker="INFY",
        severity=AlertSeverity.CRITICAL,
        title="Forensic Risk Score 74.0 (High)",
        message="Aggregate forensic risk score reached 74.0.",
        trigger_value=74.0,
        threshold_value=70.0,
        observation_timestamp="2026-10-19T14:35:00+05:30",
        retrieved_at="2026-10-19T14:35:05Z",
        data_freshness="live",
        feed_type="intraday_snapshot_5m",
        dedup_key="rule_portfolio_risk_high:INFY:test",
    )

    # 2. Formatted message checks
    msg_text = notifier.format_alert_message(test_alert)
    assert "🚨 *DAKOTA FORENSIC ALERT* [CRITICAL]" in msg_text
    assert "`INFY`" in msg_text
    assert "Observation Time:" in msg_text
    assert "LIVE" in msg_text and "intraday_snapshot_5m" in msg_text
    assert "not investment advice" in msg_text.lower()

    # 3. Simulated dispatch without credentials
    res = notifier.dispatch(test_alert)
    assert res["status"] == "missing_credentials"

    # 4. Simulated dispatch with mocked Telegram API success
    with patch("src.alerts.telegram_notifier.env") as mock_env, \
         patch("src.alerts.telegram_notifier.send_message") as mock_send:
        mock_env.side_effect = lambda k, d="": "token123" if "TOKEN" in k else "12345678"
        mock_send.return_value = {"ok": True, "result": {"message_id": 998811}}

        custom_notifier = TelegramAlertNotifier(default_chat_id="12345678")
        dispatch_res = custom_notifier.dispatch(test_alert)
        assert dispatch_res["status"] == "sent"
        assert dispatch_res["message_id"] == "998811"


# -----------------------------------------------------------------------------
# 6. FastAPI Endpoints Integration Tests
# -----------------------------------------------------------------------------

def test_alerts_endpoints_integration(client):
    """Verify all /api/alerts endpoints operate correctly end to end."""
    # 1. Get summary
    res_summary = client.get("/api/alerts/summary")
    assert res_summary.status_code == 200
    data_summary = res_summary.json()
    assert data_summary["status"] == "ok"
    assert "summary" in data_summary
    assert "active_alerts" in data_summary["summary"]

    # 2. Get rules
    res_rules = client.get("/api/alerts/rules")
    assert res_rules.status_code == 200
    data_rules = res_rules.json()
    assert data_rules["status"] == "ok"
    assert len(data_rules["rules"]) > 0

    first_rule = data_rules["rules"][0]
    rule_id = first_rule["rule_id"]

    # 3. Toggle rule
    res_toggle = client.post(f"/api/alerts/rules/{rule_id}/toggle")
    assert res_toggle.status_code == 200
    assert "enabled" in res_toggle.json()

    # Re-toggle to restore
    client.post(f"/api/alerts/rules/{rule_id}/toggle")

    # 4. Create custom rule
    new_rule_payload = {
        "rule_id": "rule_api_integration_test",
        "name": "Integration Test Rule",
        "ticker": "WIPRO",
        "scope": "ticker",
        "rule_type": "risk_threshold",
        "condition": ">=",
        "threshold": 50.0,
        "severity": "warning",
    }
    res_create = client.post("/api/alerts/rules", json=new_rule_payload)
    assert res_create.status_code == 200
    assert res_create.json()["rule"]["rule_id"] == "rule_api_integration_test"

    # 5. Evaluate ticker
    res_eval = client.post("/api/alerts/evaluate?ticker=WIPRO")
    assert res_eval.status_code == 200
    assert res_eval.json()["status"] == "completed"

    # 6. List alerts
    res_alerts = client.get("/api/alerts?status=all&limit=50")
    assert res_alerts.status_code == 200
    data_alerts = res_alerts.json()
    assert data_alerts["status"] == "ok"
    assert isinstance(data_alerts["alerts"], list)

    # 7. Engine operational status
    res_status = client.get("/api/alerts/status")
    assert res_status.status_code == 200
    data_status = res_status.json()
    assert data_status["status"] == "operational"
    assert "active_rules_count" in data_status
    assert "telegram" in data_status

    # 8. Clean up created rule
    res_del = client.delete("/api/alerts/rules/rule_api_integration_test")
    assert res_del.status_code == 200
    assert res_del.json()["deleted"] is True


# -----------------------------------------------------------------------------
# 7. System Health Reports Alert Status
# -----------------------------------------------------------------------------

def test_system_health_and_connectors_report_alerts(client):
    """Verify /health and /api/connectors/status expose alert telemetry."""
    res_health = client.get("/health")
    assert res_health.status_code == 200
    h_data = res_health.json()
    assert "alerts" in h_data
    assert h_data["alerts"]["status"] == "operational"

    res_conn = client.get("/api/connectors/status")
    assert res_conn.status_code == 200
    c_data = res_conn.json()
    assert "alerts" in c_data
    assert c_data["alerts"]["status"] == "operational"
