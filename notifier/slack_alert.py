"""
SEPLE Tender Notifier — Slack Alert
Sends instant alerts for high-priority tenders to Slack.
Implements PRD §8.2
"""
import os
import logging
import httpx
from typing import Optional
from database.models import Tender

logger = logging.getLogger(__name__)

class SlackAlerter:
    
    def __init__(self):
        self.webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        
    async def send_instant_alert(self, tender: Tender, reason: str) -> bool:
        """Send an instant alert to Slack."""
        if not self.webhook_url:
            logger.warning("SLACK_WEBHOOK_URL not set. Cannot send Slack alert.")
            return False
            
        val = tender.value_inr / 100000 if tender.value_inr else 0
        val_str = f"₹{val:,.2f} Lakh" if val > 0 else (tender.value_raw or "Not specified")
        deadline = tender.deadline.strftime("%d %b %Y") if tender.deadline else "Not specified"
        
        # Slack Block Kit formatting
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🚨 URGENT: High Priority Tender Discovered",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Reason for Alert:* {reason}\n\n*<{tender.source_url or '#'}|{tender.title}>*"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Authority:*\n{tender.issuing_authority or 'Unknown'}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Value:*\n{val_str}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Deadline:*\n{deadline}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Location:*\n{tender.location or 'Unknown'}"
                    }
                ]
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Found on {tender.source_url.split('/')[2] if tender.source_url else 'Unknown'}"
                    }
                ]
            }
        ]
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url,
                    json={"blocks": blocks, "text": f"High Priority Tender: {tender.title}"}
                )
                response.raise_for_status()
            logger.info(f"Successfully sent Slack alert for tender {tender.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")
            return False
