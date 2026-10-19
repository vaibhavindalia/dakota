"""Safe, authorized outbound Telegram notifier for Dakota's Campaign & Syndicate Intelligence."""
from __future__ import annotations

import logging
import os
import time
from typing import Any

from src.campaign.models import CampaignRecord, CampaignTier
from src.connectors.config import env
from src.connectors.telegram import send_message

logger = logging.getLogger("dakota.campaign.notifier")


class CampaignTelegramNotifier:
    """Dispatches formatted campaign notifications with deduplication and cooldown policies."""

    def __init__(self, default_chat_id: str | None = None, cooldown_seconds: int = 900) -> None:
        self.default_chat_id = (
            default_chat_id
            or env("TELEGRAM_ALERT_CHAT_ID")
            or env("DAKOTA_ALERT_CHAT_ID")
            or os.getenv("TELEGRAM_CHAT_ID", "").strip()
        )
        self.cooldown_seconds = cooldown_seconds
        self._last_notification: dict[str, float] = {}

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

    def format_campaign_message(self, campaign: CampaignRecord, update_reason: str) -> str:
        tier_emoji = {
            CampaignTier.HIGH: "🚨",
            CampaignTier.MODERATE: "⚠️",
            CampaignTier.CANDIDATE: "🔍",
        }.get(campaign.tier, "📢")

        securities_str = ", ".join(f"`{s}`" for s in campaign.securities) or "None"
        actors_str = ", ".join(campaign.actors) or "Unknown / Unverified"
        relationships_str = ", ".join(campaign.relationship_types) or "temporal_proximity"

        lines = [
            f"{tier_emoji} *DAKOTA SYNDICATE CAMPAIGN DETECTED* [{campaign.tier.value}]",
            f"*Campaign:* {campaign.name}",
            f"*Status:* `{campaign.status.value.upper()}` | *Score:* `{campaign.confidence_score:.2f}`",
            f"*Update Reason:* {update_reason}",
            "",
            f"*Participating Securities:* {securities_str}",
            f"*Identified Sources/Actors:* {actors_str}",
            f"*Relationships:* {relationships_str}",
            f"*First Seen:* `{campaign.first_seen or 'N/A'}`",
            f"*Last Seen:* `{campaign.last_seen or 'N/A'}`",
            "",
            "*Forensic Evidence Observations:*",
        ]

        for rel, expl in list(campaign.relationship_explanations.items())[:4]:
            lines.append(f"• *{rel}:* {expl}")

        if campaign.alert_ids:
            lines.append(f"• *Corroborating Alerts:* {len(campaign.alert_ids)} alert(s) linked")

        if campaign.shared_urls:
            lines.append(f"• *Shared URLs/Markers:* {', '.join(campaign.shared_urls[:2])}")

        if campaign.contradictions:
            lines.append("")
            lines.append("*Context & Potential Contradictions:*")
            for c in campaign.contradictions[:2]:
                lines.append(f"ℹ️ {c}")

        lines.append("")
        lines.append("⚠️ _Forensic syndicate intelligence candidate. For regulatory & analytical review only; not investment advice._")
        return "\n".join(lines)

    def dispatch(
        self,
        campaign: CampaignRecord,
        update_reason: str,
        target_chat_id: str | int | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Dispatch campaign notification with cooldown and credential safety."""
        cid = campaign.campaign_id
        now = time.time()

        # Cooldown check
        if not force:
            last_time = self._last_notification.get(cid, 0.0)
            if now - last_time < self.cooldown_seconds:
                logger.info("Campaign notification skipped for %s: within cooldown window (%.0fs remaining)",
                            cid, self.cooldown_seconds - (now - last_time))
                return {
                    "status": "suppressed",
                    "reason": "cooldown_active",
                    "cooldown_remaining_seconds": round(self.cooldown_seconds - (now - last_time)),
                }

        chat_id = target_chat_id or self.default_chat_id
        if not chat_id:
            logger.info("Telegram notification skipped for campaign %s: chat ID is not configured.", cid)
            return {"status": "missing_credentials", "error": "TELEGRAM_ALERT_CHAT_ID is not configured"}

        bot_token = env("TELEGRAM_BOT_TOKEN") or env("DAKOTA_BOT_TOKEN")
        if not bot_token:
            logger.info("Telegram notification skipped for campaign %s: Bot token is not configured.", cid)
            return {"status": "missing_credentials", "error": "TELEGRAM_BOT_TOKEN is not configured"}

        text = self.format_campaign_message(campaign, update_reason)

        try:
            res = send_message(chat_id=chat_id, text=text, timeout=8.0)
            if res.get("status") == "missing_credentials":
                return res

            if res.get("ok"):
                msg_id = str(res.get("result", {}).get("message_id", ""))
                self._last_notification[cid] = now
                logger.info("Campaign notification for %s delivered successfully to %s (message_id=%s).",
                            cid, chat_id, msg_id)
                return {"status": "sent", "message_id": msg_id, "response": res}
            else:
                err_msg = res.get("description", "Unknown Telegram API error")
                logger.warning("Telegram delivery failed for campaign %s: %s", cid, err_msg)
                return {"status": "failed", "error": err_msg}
        except Exception as exc:
            logger.error("Exception dispatching Telegram campaign notification %s: %s", cid, exc)
            return {"status": "failed", "error": str(exc)}


campaign_notifier = CampaignTelegramNotifier()
