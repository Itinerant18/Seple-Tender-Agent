"""
SEPLE Tender Scheduler — Milestone Tracker
Tracks tender milestones and sends reminders (F8).
"""
import logging
from datetime import datetime, timedelta
from database import repository
from database.models import Notification, NotificationType
from notifier.slack_alert import SlackAlerter
from notifier.email_digest import EmailDigestSender

logger = logging.getLogger(__name__)

class MilestoneTracker:
    """Checks for upcoming milestones and sends reminders."""
    
    def __init__(self):
        self.slack = SlackAlerter()
        self.email = EmailDigestSender()
        
    async def run_checks(self):
        """Run all milestone reminder checks."""
        logger.info("Starting milestone tracker run")
        
        # Check for 7-day reminders
        tenders_7d = await repository.get_upcoming_milestones(within_days=7, reminder_level="7d")
        for mt in tenders_7d:
            await self._send_reminder(mt, 7, "7d")
            
        # Check for 3-day reminders
        tenders_3d = await repository.get_upcoming_milestones(within_days=3, reminder_level="3d")
        for mt in tenders_3d:
            await self._send_reminder(mt, 3, "3d")
            
        # Check for 1-day reminders
        tenders_1d = await repository.get_upcoming_milestones(within_days=1, reminder_level="1d")
        for mt in tenders_1d:
            await self._send_reminder(mt, 1, "1d")
            
        logger.info("Milestone tracker run complete")
            
    async def _send_reminder(self, milestone_data: dict, days_left: int, level: str):
        """Send a reminder for a specific milestone."""
        m_type = milestone_data["milestone_type"].replace("_", " ").title()
        title = milestone_data["tender_title"]
        date = milestone_data["milestone_date"].strftime("%d %b %Y %H:%M")
        
        reason = f"Upcoming {m_type} in {days_left} day(s) (on {date})"
        
        # Convert dict back to an object-like structure for the Slack alerter
        from types import SimpleNamespace
        tender_mock = SimpleNamespace(
            id=milestone_data["tender_id"],
            title=title,
            issuing_authority=milestone_data["issuing_authority"],
            value_inr=0,  # Not strictly needed for reminder
            value_raw="N/A",
            deadline=milestone_data["milestone_date"], # use milestone date as the "deadline" for formatting
            location=milestone_data["location"],
            source_url=milestone_data["source_url"]
        )
        
        # Send Slack Alert
        success = await self.slack.send_instant_alert(tender_mock, reason)
        
        if success:
            await repository.mark_reminder_sent(milestone_data["id"], level)
            
            # Log it
            notif = Notification(
                tender_id=milestone_data["tender_id"],
                channel="slack",
                notification_type=NotificationType.MILESTONE_REMINDER,
                subject=f"Milestone Reminder: {m_type}",
                message=reason,
                status="sent"
            )
            await repository.log_notification(notif)
