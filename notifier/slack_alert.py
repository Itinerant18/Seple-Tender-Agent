"""
SEPLE Slack Alert Notifier
Sends tender alerts to Slack channels via webhook.
"""
import os
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class SlackNotifier:
    """Sends tender notifications to Slack via incoming webhook."""

    def __init__(self):
        self.webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        if not self.webhook_url:
            logger.warning("SLACK_WEBHOOK_URL not set — Slack notifications disabled")

    async def send_tender_alert(self, tender: dict) -> bool:
        """
        Send a single tender alert to Slack.

        Args:
            tender: Tender dict with title, value, deadline, source, url

        Returns:
            True if sent successfully
        """
        if not self.webhook_url:
            return False

        analysis = tender.get("analysis", {})
        relevance = analysis.get("relevance_score", "N/A")
        action = analysis.get("recommended_action", "review")

        # Choose emoji based on relevance
        if isinstance(relevance, (int, float)):
            emoji = "🔥" if relevance >= 80 else "⚡" if relevance >= 60 else "📋"
        else:
            emoji = "📋"

        value = tender.get("value", {})
        value_display = value.get("formatted", "Unknown") if isinstance(value, dict) else str(value)

        payload = {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{emoji} New Tender Found",
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Title:*\n{tender.get('title', 'Unknown')}"},
                        {"type": "mrkdwn", "text": f"*Source:*\n{tender.get('source', 'Unknown')}"},
                        {"type": "mrkdwn", "text": f"*Value:*\n{value_display}"},
                        {"type": "mrkdwn", "text": f"*Deadline:*\n{tender.get('deadline', 'Unknown')}"},
                        {"type": "mrkdwn", "text": f"*Relevance:*\n{relevance}"},
                        {"type": "mrkdwn", "text": f"*Action:*\n{action.upper()}"},
                    ],
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "View Tender"},
                            "url": tender.get("url", "#"),
                        },
                    ],
                },
            ],
        }

        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    self.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code == 200:
                    logger.info(f"Slack alert sent: {tender.get('title', '')[:50]}")
                    return True
                else:
                    logger.error(f"Slack webhook failed: {resp.status_code} — {resp.text}")
                    return False
        except Exception as e:
            logger.error(f"Slack alert failed: {e}")
            return False

    async def send_daily_summary(self, tenders: list[dict]) -> bool:
        """Send a daily digest summary to Slack."""
        if not self.webhook_url or not tenders:
            return False

        summary_lines = []
        for t in tenders[:10]:  # Top 10 tenders
            title = t.get("title", "Unknown")[:60]
            value = t.get("value", {})
            val_display = value.get("formatted", "?") if isinstance(value, dict) else "?"
            summary_lines.append(f"• {title} — {val_display}")

        payload = {
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": f"📊 Daily Tender Digest — {len(tenders)} New Tenders"},
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "\n".join(summary_lines)},
                },
            ],
        }

        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.post(self.webhook_url, json=payload)
                return resp.status_code == 200
        except Exception as e:
            logger.error(f"Daily summary failed: {e}")
            return False
