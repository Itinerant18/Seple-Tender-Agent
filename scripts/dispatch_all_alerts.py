"""
SEPLE Tender Platform — High Priority Alert Dispatcher
Evaluates all stored tenders using AlertRulesEngine and posts ONLY High Priority Tenders to Slack.
Sends the daily email digest to RECIPIENT_EMAILS.
"""
import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

import asyncio
import logging
from dotenv import load_dotenv

from database import repository
from database.models import Tender
from notifier.slack_alert import SlackAlerter
from notifier.teams_alert import TeamsAlerter
from notifier.email_digest import EmailDigestSender
from notifier.alert_rules import AlertRulesEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    load_dotenv()
    await repository.init_schema()
    
    # 1. Fetch raw tender dicts from DB
    raw_tenders = await repository.list_tenders(limit=500)
    logger.info(f"Retrieved {len(raw_tenders)} total tenders from database.")
    
    if not raw_tenders:
        print("No tenders in database. Run a scan first.")
        return
        
    tenders = []
    for d in raw_tenders:
        try:
            t = Tender(
                id=d.get("id"),
                title=d.get("title") or "Untitled Tender",
                description=d.get("description"),
                issuing_authority=d.get("issuing_authority"),
                location=d.get("location"),
                value_inr=d.get("value_inr"),
                value_raw=d.get("value_raw"),
                deadline=d.get("deadline"),
                source_url=d.get("source_url"),
                fit_classification=d.get("fit_classification"),
                product_categories=d.get("product_categories") or ["General Security / SITC"],
                matching_rationale=d.get("matching_rationale") or "Matched platform search criteria"
            )
            tenders.append(t)
        except Exception as e:
            logger.warning(f"Error parsing tender dict: {e}")
            
    # Filter for HIGH PRIORITY tenders using AlertRulesEngine
    high_priority_tenders = []
    for t in tenders:
        should_alert, reason = AlertRulesEngine.evaluate(t)
        if should_alert:
            high_priority_tenders.append((t, reason))
            
    print(f"\nFound {len(high_priority_tenders)} High Priority Tenders out of {len(tenders)} total tenders.")
    
    print(f"\n📧 Sending Email Digest for relevant tenders...")
    email_sender = EmailDigestSender()
    digest_tenders = [t for t, _ in high_priority_tenders]
    email_success = await email_sender.send_digest(digest_tenders)
    print(f"Email Digest Delivery: {'SUCCESS' if email_success else 'FAILED'}")
    
    print(f"\n💬 Posting ONLY High Priority Tenders ({len(high_priority_tenders)}) to Slack & Teams...")
    slack_sender = SlackAlerter()
    teams_sender = TeamsAlerter()
    slack_count = 0
    teams_count = 0
    for t, reason in high_priority_tenders:
        if await slack_sender.send_instant_alert(t, reason):
            slack_count += 1
        if await teams_sender.send_instant_alert(t, reason):
            teams_count += 1
            
    print(f"\nHigh Priority Alerts Delivered: {slack_count} to Slack, {teams_count} to Teams successfully!")

if __name__ == "__main__":
    asyncio.run(main())
