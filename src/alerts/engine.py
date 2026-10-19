"""Persistent Alert and Intelligent Monitoring Engine for Dakota."""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.alerts.models import (
    AlertRecord,
    AlertRule,
    AlertRuleType,
    AlertSeverity,
    AlertStatus,
    AlertSummary,
)
from src.alerts.store import AlertStore, alert_store
from src.alerts.telegram_notifier import TelegramAlertNotifier, telegram_notifier

logger = logging.getLogger("dakota.alerts.engine")

BASE_DIR = Path(__file__).resolve().parents[2]
PORTFOLIO_FILE = BASE_DIR / "data" / "portfolio.json"


class AlertEngine:
    """Core evaluation and dispatch engine for quantitative threshold breaches and forensic risk alerts."""

    _instance: AlertEngine | None = None
    _instance_lock = threading.Lock()

    def __init__(
        self,
        store: AlertStore | None = None,
        notifier: TelegramAlertNotifier | None = None,
    ):
        self.store = store or alert_store
        self.notifier = notifier or telegram_notifier
        self._eval_lock = asyncio.Lock()
        
        # Operational Telemetry
        self._last_evaluation_time: str | None = None
        self._last_eval_duration_ms: float = 0.0
        self._eval_count: int = 0
        self._alerts_generated_count: int = 0
        self._last_error: str | None = None
        self._is_evaluating: bool = False

    @classmethod
    def get_instance(cls) -> AlertEngine:
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _get_portfolio_tickers(self) -> set[str]:
        tickers: set[str] = set()
        if PORTFOLIO_FILE.exists():
            try:
                data = json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8"))
                holdings = data if isinstance(data, list) else data.get("holdings", [])
                for h in holdings:
                    tk = str(h.get("ticker", "")).upper().strip()
                    if tk:
                        tickers.add(tk)
            except Exception as exc:
                logger.debug("Failed reading portfolio tickers for alerts: %s", exc)
        return tickers

    def evaluate_rule(
        self,
        rule: AlertRule,
        ticker: str,
        data: dict[str, Any],
    ) -> AlertRecord | None:
        """Evaluate a single rule against instrument telemetry or risk data."""
        if not rule.enabled:
            return None

        clean_ticker = ticker.upper().strip()
        now_utc = datetime.now(timezone.utc)
        now_iso = now_utc.isoformat()

        # Check scope match
        if rule.scope == "ticker":
            if rule.ticker != "*" and rule.ticker.upper().strip() != clean_ticker:
                return None
        elif rule.scope == "portfolio":
            portfolio_tickers = self._get_portfolio_tickers()
            if clean_ticker not in portfolio_tickers:
                return None

        # Data Freshness Audit:
        # Refuse to fire alerts on stale or unavailable market telemetry
        # UNLESS the rule specifically concerns data staleness / provider health.
        data_freshness = (data.get("data_freshness") or "cached").lower()
        if rule.rule_type != AlertRuleType.DATA_STALENESS:
            if data_freshness in ("stale", "unavailable"):
                logger.debug(
                    "Rule %s skipped for %s: market telemetry is %s (stale alerts prohibited).",
                    rule.rule_id, clean_ticker, data_freshness.upper()
                )
                return None

        # Extract telemetry fields
        obs_timestamp = data.get("market_event_timestamp") or data.get("observation_timestamp") or data.get("as_of")
        retrieved_at = data.get("retrieved_at") or now_iso
        feed_type = data.get("feed_type") or "intraday_snapshot_5m"

        condition_met = False
        trigger_val: float | None = None
        trigger_val_str: str | None = None
        threshold_val = rule.threshold
        threshold_val_str = rule.threshold_str
        title = ""
        message = ""

        # ----------------------------------------------------------------------
        # Rule Condition Evaluations
        # ----------------------------------------------------------------------
        if rule.rule_type == AlertRuleType.RISK_THRESHOLD:
            score = data.get("score") if data.get("score") is not None else data.get("risk_score")
            if score is None:
                return None
            trigger_val = float(score)
            if threshold_val is not None:
                if rule.condition in (">=", "crosses_above"):
                    condition_met = trigger_val >= threshold_val
                elif rule.condition in ("<=", "crosses_below"):
                    condition_met = trigger_val <= threshold_val
                elif rule.condition == "==":
                    condition_met = trigger_val == threshold_val

            band_str = data.get("band", "Unknown")
            title = f"Forensic Risk Score {trigger_val:.1f} ({band_str})"
            message = (
                f"Aggregate forensic risk score for {clean_ticker} reached {trigger_val:.1f} "
                f"(Threshold: {rule.condition} {threshold_val}). Primary indicators: "
                + ", ".join(data.get("reasons", [])[:3] or ["Elevated composite signals"])
            )

        elif rule.rule_type == AlertRuleType.PRICE_CHANGE_PCT:
            chg = data.get("change_pct")
            if chg is None:
                return None
            trigger_val = float(chg)
            if threshold_val is not None:
                if rule.condition in ("<=", "crosses_below"):
                    condition_met = trigger_val <= threshold_val
                elif rule.condition in (">=", "crosses_above"):
                    condition_met = trigger_val >= threshold_val

            sign = "+" if trigger_val >= 0 else ""
            title = f"Price Movement {sign}{trigger_val:.2f}%"
            message = (
                f"Security {clean_ticker} recorded a single-session price change of {sign}{trigger_val:.2f}% "
                f"(Threshold: {rule.condition} {threshold_val}%). Last price: ₹{data.get('latest_price', data.get('last_price', 'N/A'))}."
            )

        elif rule.rule_type == AlertRuleType.PRICE_LEVEL:
            price = data.get("latest_price") or data.get("last_price")
            if price is None:
                return None
            trigger_val = float(price)
            if threshold_val is not None:
                if rule.condition in (">=", "crosses_above"):
                    condition_met = trigger_val >= threshold_val
                elif rule.condition in ("<=", "crosses_below"):
                    condition_met = trigger_val <= threshold_val

            title = f"Price Level ₹{trigger_val:.2f}"
            message = f"Security {clean_ticker} reached price level ₹{trigger_val:.2f} (Target: {rule.condition} ₹{threshold_val})."

        elif rule.rule_type == AlertRuleType.ABNORMAL_VOLUME:
            vol = data.get("volume", 0)
            avg_vol = data.get("avg_volume", 0)
            if avg_vol and avg_vol > 0:
                ratio = round(float(vol) / float(avg_vol), 2)
                trigger_val = ratio
                if threshold_val is not None:
                    condition_met = ratio >= threshold_val
                title = f"Volume Surge {ratio:.1f}x"
                message = (
                    f"Trading volume for {clean_ticker} reached {vol:,} shares ({ratio:.1f}x of 20-day "
                    f"average {int(avg_vol):,}). (Threshold: >= {threshold_val}x)."
                )

        elif rule.rule_type == AlertRuleType.DELIVERY_VOLUME_DROP:
            deliv = data.get("delivery_pct")
            if deliv is not None:
                trigger_val = float(deliv)
                if threshold_val is not None:
                    condition_met = trigger_val <= threshold_val
                title = f"Low Delivery Volume {trigger_val:.1f}%"
                message = (
                    f"Speculative churning / delivery drop detected on {clean_ticker}: Delivery percentage is "
                    f"{trigger_val:.1f}% (Threshold: <= {threshold_val}%). High volume without long-term ownership."
                )

        elif rule.rule_type == AlertRuleType.SURVEILLANCE_EVENT:
            is_surv = data.get("is_surveillance") or (data.get("surveillance_status") not in (None, "", "none", "Normal"))
            if is_surv:
                condition_met = True
                trigger_val_str = str(data.get("surveillance_status") or "Active Framework")
                title = f"Surveillance Framework Active ({trigger_val_str})"
                message = f"Security {clean_ticker} is placed under regulatory exchange surveillance: {trigger_val_str}."

        elif rule.rule_type == AlertRuleType.DATA_STALENESS:
            age_sec = data.get("age_seconds")
            if age_sec is None and retrieved_at:
                try:
                    r_dt = datetime.fromisoformat(str(retrieved_at).replace("Z", "+00:00"))
                    if r_dt.tzinfo is None:
                        r_dt = r_dt.replace(tzinfo=timezone.utc)
                    age_sec = (now_utc - r_dt).total_seconds()
                except Exception:
                    age_sec = None

            if age_sec is not None:
                trigger_val = round(float(age_sec), 1)
                if threshold_val is not None:
                    condition_met = trigger_val >= threshold_val
                title = f"Market Feed Outage ({int(trigger_val)}s stale)"
                message = (
                    f"Exchange telemetry for {clean_ticker} has been stale for {int(trigger_val)} seconds "
                    f"(Threshold: >= {int(threshold_val)}s). Feed status: {data_freshness.upper()}."
                )

        # ----------------------------------------------------------------------
        # Cooldown and Edge-Triggering Re-arming Semantics
        # ----------------------------------------------------------------------
        if not condition_met:
            # Re-arm rule if condition has reset
            if rule.is_triggered:
                self.store.update_rule_evaluation_state(
                    rule_id=rule.rule_id,
                    last_evaluated_at=now_iso,
                    is_triggered=False,
                )
            else:
                self.store.update_rule_evaluation_state(
                    rule_id=rule.rule_id,
                    last_evaluated_at=now_iso,
                )
            return None

        # Condition IS met. Check cooldown and duplicate suppression
        now_ts = now_utc.timestamp()
        if rule.last_triggered_at:
            try:
                last_dt = datetime.fromisoformat(str(rule.last_triggered_at).replace("Z", "+00:00"))
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                seconds_since_trigger = now_ts - last_dt.timestamp()
                if seconds_since_trigger < rule.cooldown_seconds:
                    logger.debug(
                        "Alert suppressed by cooldown for rule %s on %s (elapsed %ds < cooldown %ds).",
                        rule.rule_id, clean_ticker, int(seconds_since_trigger), rule.cooldown_seconds
                    )
                    self.store.update_rule_evaluation_state(
                        rule_id=rule.rule_id,
                        last_evaluated_at=now_iso,
                    )
                    return None
            except Exception:
                pass

        # Deduplication key across unchanged observations
        obs_key = str(obs_timestamp or "current")[:19]
        val_key = f"{trigger_val:.2f}" if trigger_val is not None else str(trigger_val_str)
        dedup_key = f"{rule.rule_id}:{clean_ticker}:{obs_key}:{val_key}"

        if self.store.is_dedup_key_present(dedup_key):
            logger.debug("Duplicate alert observation detected with dedup_key=%s; skipped.", dedup_key)
            self.store.update_rule_evaluation_state(
                rule_id=rule.rule_id,
                last_evaluated_at=now_iso,
            )
            return None

        # ----------------------------------------------------------------------
        # Construct and Persist Alert Record
        # ----------------------------------------------------------------------
        alert_id = f"alt_{uuid.uuid4().hex[:12]}"
        alert = AlertRecord(
            alert_id=alert_id,
            rule_id=rule.rule_id,
            rule_name=rule.name,
            rule_type=rule.rule_type.value if hasattr(rule.rule_type, "value") else str(rule.rule_type),
            ticker=clean_ticker,
            severity=rule.severity,
            status=AlertStatus.ACTIVE,
            title=title,
            message=message,
            trigger_value=trigger_val,
            trigger_value_str=trigger_val_str,
            threshold_value=threshold_val,
            threshold_value_str=threshold_val_str,
            observation_timestamp=obs_timestamp,
            retrieved_at=retrieved_at,
            data_freshness=data_freshness,
            feed_type=feed_type,
            dedup_key=dedup_key,
            evidence_context={
                "ticker": clean_ticker,
                "latest_price": data.get("latest_price") or data.get("last_price"),
                "change_pct": data.get("change_pct"),
                "volume": data.get("volume"),
                "delivery_pct": data.get("delivery_pct"),
                "risk_band": data.get("band"),
                "reasons": data.get("reasons", []),
            },
            jev_assessment=None,
            created_at=now_iso,
        )

        # Optional JEV Contextual Analysis for Critical Events
        if rule.auto_investigate or rule.severity == AlertSeverity.CRITICAL:
            try:
                from src.intelligence.jev.analysis_layer import EvidenceGroundedAnalyzer
                analyzer = EvidenceGroundedAnalyzer()
                sample_ctx = {
                    "ticker": clean_ticker,
                    "claim": f"Forensic Alert: {title} for {clean_ticker}",
                    "latest_price": data.get("latest_price") or data.get("last_price"),
                    "volume": data.get("volume"),
                    "delivery_pct": data.get("delivery_pct"),
                    "data_freshness": data_freshness,
                    "retrieved_at": retrieved_at,
                    "is_surveillance": bool(data.get("is_surveillance")),
                    "evidence_ids": [f"E_MKT_{clean_ticker}", f"E_ALERT_{rule.rule_id}"],
                    "news_headlines": [],
                    "social_signals": [],
                }
                jev_res = analyzer.analyze(sample_ctx)
                alert.jev_assessment = {
                    "backend": "evidence_grounded_analyzer",
                    "analysis": jev_res.model_dump(),
                }
            except Exception as jev_exc:
                logger.debug("JEV contextual analysis skipped for alert %s: %s", alert_id, jev_exc)

        # Save to SQLite
        saved = self.store.save_alert(alert)
        if not saved:
            return None

        # Update Rule Trigger State
        self.store.update_rule_evaluation_state(
            rule_id=rule.rule_id,
            last_evaluated_at=now_iso,
            is_triggered=True,
            last_triggered_at=now_iso,
            increment_trigger=True,
        )
        self._alerts_generated_count += 1

        # Correlate with active campaigns in the syndicate intelligence engine
        try:
            from src.campaign.detector import campaign_detector
            campaign_detector.correlate_alert(alert)
        except Exception as camp_exc:
            logger.debug("Failed correlating alert with campaigns: %s", camp_exc)

        # Outbound Telegram Notification
        if rule.notify_telegram:
            res = self.notifier.dispatch(alert)
            delivery_status = res.get("status", "failed")
            msg_id = res.get("message_id")
            err_msg = res.get("error")
            self.store.update_alert_telegram_status(
                alert_id=alert.alert_id,
                status=delivery_status,
                message_id=msg_id,
                error=err_msg,
            )
            alert.telegram_delivery_status = delivery_status
            alert.telegram_message_id = msg_id
            alert.telegram_error = err_msg

        logger.info(
            "ALERT GENERATED: [%s] %s on %s - %s (dedup=%s)",
            alert.severity.value.upper(), rule.name, clean_ticker, title, dedup_key
        )
        return alert

    async def evaluate_ticker(
        self,
        ticker: str,
        data: dict[str, Any] | None = None,
    ) -> list[AlertRecord]:
        """Evaluate all active rules against a specific ticker's latest data."""
        clean_ticker = ticker.upper().strip()
        if data is None:
            from src.market.universe_manager import get_or_assess_stock
            data = await asyncio.to_thread(get_or_assess_stock, clean_ticker, False, 180)

        rules = self.store.get_rules(enabled_only=True)
        generated_alerts: list[AlertRecord] = []

        for rule in rules:
            alt = self.evaluate_rule(rule, clean_ticker, data)
            if alt:
                generated_alerts.append(alt)

        return generated_alerts

    async def evaluate_portfolio(self) -> list[AlertRecord]:
        """Evaluate all active rules across portfolio holdings."""
        portfolio_tickers = self._get_portfolio_tickers()
        if not portfolio_tickers:
            return []

        generated: list[AlertRecord] = []
        for ticker in portfolio_tickers:
            try:
                from src.market.universe_manager import get_or_assess_stock
                data = await asyncio.to_thread(get_or_assess_stock, ticker, False, 180)
                alts = await self.evaluate_ticker(ticker, data)
                generated.extend(alts)
            except Exception as exc:
                logger.debug("Error evaluating alerts for portfolio ticker %s: %s", ticker, exc)

        return generated

    async def evaluate_all(self, force: bool = False) -> dict[str, Any]:
        """Run a full evaluation cycle across monitored securities and portfolio."""
        if self._eval_lock.locked():
            return {"status": "skipped", "reason": "evaluation_in_progress"}

        async with self._eval_lock:
            start_time = time.perf_counter()
            self._is_evaluating = True
            now_iso = datetime.now(timezone.utc).isoformat()
            new_alerts: list[AlertRecord] = []
            errors: list[str] = []

            try:
                # 1. Collect priority tickers: portfolio + actively monitored
                tickers = self._get_portfolio_tickers()
                from src.market.auto_sync import market_sync_worker
                monitored = market_sync_worker.get_monitored_tickers()
                tickers.update(monitored)

                if not tickers:
                    tickers.update(["VARANIUM", "ZOMATO", "WIPRO", "RELIANCE"])

                # 2. Evaluate each priority security
                for tk in tickers:
                    try:
                        from src.market.universe_manager import get_or_assess_stock
                        data = await asyncio.to_thread(get_or_assess_stock, tk, False, 180)
                        alts = await self.evaluate_ticker(tk, data)
                        new_alerts.extend(alts)
                    except Exception as tk_exc:
                        errors.append(f"{tk}: {tk_exc}")

                duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                self._last_evaluation_time = now_iso
                self._last_eval_duration_ms = duration_ms
                self._eval_count += 1
                if errors:
                    self._last_error = "; ".join(errors[:3])

                return {
                    "status": "completed",
                    "evaluation_time": now_iso,
                    "duration_ms": duration_ms,
                    "tickers_evaluated": len(tickers),
                    "alerts_generated": len(new_alerts),
                    "errors": errors,
                }
            finally:
                self._is_evaluating = False

    def get_status(self) -> dict[str, Any]:
        """Return operational health telemetry for Dakota connectors/system health."""
        summary = self.store.get_summary()
        tg_status = self.notifier.get_diagnostic_status()

        return {
            "status": "operational",
            "is_evaluating": self._is_evaluating,
            "last_evaluation_time": self._last_evaluation_time or summary.last_evaluation_time,
            "last_eval_duration_ms": self._last_eval_duration_ms,
            "evaluation_count": self._eval_count,
            "total_alerts": summary.total_alerts,
            "active_alerts": summary.active_alerts,
            "critical_count": summary.critical_count,
            "warning_count": summary.warning_count,
            "info_count": summary.info_count,
            "active_rules_count": summary.active_rules,
            "telegram": tg_status,
            "last_error": self._last_error,
        }


alert_engine = AlertEngine.get_instance()
