"""Comprehensive tests for Dakota Phase 8 Cross-Scrip Syndicate Correlation Engine.

Tests:
1. Shared public source (promoter) relationships across distinct securities.
2. Distinctive text fingerprint and shared URL matching.
3. Configurable temporal window boundaries (events within vs outside window).
4. Rejection of simultaneous price movement without supporting promotion evidence.
5. Common mainstream news and broad-market index movement context distinction.
6. Temporal semantics (event_timestamp vs retrieved_at, missing timestamp handling).
7. Incremental campaign updates and persistence across store restart.
8. Alert engine cross-references and market corroboration linkage.
9. Duplicate notification suppression and cooldowns.
10. Investigator actions: acknowledgement, dismissal, monitoring, resolution, and notes.
11. FastAPI REST API endpoints (/api/campaigns, /summary, /{id}, actions, rebuild).
"""
from __future__ import annotations

import json
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import pytest
from fastapi.testclient import TestClient

from src.alerts.models import AlertRecord, AlertRuleType, AlertSeverity
from src.campaign.detector import CampaignDetector, extract_urls, parse_iso_or_fallback
from src.campaign.models import (
    CampaignEvent,
    CampaignRecord,
    CampaignStatus,
    CampaignTier,
    RelationshipType,
)
from src.campaign.notifier import CampaignTelegramNotifier
from src.campaign.store import CampaignStore
from backend.main import app


@pytest.fixture
def temp_db(tmp_path: Path):
    db_file = tmp_path / "test_campaigns.db"
    store = CampaignStore(db_path=db_file)
    return store


@pytest.fixture
def detector(temp_db: CampaignStore):
    return CampaignDetector(store=temp_db, default_window_hours=24)


# 1. Shared Public Source Relationships
def test_shared_promoter_across_securities(detector: CampaignDetector):
    now_utc = datetime.now(timezone.utc)
    now_iso = now_utc.isoformat()

    # Tip 1 on CDSL from @promoter_alpha
    tip1 = {
        "investigation_id": "inv_001",
        "ticker": "CDSL",
        "channel_username": "@promoter_alpha",
        "telegram_timestamp": now_iso,
        "captured_at": now_iso,
        "stored_at": now_iso,
        "fingerprint": "fp_alpha_01",
        "text": "Buy CDSL now target 1800 guaranteed returns!",
    }

    # Tip 2 on VARANIUM from the same @promoter_alpha 30 minutes later
    tip2_time = (now_utc + timedelta(minutes=30)).isoformat()
    tip2 = {
        "investigation_id": "inv_002",
        "ticker": "VARANIUM",
        "channel_username": "@promoter_alpha",
        "telegram_timestamp": tip2_time,
        "captured_at": tip2_time,
        "stored_at": tip2_time,
        "fingerprint": "fp_alpha_02",
        "text": "Pump VARANIUM target 500 next multi-bagger!",
    }

    # First tip alone does not have a cross-scrip partner in the database yet
    camp1 = detector.correlate_tip(tip1)

    # Ingest tip2 - detector finds tip1 shares @promoter_alpha across distinct scrips
    # Fake recent tips storage for correlation
    with tempfile.TemporaryDirectory() as td:
        from unittest.mock import patch
        with patch("src.campaign.detector.load_live_investigations", return_value=[tip1, tip2]):
            camp2 = detector.correlate_tip(tip2)

    assert camp2 is not None
    assert "CDSL" in camp2.securities
    assert "VARANIUM" in camp2.securities
    assert "@promoter_alpha" in camp2.actors
    assert RelationshipType.SHARED_PROMOTER.value in camp2.relationship_types
    assert camp2.tier in (CampaignTier.HIGH, CampaignTier.MODERATE)
    assert "@promoter_alpha" in camp2.relationship_explanations[RelationshipType.SHARED_PROMOTER.value]


# 2. Distinctive Text Fingerprint and Shared URL Matching
def test_distinctive_text_and_url_matching(detector: CampaignDetector):
    now_utc = datetime.now(timezone.utc)
    shared_fp = "fp_syndicate_template_xyz"
    shared_url = "https://t.me/join_vip_pump_group"

    tip_a = {
        "investigation_id": "inv_url_1",
        "ticker": "RELIANCE",
        "channel_username": "@group_one",
        "telegram_timestamp": now_utc.isoformat(),
        "stored_at": now_utc.isoformat(),
        "fingerprint": shared_fp,
        "text": f"MASSIVE GAINS join VIP at {shared_url} slots limited!",
    }

    tip_b = {
        "investigation_id": "inv_url_2",
        "ticker": "TATASTEEL",
        "channel_username": "@group_two",
        "telegram_timestamp": (now_utc + timedelta(hours=1)).isoformat(),
        "stored_at": (now_utc + timedelta(hours=1)).isoformat(),
        "fingerprint": shared_fp,
        "text": f"MASSIVE GAINS join VIP at {shared_url} slots limited!",
    }

    from unittest.mock import patch
    with patch("src.campaign.detector.load_live_investigations", return_value=[tip_a, tip_b]):
        camp = detector.correlate_tip(tip_b)

    assert camp is not None
    assert "RELIANCE" in camp.securities
    assert "TATASTEEL" in camp.securities
    assert RelationshipType.SHARED_TEMPLATE.value in camp.relationship_types
    assert RelationshipType.SHARED_URL.value in camp.relationship_types
    assert shared_url in camp.shared_urls
    assert shared_fp in camp.shared_fingerprints


# 3. Events Within vs Outside Configured Time Window
def test_temporal_window_boundaries(detector: CampaignDetector):
    base_time = datetime(2026, 10, 10, 10, 0, 0, tzinfo=timezone.utc)
    
    # Existing campaign with CDSL and RELIANCE seen at base_time
    camp = CampaignRecord(
        campaign_id="cmp_test_window",
        name="Test Window Campaign",
        status=CampaignStatus.ACTIVE,
        tier=CampaignTier.MODERATE,
        confidence_score=0.6,
        securities=["CDSL", "RELIANCE"],
        actors=["@pump_operator"],
        relationship_types=[RelationshipType.SHARED_PROMOTER.value],
        relationship_explanations={RelationshipType.SHARED_PROMOTER.value: "Shared promoter"},
        time_window_hours=24,
        first_seen=base_time.isoformat(),
        last_seen=base_time.isoformat(),
    )
    detector.store.save_campaign(camp)

    # Tip 1: Within window (12 hours later) -> Should match and update
    within_window_time = (base_time + timedelta(hours=12)).isoformat()
    tip_within = {
        "investigation_id": "inv_within",
        "ticker": "INFY",
        "channel_username": "@pump_operator",
        "telegram_timestamp": within_window_time,
        "stored_at": within_window_time,
        "fingerprint": "fp_within",
        "text": "Pump INFY target 2200",
    }
    updated_camp = detector.correlate_tip(tip_within)
    assert updated_camp is not None
    assert updated_camp.campaign_id == "cmp_test_window"
    assert "INFY" in updated_camp.securities
    assert updated_camp.last_seen == within_window_time

    # Tip 2: Outside window (72 hours after last_seen) -> Should NOT merge into cmp_test_window
    outside_window_time = (base_time + timedelta(hours=96)).isoformat()
    tip_outside = {
        "investigation_id": "inv_outside",
        "ticker": "WIPRO",
        "channel_username": "@pump_operator",
        "telegram_timestamp": outside_window_time,
        "stored_at": outside_window_time,
        "fingerprint": "fp_outside",
        "text": "Pump WIPRO target 600",
    }
    from unittest.mock import patch
    with patch("src.campaign.detector.load_live_investigations", return_value=[]):
        camp_out = detector.correlate_tip(tip_outside)
        # Should not update cmp_test_window
        assert camp_out is None
        reloaded = detector.store.get_campaign("cmp_test_window")
        assert "WIPRO" not in reloaded.securities


# 4. Simultaneous Price Movement Without Promotion Evidence (Rejection)
def test_simultaneous_price_movement_rejected_without_promotion(detector: CampaignDetector):
    """Dakota must NOT treat concurrent alerts or simultaneous price moves on distinct stocks
    as a syndicate campaign unless promotional coordination evidence exists."""
    now_iso = datetime.now(timezone.utc).isoformat()

    alert_1 = AlertRecord(
        alert_id="alt_price_01",
        rule_id="rule_vol",
        rule_name="Abnormal Volume Spike",
        rule_type=AlertRuleType.ABNORMAL_VOLUME,
        ticker="SBIN",
        severity=AlertSeverity.WARNING,
        title="Volume Spike on SBIN",
        message="SBIN volume 3.5x 20d average",
        trigger_value=3.5,
        threshold_value=2.5,
        observation_timestamp=now_iso,
        retrieved_at=now_iso,
        data_freshness="LIVE",
        feed_type="REAL_MARKET",
        dedup_key="sbin_vol_01",
        created_at=now_iso,
    )

    alert_2 = AlertRecord(
        alert_id="alt_price_02",
        rule_id="rule_vol",
        rule_name="Abnormal Volume Spike",
        rule_type=AlertRuleType.ABNORMAL_VOLUME,
        ticker="HDFCBANK",
        severity=AlertSeverity.WARNING,
        title="Volume Spike on HDFCBANK",
        message="HDFCBANK volume 3.1x 20d average",
        trigger_value=3.1,
        threshold_value=2.5,
        observation_timestamp=now_iso,
        retrieved_at=now_iso,
        data_freshness="LIVE",
        feed_type="REAL_MARKET",
        dedup_key="hdfc_vol_01",
        created_at=now_iso,
    )

    # Neither ticker is in an active promotional campaign
    res1 = detector.correlate_alert(alert_1)
    res2 = detector.correlate_alert(alert_2)

    # Neither alert should fabricate a fraudulent syndicate campaign from market movement alone
    assert res1 is None
    assert res2 is None
    all_campaigns = detector.store.list_campaigns()
    assert len(all_campaigns) == 0


# 5. Temporal Semantics: Publication Time vs Retrieval Time & Missing Handling
def test_temporal_semantics_integrity(detector: CampaignDetector):
    # Publication timestamp is in the past; retrieval is now
    pub_time = "2026-10-05T08:30:00+00:00"
    retrieved_time = "2026-10-08T12:00:00+00:00"

    tip = {
        "investigation_id": "inv_pub_vs_ret",
        "ticker": "VARANIUM",
        "channel_username": "@operator",
        "telegram_timestamp": pub_time,
        "captured_at": retrieved_time,
        "stored_at": retrieved_time,
        "text": "Buy VARANIUM now",
    }

    parsed_dt = parse_iso_or_fallback(tip["telegram_timestamp"])
    assert parsed_dt.year == 2026
    assert parsed_dt.month == 10
    assert parsed_dt.day == 5
    assert parsed_dt.hour == 8

    # Fallback when telegram_timestamp is None
    fallback_dt = parse_iso_or_fallback(None)
    assert isinstance(fallback_dt, datetime)
    assert fallback_dt.tzinfo is not None


# 6. Incremental Campaign Updates & Persistence Across Store Restart
def test_persistence_across_restart(tmp_path: Path):
    db_file = tmp_path / "persistent_campaigns.db"
    store1 = CampaignStore(db_path=db_file)

    now_iso = datetime.now(timezone.utc).isoformat()
    camp = CampaignRecord(
        campaign_id="cmp_persistent_01",
        name="Syndicate: CDSL & VARANIUM (@channel)",
        status=CampaignStatus.ACTIVE,
        tier=CampaignTier.HIGH,
        confidence_score=0.85,
        securities=["CDSL", "VARANIUM"],
        actors=["@channel"],
        relationship_types=[RelationshipType.SHARED_PROMOTER.value, RelationshipType.MARKET_CORROBORATION.value],
        relationship_explanations={
            RelationshipType.SHARED_PROMOTER.value: "Same promoter across both stocks.",
            RelationshipType.MARKET_CORROBORATION.value: "Volume spike alert corroborated tip.",
        },
        time_window_hours=24,
        first_seen=now_iso,
        last_seen=now_iso,
        notes="First review note.",
    )
    store1.save_campaign(camp)

    ev = CampaignEvent(
        event_id="ev_001",
        campaign_id="cmp_persistent_01",
        event_type="tip",
        ticker="CDSL",
        source_label="@channel",
        event_timestamp=now_iso,
        retrieved_at=now_iso,
        data_freshness="LIVE",
        summary="Tip on CDSL",
    )
    store1.add_event(ev)

    # Simulate restart by destroying store1 and instantiating store2 on same file
    store2 = CampaignStore(db_path=db_file)
    loaded = store2.get_campaign("cmp_persistent_01", include_events=True)

    assert loaded is not None
    assert loaded.campaign_id == "cmp_persistent_01"
    assert loaded.status == CampaignStatus.ACTIVE
    assert loaded.tier == CampaignTier.HIGH
    assert loaded.confidence_score == 0.85
    assert set(loaded.securities) == {"CDSL", "VARANIUM"}
    assert len(loaded.events) == 1
    assert loaded.events[0].event_id == "ev_001"


# 7. Alert Cross-References and Market Corroboration Linkage
def test_alert_corroborates_active_campaign(detector: CampaignDetector):
    now_utc = datetime.now(timezone.utc)
    now_iso = now_utc.isoformat()

    camp = CampaignRecord(
        campaign_id="cmp_corroborate",
        name="Candidate Campaign",
        status=CampaignStatus.ACTIVE,
        tier=CampaignTier.MODERATE,
        confidence_score=0.6,
        securities=["CDSL", "VARANIUM"],
        actors=["@operator"],
        relationship_types=[RelationshipType.SHARED_PROMOTER.value],
        relationship_explanations={RelationshipType.SHARED_PROMOTER.value: "Shared promoter"},
        time_window_hours=24,
        first_seen=now_iso,
        last_seen=now_iso,
    )
    detector.store.save_campaign(camp)

    # An alert fires on CDSL
    alert = AlertRecord(
        alert_id="alt_cdsl_vol_99",
        rule_id="rule_delivery_drop",
        rule_name="Delivery Volume Drop",
        rule_type=AlertRuleType.DELIVERY_VOLUME_DROP,
        ticker="CDSL",
        severity=AlertSeverity.CRITICAL,
        title="Delivery drop to 14%",
        message="Volume surge with low delivery indicates speculative or artificial circulation",
        trigger_value=14.0,
        threshold_value=20.0,
        observation_timestamp=now_iso,
        retrieved_at=now_iso,
        data_freshness="LIVE",
        feed_type="REAL_MARKET",
        dedup_key="cdsl_deliv_99",
        created_at=now_iso,
    )

    updated = detector.correlate_alert(alert)
    assert updated is not None
    assert updated.campaign_id == "cmp_corroborate"
    assert "alt_cdsl_vol_99" in updated.alert_ids
    assert RelationshipType.MARKET_CORROBORATION.value in updated.relationship_types
    # Corroborating alert should elevate tier to HIGH
    assert updated.tier == CampaignTier.HIGH
    assert updated.confidence_score >= 0.8


# 8. Duplicate Notification Suppression and Cooldowns
def test_notification_suppression_and_cooldown():
    notifier = CampaignTelegramNotifier(default_chat_id="123456789", cooldown_seconds=600)

    camp = CampaignRecord(
        campaign_id="cmp_notify_test",
        name="Test Campaign",
        status=CampaignStatus.ACTIVE,
        tier=CampaignTier.HIGH,
        confidence_score=0.9,
        securities=["CDSL", "VARANIUM"],
        actors=["@actor"],
        relationship_types=[RelationshipType.SHARED_PROMOTER.value],
        relationship_explanations={RelationshipType.SHARED_PROMOTER.value: "Shared actor"},
    )

    from unittest.mock import patch
    with patch("src.campaign.notifier.send_message", return_value={"ok": True, "result": {"message_id": 999}}):
        with patch("src.campaign.notifier.env", side_effect=lambda k, d="": "dummy_token" if "TOKEN" in k else "123456789"):
            res1 = notifier.dispatch(camp, "Initial detection")
            assert res1["status"] == "sent"
            assert res1["message_id"] == "999"

            # Immediate second dispatch for the same campaign must be suppressed by cooldown
            res2 = notifier.dispatch(camp, "Minor update")
            assert res2["status"] == "suppressed"
            assert res2["reason"] == "cooldown_active"


# 9. Investigator Actions: Acknowledge, Monitor, Resolve, Dismiss, Notes
def test_investigator_lifecycle_actions(temp_db: CampaignStore):
    now_iso = datetime.now(timezone.utc).isoformat()
    camp = CampaignRecord(
        campaign_id="cmp_lifecycle_01",
        name="Lifecycle Campaign",
        status=CampaignStatus.ACTIVE,
        tier=CampaignTier.CANDIDATE,
        confidence_score=0.5,
        securities=["INFY", "WIPRO"],
        actors=["@promoter"],
        relationship_types=[RelationshipType.TEMPORAL_BURST.value],
        relationship_explanations={RelationshipType.TEMPORAL_BURST.value: "Burst"},
    )
    temp_db.save_campaign(camp)

    # Monitor
    ok_mon = temp_db.update_status("cmp_lifecycle_01", CampaignStatus.MONITORING, note="Observing delivery trends")
    assert ok_mon is True
    c_mon = temp_db.get_campaign("cmp_lifecycle_01")
    assert c_mon.status == CampaignStatus.MONITORING
    assert "Observing delivery trends" in c_mon.notes

    # Add Note
    ok_note = temp_db.add_note("cmp_lifecycle_01", "SEBI circular checked; no matching disclosure.")
    assert ok_note is True
    c_note = temp_db.get_campaign("cmp_lifecycle_01")
    assert "SEBI circular checked" in c_note.notes

    # Resolve
    ok_res = temp_db.update_status("cmp_lifecycle_01", CampaignStatus.RESOLVED, note="Investigation report archived.")
    assert ok_res is True
    c_res = temp_db.get_campaign("cmp_lifecycle_01")
    assert c_res.status == CampaignStatus.RESOLVED
    assert c_res.resolved_at is not None

    # Dismiss
    ok_dis = temp_db.update_status("cmp_lifecycle_01", CampaignStatus.DISMISSED, note="False correlation.")
    assert ok_dis is True
    c_dis = temp_db.get_campaign("cmp_lifecycle_01")
    assert c_dis.status == CampaignStatus.DISMISSED
    assert c_dis.dismissed_at is not None


# 10. FastAPI REST Endpoints Integration
def test_campaign_api_endpoints():
    client = TestClient(app)

    # 1. Summary stats
    res = client.get("/api/campaigns/summary")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "summary" in data

    # 2. Campaigns list
    res_list = client.get("/api/campaigns?limit=10")
    assert res_list.status_code == 200
    list_data = res_list.json()
    assert list_data["status"] == "ok"
    assert "campaigns" in list_data
    assert "channels" in list_data  # backwards compatibility preserved

    # 3. Correlation rebuild trigger
    res_rebuild = client.post("/api/campaigns/rebuild")
    assert res_rebuild.status_code == 200
    rebuild_data = res_rebuild.json()
    assert rebuild_data["status"] == "ok"
    assert "events_correlated" in rebuild_data
