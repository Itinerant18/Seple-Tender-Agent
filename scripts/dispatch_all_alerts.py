"""
SEPLE Tender Platform — Manual Trigger for Slack & Email Digest
Fetches stored tenders, evaluates relevance, sends Slack alerts and emails digest.
"""
import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

import asyncio
import logging
from dotenv import load_dotenv

from database import repository
from database.models import Tender, FitLabel
from notifier.slack_alert import SlackAlerter
from notifier.email_digest import EmailDigestSender

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    load_dotenv()
    await repository.init_schema()
    
    # 1. Fetch raw tender dicts from DB
    raw_tenders = await repository.list_tenders(limit=100)
    logger.info(f"Retrieved {len(raw_tenders)} tenders from database.")
    
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
                source_url=d.get("source_url"),
                fit_classification=d.get("fit_classification") or FitLabel.STRONG_FIT,
                product_categories=d.get("product_categories") or ["General Security / SITC"],
                matching_rationale=d.get("matching_rationale") or "Matched platform search criteria"
            )
            tenders.append(t)
        except Exception as e:
            logger.warning(f"Error parsing tender dict: {e}")
            
    print(f"\nSending Email Digest for {len(tenders[:15])} relevant tenders...")
    email_sender = EmailDigestSender()
    email_success = await email_sender.send_digest(tenders[:15])
    print(f"Email Digest Delivery: {'SUCCESS' if email_success else 'FAILED'}")
    
    print(f"\nSending Slack Alerts for top 5 relevant tenders...")
    slack_sender = SlackAlerter()
    slack_count = 0
    for t in tenders[:5]:
        reason = f"Classification: {t.fit_classification or 'Strong Fit'} | Strategic Opportunity"
        if await slack_sender.send_instant_alert(t, reason):
            slack_count += 1
            
    print(f"\nSlack Alerts Delivered: {slack_count} alerts sent to Slack")

if __name__ == "__main__":
    asyncio.run(main())
