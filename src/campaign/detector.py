"""Cross-Scrip Syndicate Correlation and Forensic Campaign Intelligence Engine.

Correlates promotional messages, actors, temporal bursts, and corroborating
market events (alerts, volume/delivery anomalies, surveillance flags) across
multiple securities into explainable forensic campaign entities.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.alerts.models import AlertRecord
from src.alerts.store import alert_store
from src.campaign.models import (
    CampaignEvent,
    CampaignRecord,
    CampaignStatus,
    CampaignTier,
    RelationshipType,
)
from src.campaign.notifier import campaign_notifier
from src.campaign.store import campaign_store, CampaignStore
from src.intake.live_store import load_live_investigations

logger = logging.getLogger("dakota.campaign.detector")

URL_REGEX = re.compile(r"https?://[^\s<>\"']+|www\.[^\s<>\"']+|t\.me/[^\s<>\"']+|wa\.me/[^\s<>\"']+", re.IGNORECASE)


def extract_urls(text: str) -> list[str]:
    """Extract clean URLs, Telegram invite links, or WhatsApp links from text."""
    if not text:
        return []
    matches = URL_REGEX.findall(text)
    cleaned = []
    for m in matches:
        m_str = m.strip().rstrip(".,;:)")
        if m_str and len(m_str) > 6:
            cleaned.append(m_str)
    return sorted(list(set(cleaned)))


def parse_iso_or_fallback(ts_str: str | None) -> datetime:
    """Parse ISO timestamp or return current UTC datetime."""
    if not ts_str:
        return datetime.now(timezone.utc)
    try:
        # Handle trailing Z or offsets
        clean_ts = ts_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.now(timezone.utc)


class CampaignDetector:
    """Detects and maintains multi-scrip promotional syndicate campaigns."""

    def __init__(
        self,
        store: CampaignStore | None = None,
        default_window_hours: int = 24,
    ) -> None:
        self.store = store or campaign_store
        self.default_window_hours = default_window_hours

    def _generate_campaign_id(self, primary_actor: str, tickers: list[str]) -> str:
        """Generate a stable, deterministic campaign identifier."""
        sorted_tickers = "-".join(sorted(set(t.upper().strip() for t in tickers if t)))
        clean_actor = (primary_actor or "unknown").lower().replace("@", "").strip()
        seed = f"{clean_actor}::{sorted_tickers}"
        h = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
        return f"cmp_{h}"

    def _evaluate_tier_and_score(
        self,
        relationship_types: list[str],
        securities_count: int,
        alert_count: int,
        has_surveillance: bool = False,
    ) -> tuple[CampaignTier, float]:
        """Calculate explainable confidence score and tier.
        
        Tiers:
          HIGH: Multi-dimensional (shared promoter/copy + market alert / volume anomaly or surveillance).
          MODERATE: Shared actor or identical copy across 2+ distinct securities without verified market corroboration yet.
          CANDIDATE: Temporal proximity or single uncorroborated link.
        """
        score = 0.2
        if securities_count >= 2:
            score += 0.15

        if RelationshipType.SHARED_PROMOTER.value in relationship_types:
            score += 0.25
        if RelationshipType.SHARED_TEMPLATE.value in relationship_types:
            score += 0.25
        if RelationshipType.SHARED_URL.value in relationship_types:
            score += 0.15
        if RelationshipType.TEMPORAL_BURST.value in relationship_types:
            score += 0.10
        if RelationshipType.MARKET_CORROBORATION.value in relationship_types or alert_count > 0:
            score += 0.20
        if has_surveillance or RelationshipType.SURVEILLANCE_FLAG.value in relationship_types:
            score += 0.15

        score = min(1.0, round(score, 2))

        # Tier assignment
        has_promoter_or_copy = (
            RelationshipType.SHARED_PROMOTER.value in relationship_types
            or RelationshipType.SHARED_TEMPLATE.value in relationship_types
        )
        has_market = (
            RelationshipType.MARKET_CORROBORATION.value in relationship_types
            or alert_count > 0
            or has_surveillance
        )

        if securities_count >= 2 and has_promoter_or_copy and has_market:
            tier = CampaignTier.HIGH
        elif securities_count >= 2 and has_promoter_or_copy:
            tier = CampaignTier.MODERATE
        else:
            tier = CampaignTier.CANDIDATE

        return tier, score

    def correlate_tip(self, tip: dict[str, Any]) -> CampaignRecord | None:
        """Ingest and correlate a single tip/investigation record.
        
        Updates existing campaign or creates a new cross-scrip campaign when
        coordination evidence spans multiple securities.
        """
        # 1. Extract tickers
        tickers: list[str] = []
        if tip.get("ticker"):
            tickers.append(str(tip["ticker"]).upper().strip())
        for tk in tip.get("tickers") or []:
            if tk:
                tickers.append(str(tk).upper().strip())
        entity = tip.get("impact", {}).get("entity")
        if entity and len(entity) <= 12 and entity.isalnum():
            tickers.append(str(entity).upper().strip())
        tickers = sorted(list(set(tickers)))

        if not tickers:
            return None

        # 2. Extract actor / channel
        actor = (
            tip.get("channel_username")
            or tip.get("investigation", {}).get("source")
            or tip.get("channel")
            or "unverified_source"
        ).strip()

        # 3. Extract timestamps (separate observation/post time from ingestion time)
        event_ts_str = (
            tip.get("telegram_timestamp")
            or tip.get("captured_at")
            or tip.get("stored_at")
            or datetime.now(timezone.utc).isoformat()
        )
        retrieved_at = tip.get("stored_at") or tip.get("captured_at") or datetime.now(timezone.utc).isoformat()
        event_dt = parse_iso_or_fallback(event_ts_str)

        # 4. Extract fingerprints & URLs
        fp = tip.get("fingerprint") or ""
        text_content = tip.get("raw_text") or tip.get("text") or tip.get("message") or ""
        urls = extract_urls(text_content)
        inv_id = tip.get("investigation_id") or f"tip_{event_dt.strftime('%Y%m%d%H%M%S')}_{tickers[0]}"

        # 5. Search existing campaigns to match
        existing_campaigns = self.store.list_campaigns(limit=100)
        matched_campaign: CampaignRecord | None = None

        for camp in existing_campaigns:
            if camp.status in (CampaignStatus.RESOLVED, CampaignStatus.DISMISSED):
                continue

            camp_last_dt = parse_iso_or_fallback(camp.last_seen or camp.created_at)
            time_diff_hours = abs((event_dt - camp_last_dt).total_seconds()) / 3600.0
            if time_diff_hours > camp.time_window_hours:
                continue

            # Match criteria: shared actor, shared fingerprint, shared URL, or existing security in active campaign
            actor_match = actor and actor != "unverified_source" and actor in camp.actors
            fp_match = fp and fp in camp.shared_fingerprints
            url_match = any(u in camp.shared_urls for u in urls) if urls else False
            ticker_match = any(tk in camp.securities for tk in tickers)

            if actor_match or fp_match or url_match:
                matched_campaign = camp
                break
            elif ticker_match and time_diff_hours <= 6.0:
                matched_campaign = camp
                break

        # 6. Update existing campaign
        if matched_campaign:
            updated = False
            prev_tier = matched_campaign.tier
            prev_securities_count = len(matched_campaign.securities)

            for tk in tickers:
                if tk not in matched_campaign.securities:
                    matched_campaign.securities.append(tk)
                    updated = True
            if actor and actor not in matched_campaign.actors:
                matched_campaign.actors.append(actor)
                updated = True
            if fp and fp not in matched_campaign.shared_fingerprints:
                matched_campaign.shared_fingerprints.append(fp)
                updated = True
            for u in urls:
                if u not in matched_campaign.shared_urls:
                    matched_campaign.shared_urls.append(u)
                    updated = True
            if inv_id not in matched_campaign.evidence_ids:
                matched_campaign.evidence_ids.append(inv_id)
                updated = True

            # Update temporal bounds
            if not matched_campaign.first_seen or event_ts_str < matched_campaign.first_seen:
                matched_campaign.first_seen = event_ts_str
            if not matched_campaign.last_seen or event_ts_str > matched_campaign.last_seen:
                matched_campaign.last_seen = event_ts_str

            # Update relationships & explanations
            if len(matched_campaign.actors) > 0 and len(matched_campaign.securities) >= 2:
                if RelationshipType.SHARED_PROMOTER.value not in matched_campaign.relationship_types:
                    matched_campaign.relationship_types.append(RelationshipType.SHARED_PROMOTER.value)
                matched_campaign.relationship_explanations[RelationshipType.SHARED_PROMOTER.value] = (
                    f"Identified source(s) {', '.join(matched_campaign.actors)} actively promoting "
                    f"{len(matched_campaign.securities)} distinct securities ({', '.join(matched_campaign.securities)})."
                )

            if len(matched_campaign.shared_fingerprints) > 0 and len(matched_campaign.securities) >= 2:
                if RelationshipType.SHARED_TEMPLATE.value not in matched_campaign.relationship_types:
                    matched_campaign.relationship_types.append(RelationshipType.SHARED_TEMPLATE.value)
                matched_campaign.relationship_explanations[RelationshipType.SHARED_TEMPLATE.value] = (
                    f"Matching normalized message fingerprint(s) shared across multiple securities."
                )

            if len(matched_campaign.shared_urls) > 0:
                if RelationshipType.SHARED_URL.value not in matched_campaign.relationship_types:
                    matched_campaign.relationship_types.append(RelationshipType.SHARED_URL.value)
                matched_campaign.relationship_explanations[RelationshipType.SHARED_URL.value] = (
                    f"Identical promotional invite/referral URL(s) detected: {', '.join(matched_campaign.shared_urls[:2])}."
                )

            # Recompute tier and score
            tier, score = self._evaluate_tier_and_score(
                matched_campaign.relationship_types,
                len(matched_campaign.securities),
                len(matched_campaign.alert_ids),
            )
            matched_campaign.tier = tier
            matched_campaign.confidence_score = score
            matched_campaign.name = f"Syndicate Promotion: {', '.join(matched_campaign.securities[:3])} ({matched_campaign.actors[0] if matched_campaign.actors else 'Multi-channel'})"

            # Append CampaignEvent
            ev_id = f"ev_{inv_id}_{int(event_dt.timestamp())}"
            event = CampaignEvent(
                event_id=ev_id,
                campaign_id=matched_campaign.campaign_id,
                event_type="tip",
                ticker=tickers[0],
                source_label=actor,
                event_timestamp=event_ts_str,
                retrieved_at=retrieved_at,
                data_freshness="LIVE",
                summary=f"Promotional tip on {', '.join(tickers)} from {actor}" + (f" with fingerprint {fp[:8]}" if fp else ""),
                metadata={
                    "investigation_id": inv_id,
                    "fingerprint": fp,
                    "urls": urls,
                    "urgency": bool(tip.get("urgency")),
                    "scam_markers": int(tip.get("n_scam_markers", 0) or 0),
                },
            )
            self.store.add_event(event)
            self.store.save_campaign(matched_campaign)

            # Notify on material changes (new security or tier upgrade)
            material_update = (
                len(matched_campaign.securities) > prev_securities_count
                or matched_campaign.tier != prev_tier
            )
            if material_update:
                update_reason = (
                    f"Campaign expanded to security {tickers[0]}"
                    if len(matched_campaign.securities) > prev_securities_count
                    else f"Tier upgraded to {matched_campaign.tier.value}"
                )
                campaign_notifier.dispatch(matched_campaign, update_reason)

            return matched_campaign

        # 7. No existing campaign matched. Check if new cross-scrip campaign can be formed
        # Query recent investigations to check for cross-scrip overlaps
        recent_tips = load_live_investigations(limit=100)
        cross_scrip_matches: list[dict[str, Any]] = []

        for r in recent_tips:
            r_tk = (r.get("ticker") or "").upper().strip()
            if not r_tk or r_tk in tickers:
                continue

            r_actor = (
                r.get("channel_username")
                or r.get("investigation", {}).get("source")
                or r.get("channel")
                or ""
            ).strip()
            r_fp = r.get("fingerprint") or ""
            r_urls = extract_urls(r.get("raw_text") or r.get("text") or r.get("message") or "")
            r_ts_str = r.get("telegram_timestamp") or r.get("captured_at") or r.get("stored_at")
            r_dt = parse_iso_or_fallback(r_ts_str)

            time_diff = abs((event_dt - r_dt).total_seconds()) / 3600.0
            if time_diff > self.default_window_hours:
                continue

            has_shared_actor = actor and actor != "unverified_source" and actor == r_actor
            has_shared_fp = fp and fp == r_fp
            has_shared_url = bool(urls and any(u in r_urls for u in urls))

            if has_shared_actor or has_shared_fp or has_shared_url:
                cross_scrip_matches.append(r)

        if cross_scrip_matches:
            # Form brand new CampaignRecord!
            all_tickers = set(tickers)
            all_actors = {actor} if actor else set()
            all_fps = {fp} if fp else set()
            all_urls = set(urls)
            all_evidence = [inv_id]
            earliest_ts = event_ts_str
            latest_ts = event_ts_str

            rel_types: list[str] = [RelationshipType.TEMPORAL_BURST.value]
            rel_explanations: dict[str, str] = {
                RelationshipType.TEMPORAL_BURST.value: (
                    f"Promotional activities detected within a {self.default_window_hours}-hour observation window."
                )
            }

            for m in cross_scrip_matches:
                m_tk = (m.get("ticker") or "").upper().strip()
                if m_tk:
                    all_tickers.add(m_tk)
                m_act = (m.get("channel_username") or m.get("investigation", {}).get("source") or m.get("channel") or "").strip()
                if m_act:
                    all_actors.add(m_act)
                m_fp = m.get("fingerprint") or ""
                if m_fp:
                    all_fps.add(m_fp)
                m_inv = m.get("investigation_id")
                if m_inv:
                    all_evidence.append(m_inv)
                m_ts = m.get("telegram_timestamp") or m.get("captured_at") or m.get("stored_at")
                if m_ts:
                    earliest_ts = min(earliest_ts, m_ts)
                    latest_ts = max(latest_ts, m_ts)

            if len(all_actors) == 1 and len(all_tickers) >= 2:
                rel_types.append(RelationshipType.SHARED_PROMOTER.value)
                rel_explanations[RelationshipType.SHARED_PROMOTER.value] = (
                    f"Single promoter '{list(all_actors)[0]}' actively promoting multiple securities ({', '.join(sorted(all_tickers))})."
                )
            elif len(all_actors) > 1 and len(all_tickers) >= 2:
                rel_types.append(RelationshipType.SHARED_PROMOTER.value)
                rel_explanations[RelationshipType.SHARED_PROMOTER.value] = (
                    f"Multiple promotional channels ({', '.join(sorted(all_actors))}) coordinating across {len(all_tickers)} securities."
                )

            if len(all_fps) > 0 and any(m.get("fingerprint") == fp for m in cross_scrip_matches if fp):
                rel_types.append(RelationshipType.SHARED_TEMPLATE.value)
                rel_explanations[RelationshipType.SHARED_TEMPLATE.value] = (
                    f"Identical normalized message template shared across distinct scrips."
                )

            if all_urls:
                rel_types.append(RelationshipType.SHARED_URL.value)
                rel_explanations[RelationshipType.SHARED_URL.value] = (
                    f"Matching campaign URL(s): {', '.join(list(all_urls)[:2])}"
                )

            cid = self._generate_campaign_id(actor, list(all_tickers))
            tier, score = self._evaluate_tier_and_score(rel_types, len(all_tickers), 0)

            # Check for potential broad-market or unverified source contradictions
            contradictions: list[str] = []
            if not actor or actor == "unverified_source":
                contradictions.append("Promotional channel lacks verified public identity; source attribution is provisional.")

            campaign = CampaignRecord(
                campaign_id=cid,
                name=f"Syndicate Promotion: {', '.join(sorted(all_tickers)[:3])} ({actor or 'Multi-source'})",
                status=CampaignStatus.ACTIVE,
                tier=tier,
                confidence_score=score,
                securities=sorted(list(all_tickers)),
                actors=sorted(list(all_actors)),
                relationship_types=rel_types,
                relationship_explanations=rel_explanations,
                evidence_ids=all_evidence,
                alert_ids=[],
                shared_urls=sorted(list(all_urls)),
                shared_fingerprints=sorted(list(all_fps)),
                time_window_hours=self.default_window_hours,
                first_seen=earliest_ts,
                last_seen=latest_ts,
                notes="Automated syndicate candidate initialized from cross-scrip correlation.",
                contradictions=contradictions,
            )

            # Add timeline event for current tip
            ev = CampaignEvent(
                event_id=f"ev_{inv_id}_{int(event_dt.timestamp())}",
                campaign_id=cid,
                event_type="tip",
                ticker=tickers[0],
                source_label=actor,
                event_timestamp=event_ts_str,
                retrieved_at=retrieved_at,
                data_freshness="LIVE",
                summary=f"Syndicate promotion detected on {tickers[0]} from {actor}",
                metadata={"investigation_id": inv_id, "fingerprint": fp, "urls": urls},
            )
            campaign.events.append(ev)

            # Check for existing alerts matching any of these securities
            for tk in all_tickers:
                recent_alerts = alert_store.get_alerts(ticker=tk, limit=5)
                for alt in recent_alerts:
                    alt_dt = parse_iso_or_fallback(alt.observation_timestamp or alt.created_at)
                    if abs((alt_dt - event_dt).total_seconds()) / 3600.0 <= self.default_window_hours:
                        if alt.alert_id not in campaign.alert_ids:
                            campaign.alert_ids.append(alt.alert_id)
                            if RelationshipType.MARKET_CORROBORATION.value not in campaign.relationship_types:
                                campaign.relationship_types.append(RelationshipType.MARKET_CORROBORATION.value)
                                campaign.relationship_explanations[RelationshipType.MARKET_CORROBORATION.value] = (
                                    f"Alert '{alt.rule_name}' ({alt.severity.value}) corroborating market impact on {alt.ticker}."
                                )
                            campaign.events.append(CampaignEvent(
                                event_id=f"ev_alt_{alt.alert_id}",
                                campaign_id=cid,
                                event_type="alert",
                                ticker=alt.ticker,
                                source_label="alert_engine",
                                event_timestamp=alt.observation_timestamp or alt.created_at,
                                retrieved_at=alt.retrieved_at,
                                data_freshness=alt.data_freshness,
                                summary=alt.message,
                                metadata={"alert_id": alt.alert_id, "rule": alt.rule_name, "severity": alt.severity.value},
                            ))

            # Recalculate tier & score with any linked alerts
            tier, score = self._evaluate_tier_and_score(
                campaign.relationship_types,
                len(campaign.securities),
                len(campaign.alert_ids),
            )
            campaign.tier = tier
            campaign.confidence_score = score

            self.store.save_campaign(campaign)
            campaign_notifier.dispatch(campaign, "New cross-scrip syndicate campaign identified")
            return campaign

        return None

    def correlate_alert(self, alert: AlertRecord) -> CampaignRecord | None:
        """Correlate a newly generated market alert with active campaigns.
        
        If the alert's ticker is part of an active campaign within the time window,
        links the alert, updates market corroboration evidence, and adjusts tier.
        """
        clean_ticker = alert.ticker.upper().strip()
        alert_dt = parse_iso_or_fallback(alert.observation_timestamp or alert.created_at)

        active_campaigns = self.store.list_campaigns(limit=100)
        for camp in active_campaigns:
            if camp.status in (CampaignStatus.RESOLVED, CampaignStatus.DISMISSED):
                continue

            if clean_ticker not in camp.securities:
                continue

            camp_last_dt = parse_iso_or_fallback(camp.last_seen or camp.created_at)
            time_diff = abs((alert_dt - camp_last_dt).total_seconds()) / 3600.0
            if time_diff > camp.time_window_hours:
                continue

            # Link alert if not already present
            if alert.alert_id in camp.alert_ids:
                return camp

            camp.alert_ids.append(alert.alert_id)
            if RelationshipType.MARKET_CORROBORATION.value not in camp.relationship_types:
                camp.relationship_types.append(RelationshipType.MARKET_CORROBORATION.value)

            camp.relationship_explanations[RelationshipType.MARKET_CORROBORATION.value] = (
                f"Corroborating market alert '{alert.rule_name}' ({alert.severity.value}) triggered for {clean_ticker}: "
                f"{alert.title} (observed {alert.trigger_value} vs threshold {alert.threshold_value or alert.threshold_value_str})."
            )

            # Append CampaignEvent
            ev = CampaignEvent(
                event_id=f"ev_alt_{alert.alert_id}",
                campaign_id=camp.campaign_id,
                event_type="alert",
                ticker=clean_ticker,
                source_label="alert_engine",
                event_timestamp=alert.observation_timestamp or alert.created_at,
                retrieved_at=alert.retrieved_at,
                data_freshness=alert.data_freshness,
                summary=f"Alert [{alert.severity.value.upper()}] {alert.rule_name} on {clean_ticker}: {alert.message}",
                metadata={
                    "alert_id": alert.alert_id,
                    "rule_type": alert.rule_type.value if hasattr(alert.rule_type, "value") else str(alert.rule_type),
                    "trigger_value": alert.trigger_value,
                    "threshold_value": alert.threshold_value or alert.threshold_value_str,
                },
            )
            self.store.add_event(ev)

            # Recompute tier and score
            prev_tier = camp.tier
            tier, score = self._evaluate_tier_and_score(
                camp.relationship_types,
                len(camp.securities),
                len(camp.alert_ids),
            )
            camp.tier = tier
            camp.confidence_score = score
            self.store.save_campaign(camp)

            # Dispatch notification if tier escalated to HIGH or market alert is CRITICAL
            if camp.tier == CampaignTier.HIGH and prev_tier != CampaignTier.HIGH:
                campaign_notifier.dispatch(camp, f"Market corroboration elevated campaign to HIGH: {alert.rule_name} on {clean_ticker}")

            logger.info("Correlated alert %s (%s) with campaign %s", alert.alert_id, clean_ticker, camp.campaign_id)
            return camp

        return None

    def rebuild_correlations(self, lookback_limit: int = 150) -> int:
        """Scan stored live investigations and alerts to rebuild/refresh correlations."""
        tips = load_live_investigations(limit=lookback_limit)
        # Sort chronologically by observation/post time
        tips.sort(key=lambda t: parse_iso_or_fallback(t.get("telegram_timestamp") or t.get("captured_at") or t.get("stored_at")))

        correlated_count = 0
        for tip in tips:
            camp = self.correlate_tip(tip)
            if camp:
                correlated_count += 1

        # Also correlate existing alerts
        all_alerts = alert_store.get_alerts(limit=100)
        for alt in all_alerts:
            self.correlate_alert(alt)

        return correlated_count


campaign_detector = CampaignDetector()
