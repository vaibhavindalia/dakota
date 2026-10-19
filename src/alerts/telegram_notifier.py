"""Safe, authorized outbound Telegram notifier for Dakota's Alert Engine."""
from __future__ import annotations

import logging
import os
from typing import Any

from src.alerts.models import AlertRecord, AlertSeverity
from src.connectors.config import env
from src.connectors.telegram import send_message

logger = logging.getLogger("dakota.alerts.telegram")


class TelegramAlertNotifier:
    """Dispatches formatted alerts to authorized Telegram channels or recipients with retry and diagnostic handling."""

    def __init__(self, default_chat_id: str | None = None):
        self.default_chat_id = (
            default_chat_id
            or env("TELEGRAM_ALERT_CHAT_ID")
            or env("DAKOTA_ALERT_CHAT_ID")
            or os.getenv("TELEGRAM_CHAT_ID", "").strip()
        )

    def is_configured(self) -> bool:
        has_token = bool(env("TELEGRAM_BOT_TOKEN") or env("DAKOTA_BOT_TOKEN"))
        has_chat = bool(self.default_chat_id)
        return has_token and has_chat

    def get_diagnostic_status(self) -> dict[str, Any]:
        has_token = bool(env("TELEGRAM_BOT_TOKEN") or env("DAKOTA_BOT_TOKEN"))
        has_chat = bool(self.default_chat_id)
        return {
            "configured": has_token and has_chat,
            "has_bot_token": has_token,
            "has_alert_chat_id": has_chat,
            "chat_id_masked": f"***{self.default_chat_id[-4:]}" if has_chat and len(self.default_chat_id) > 4 else ("configured" if has_chat else None),
            "status": "ready" if (has_token and has_chat) else "missing_credentials",
        }

    def format_alert_message(self, alert: AlertRecord) -> str:
        """Construct a structured, informative, and honest notification message."""
        severity_emoji = {
            AlertSeverity.CRITICAL: "🚨",
            AlertSeverity.WARNING: "⚠️",
            AlertSeverity.INFO: "ℹ️",
        }.get(alert.severity, "🔔")

        lines = [
            f"{severity_emoji} *DAKOTA FORENSIC ALERT* [{alert.severity.value.upper()}]",
            f"*Security:* `{alert.ticker}` (NSE/BSE)",
            f"*Rule:* {alert.rule_name}",
            f"*Condition:* {alert.title}",
            "",
            f"*Observation Time:* `{alert.observation_timestamp or 'N/A'}`",
            f"*Retrieved At:* `{alert.retrieved_at or 'N/A'}`",
            f"*Data Freshness:* `{alert.data_freshness.upper()}` ({alert.feed_type})",
            "",
            f"*Summary:* {alert.message}",
        ]

        if alert.trigger_value is not None:
            threshold_disp = alert.threshold_value if alert.threshold_value is not None else alert.threshold_value_str
            lines.append(f"*Observed:* `{alert.trigger_value}` | *Threshold:* `{threshold_disp}`")

        # Include JEV Assessment summary if generated
        if alert.jev_assessment and isinstance(alert.jev_assessment, dict):
            jev_pred = alert.jev_assessment.get("prediction", {})
            jev_label = jev_pred.get("predicted_label") or "Analyzed"
            jev_summary = alert.jev_assessment.get("analysis", {}).get("executive_summary", "")
            lines.append("")
            lines.append(f"*JEV Intelligence:* [{jev_label}] {jev_summary[:200]}...")

        lines.append("")
        lines.append("⚠️ _Automated forensic intelligence alert. For investigative analysis only; not investment advice._")
        return "\n".join(lines)

    def dispatch(self, alert: AlertRecord, target_chat_id: str | int | None = None) -> dict[str, Any]:
        """Dispatch alert to authorized Telegram recipient.
        
        Returns a delivery receipt dictionary without throwing unhandled exceptions.
        """
        chat_id = target_chat_id or self.default_chat_id
        if not chat_id:
            logger.info("Telegram notification skipped for alert %s: TELEGRAM_ALERT_CHAT_ID is not configured.", alert.alert_id)
            return {
                "status": "missing_credentials",
                "error": "TELEGRAM_ALERT_CHAT_ID is not configured",
            }

        bot_token = env("TELEGRAM_BOT_TOKEN") or env("DAKOTA_BOT_TOKEN")
        if not bot_token:
            logger.info("Telegram notification skipped for alert %s: Bot token is not configured.", alert.alert_id)
            return {
                "status": "missing_credentials",
                "error": "TELEGRAM_BOT_TOKEN is not configured",
            }

        text = self.format_alert_message(alert)

        try:
            res = send_message(chat_id=chat_id, text=text, timeout=8.0)
            if res.get("status") == "missing_credentials":
                return res

            if res.get("ok"):
                msg_id = str(res.get("result", {}).get("message_id", ""))
                logger.info("Telegram alert %s delivered successfully to %s (message_id=%s).", alert.alert_id, chat_id, msg_id)
                return {
                    "status": "sent",
                    "message_id": msg_id,
                    "response": res,
                }
            else:
                err_msg = res.get("description", "Unknown Telegram API error")
                logger.warning("Telegram delivery failed for alert %s: %s", alert.alert_id, err_msg)
                return {
                    "status": "failed",
                    "error": err_msg,
                }
        except Exception as exc:
            logger.error("Exception dispatching Telegram alert %s: %s", alert.alert_id, exc)
            return {
                "status": "failed",
                "error": str(exc),
            }


telegram_notifier = TelegramAlertNotifier()
