"""
SEPLE Tender Notifier — Microsoft Teams Alert
Sends instant alerts for high-priority tenders to MS Teams.
"""
import os
import logging
import httpx
from typing import Optional
from database.models import Tender

logger = logging.getLogger(__name__)

class TeamsAlerter:
    
    def __init__(self):
        self.webhook_url = os.getenv("TEAMS_WEBHOOK_URL")
        
    async def send_instant_alert(self, tender: Tender, reason: str) -> bool:
        """Send an instant alert to Microsoft Teams."""
        if not self.webhook_url:
            logger.warning("TEAMS_WEBHOOK_URL not set. Cannot send Teams alert.")
            return False
            
        val = tender.value_inr / 100000 if tender.value_inr else 0
        val_str = f"₹{val:,.2f} Lakh" if val > 0 else (tender.value_raw or "Not specified")
        deadline = tender.deadline.strftime("%d %b %Y") if tender.deadline else "Not specified"
        
        # Adaptive Card format for MS Teams
        card = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "contentUrl": None,
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": "🚨 URGENT: High Priority Tender Discovered",
                                "weight": "Bolder",
                                "size": "Large"
                            },
                            {
                                "type": "TextBlock",
                                "text": f"**Reason for Alert:** {reason}",
                                "wrap": True
                            },
                            {
                                "type": "TextBlock",
                                "text": f"[{tender.title}]({tender.source_url or 'https://agent.seple.in'})",
                                "wrap": True,
                                "color": "Accent",
                                "weight": "Bolder"
                            },
                            {
                                "type": "FactSet",
                                "facts": [
                                    {"title": "Authority:", "value": tender.issuing_authority or "Unknown"},
                                    {"title": "Value:", "value": val_str},
                                    {"title": "Deadline:", "value": deadline},
                                    {"title": "Location:", "value": tender.location or "Unknown"}
                                ]
                            },
                            {
                                "type": "TextBlock",
                                "text": f"Found on {tender.source_url.split('/')[2] if tender.source_url else 'Unknown'}",
                                "isSubtle": True,
                                "size": "Small",
                                "wrap": True
                            }
                        ]
                    }
                }
            ]
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.webhook_url, json=card)
                response.raise_for_status()
            logger.info(f"Successfully sent Teams alert for tender {tender.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to send Teams alert: {e}")
            return False
