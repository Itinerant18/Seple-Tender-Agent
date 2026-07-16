"""
SEPLE Tender Scheduler — Daily Scan
Main orchestration script that runs the full pipeline: Scrape -> Extract -> Classify -> Save -> Alert
Can be run via cron or triggered manually.
"""
import os
import asyncio
import logging
from datetime import datetime

from database import repository
from database.models import Tender, FitLabel, Notification, NotificationType
from connectors import TenderTigerConnector, Tender247Connector, GeMConnector
from processor import FieldExtractor, TenderClassifier, Deduplicator, EligibilityChecker
from processor.keywords import SEARCH_KEYWORDS
from notifier.slack_alert import SlackAlerter
from notifier.email_digest import EmailDigestSender
from notifier.alert_rules import AlertRulesEngine

logger = logging.getLogger(__name__)

class ScannerOrchestrator:
    
    def __init__(self):
        self.extractor = FieldExtractor()
        self.classifier = TenderClassifier()
        self.slack = SlackAlerter()
        self.email = EmailDigestSender()
        self.keywords = SEARCH_KEYWORDS

    async def run_daily_scan(self):
        """Run the full daily scan pipeline. Returns relevant (digest-worthy) tenders."""
        logger.info("Starting Daily Tender Scan Pipeline")
        
        # 1. Scrape Tenders
        raw_tenders = []
        
        # TenderTiger
        tt_run = await repository.start_scrape_run("TenderTiger", self.keywords)
        tt_connector = TenderTigerConnector()
        try:
            tt_tenders = await tt_connector.scrape_tenders(self.keywords)
            raw_tenders.extend(tt_tenders)
            await repository.complete_scrape_run(tt_run, tenders_found=len(tt_tenders))
        except Exception as e:
            logger.error(f"TenderTiger scan failed: {e}")
            await repository.complete_scrape_run(tt_run, error=str(e))
        finally:
            await tt_connector.close()
            
        # Tender247
        t247_run = await repository.start_scrape_run("Tender247", self.keywords)
        t247_connector = Tender247Connector()
        try:
            t247_tenders = await t247_connector.scrape_tenders(self.keywords)
            raw_tenders.extend(t247_tenders)
            await repository.complete_scrape_run(t247_run, tenders_found=len(t247_tenders))
        except Exception as e:
            logger.error(f"Tender247 scan failed: {e}")
            await repository.complete_scrape_run(t247_run, error=str(e))
        finally:
            await t247_connector.close()
            
        logger.info(f"Total raw tenders scraped: {len(raw_tenders)}")
        
        new_tenders_today = []
        
        # 2. Process and Classify
        for raw in raw_tenders:
            # Generate deduplication fingerprint
            fingerprint = Deduplicator.generate_fingerprint(raw)
            
            # Check if we already processed this
            existing = await repository.find_by_fingerprint(fingerprint)
            if existing:
                logger.debug(f"Skipping duplicate tender: {raw.title}")
                continue
                
            # Extract fields
            extracted = self.extractor.extract_all(raw.description or raw.title)
            
            # Classify via LLM
            # In a real run, we would download the PDF first. For MVP, we classify based on title/desc
            analysis = await self.classifier.classify(raw)
            
            # Rule-based eligibility check to correct LLM
            if analysis.eligibility_assessment:
                analysis.eligibility_assessment = EligibilityChecker.evaluate(analysis.eligibility_assessment)
                
            # Create full Tender object
            tender = Tender(
                fingerprint=fingerprint,
                tender_reference=raw.tender_reference or extracted.get("gem_ref") or extracted.get("cppp_ref"),
                title=raw.title,
                description=raw.description,
                scope_summary=analysis.scope_summary,
                category=raw.category,
                product_categories=analysis.matched_categories,
                tender_type="SITC", # Default or extract
                value_raw=raw.value or extracted.get("value"),
                value_inr=FieldExtractor.parse_indian_currency(raw.value or extracted.get("value")),
                emd_amount=extracted.get("emd"),
                tender_fee=extracted.get("fee"),
                # deadline parsing would happen here
                issuing_authority=raw.issuing_authority,
                location=raw.location,
                source_url=raw.url,
                fit_classification=analysis.fit_classification,
                confidence=analysis.confidence,
                matched_keywords=analysis.matched_keywords,
                matched_categories=analysis.matched_categories,
                matching_rationale=analysis.matching_rationale,
                eligibility_status=analysis.eligibility_assessment.eligibility_status if analysis.eligibility_assessment else None,
                eligibility_gaps=analysis.eligibility_assessment.eligibility_gaps if analysis.eligibility_assessment else [],
                scraped_at=datetime.utcnow()
            )
            
            # Save to DB
            tender_id = await repository.upsert_tender(tender)
            tender.id = tender_id
            
            analysis.tender_id = tender_id
            await repository.save_analysis(analysis)
            
            new_tenders_today.append(tender)
            
            # 3. Instant Alerts
            should_alert, reason = AlertRulesEngine.evaluate(tender)
            if should_alert:
                success = await self.slack.send_instant_alert(tender, reason)
                if success:
                    tender.instant_alert_sent = True
                    # In a real app we'd update the DB here
                    
        # 4. Collect digest-worthy tenders — digest send is the caller's job
        # (scheduler/run.py rolls weekend finds into the next working-day digest, PRD §8.1)
        relevant = [t for t in new_tenders_today if t.fit_classification in (FitLabel.STRONG_FIT, FitLabel.POTENTIAL_FIT)]

        logger.info("Daily Tender Scan Pipeline Complete (%d relevant)", len(relevant))
        return relevant


if __name__ == "__main__":
    # For manual testing
    import sys
    from dotenv import load_dotenv
    load_dotenv()
    
    # Initialize DB schema first
    loop = asyncio.get_event_loop()
    loop.run_until_complete(repository.init_schema())
    
    orchestrator = ScannerOrchestrator()
    relevant = loop.run_until_complete(orchestrator.run_daily_scan())
    if relevant:
        loop.run_until_complete(orchestrator.email.send_digest(relevant))
