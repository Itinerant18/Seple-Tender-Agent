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
from connectors import TenderTigerConnector, Tender247Connector, GeMConnector, CPPPConnector, WebDiscoveryConnector
from connectors.scrape_chain import scrape_page
from processor import FieldExtractor, TenderClassifier, Deduplicator, EligibilityChecker
from config.keywords import SEARCH_KEYWORDS
from notifier.slack_alert import SlackAlerter
from notifier.teams_alert import TeamsAlerter
from notifier.email_digest import EmailDigestSender
from notifier.alert_rules import AlertRulesEngine

logger = logging.getLogger(__name__)

class ScannerOrchestrator:
    
    def __init__(self):
        self.extractor = FieldExtractor()
        self.classifier = TenderClassifier()
        self.slack = SlackAlerter()
        self.teams = TeamsAlerter()
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
            
        # CPPP (Apify actor — no login, also covers state/defence portals)
        cppp_run = await repository.start_scrape_run("CPPP", self.keywords)
        cppp_connector = CPPPConnector()
        try:
            cppp_tenders = await cppp_connector.scrape_tenders(self.keywords)
            raw_tenders.extend(cppp_tenders)
            await repository.complete_scrape_run(cppp_run, tenders_found=len(cppp_tenders))
        except Exception as e:
            logger.error(f"CPPP scan failed: {e}")
            await repository.complete_scrape_run(cppp_run, error=str(e))

        # Open-web discovery (Firecrawl search — dept/PSU/bank/newspaper sites
        # the aggregators miss, PRD §5). Recall-first; dedup drops overlaps.
        ws_run = await repository.start_scrape_run("WebSearch", self.keywords)
        ws_connector = WebDiscoveryConnector()
        try:
            ws_tenders = await ws_connector.scrape_tenders(self.keywords)
            raw_tenders.extend(ws_tenders)
            await repository.complete_scrape_run(ws_run, tenders_found=len(ws_tenders))
        except Exception as e:
            logger.error(f"Web discovery failed: {e}")
            await repository.complete_scrape_run(ws_run, error=str(e))
        finally:
            await ws_connector.close()

        logger.info(f"Total raw tenders scraped: {len(raw_tenders)}")
        
        new_tenders_today = []

        # 2. Process and Classify — one bad row must never discard the batch.
        for raw in raw_tenders:
            try:
                tender = await self._process_raw(raw)
            except Exception:
                logger.exception("Failed to process tender: %s", getattr(raw, "title", "?"))
                continue
            if tender is not None:
                new_tenders_today.append(tender)

        # 4. Return digest-worthy tenders for callers that need the current
        # batch. Delivery uses the durable notifications queue above so a
        # service restart or one-shot cron invocation cannot lose weekend finds.
        relevant = [t for t in new_tenders_today if t.fit_classification in (FitLabel.STRONG_FIT, FitLabel.POTENTIAL_FIT)]

        logger.info("Daily Tender Scan Pipeline Complete (%d relevant)", len(relevant))
        return relevant

    async def _process_raw(self, raw) -> Tender | None:
        """Dedup, classify, persist, and instant-alert a single raw tender.

        Returns the stored Tender, or None if it was a duplicate. Raises on
        unexpected failure so the caller can skip just this one row.
        """
        fingerprint = Deduplicator.generate_fingerprint(raw)

        existing = await repository.find_by_fingerprint(fingerprint)
        if existing:
            logger.debug(f"Skipping duplicate tender: {raw.title}")
            return None

        # Web-discovered rows carry only a search snippet — pull the full page
        # text via the scrape chain (Firecrawl→context.dev→Zyte) so the
        # classifier and extractor see the real scope, not just the title.
        doc_text = None
        if raw.source in ("WebDiscovery", "WebSearch") and raw.url:
            doc_text = await asyncio.to_thread(lambda: scrape_page(raw.url)["markdown"]) or None

        extracted = self.extractor.extract_all(doc_text or raw.description or raw.title)

        # Classify via LLM (falls back to regex if no provider/credit).
        analysis = await self.classifier.classify(raw, document_text=doc_text)

        if analysis.eligibility_assessment:
            analysis.eligibility_assessment = EligibilityChecker.evaluate(analysis.eligibility_assessment)

        tender = Tender(
            fingerprint=fingerprint,
            tender_reference=raw.tender_reference or extracted.get("gem_ref") or extracted.get("cppp_ref"),
            title=raw.title,
            description=raw.description,
            scope_summary=analysis.scope_summary,
            category=raw.category,
            product_categories=analysis.matched_categories,
            tender_type="SITC",  # Default or extract
            value_raw=raw.value or extracted.get("value"),
            value_inr=FieldExtractor.parse_indian_currency(raw.value or extracted.get("value")),
            emd_amount=extracted.get("emd"),
            tender_fee=extracted.get("fee"),
            issuing_authority=raw.issuing_authority,
            location=raw.location,
            source_id=await repository.get_source_id(raw.source),
            source_url=raw.url,
            fit_classification=analysis.fit_classification,
            confidence=analysis.confidence,
            matched_keywords=analysis.matched_keywords,
            matched_categories=analysis.matched_categories,
            matching_rationale=analysis.matching_rationale,
            eligibility_status=analysis.eligibility_assessment.eligibility_status if analysis.eligibility_assessment else None,
            eligibility_gaps=analysis.eligibility_assessment.eligibility_gaps if analysis.eligibility_assessment else [],
            scraped_at=datetime.utcnow(),
        )

        tender_id = await repository.upsert_tender(tender)
        tender.id = tender_id
        analysis.tender_id = tender_id
        await repository.save_analysis(analysis)

        if tender.fit_classification in (FitLabel.STRONG_FIT, FitLabel.POTENTIAL_FIT):
            await repository.queue_digest_tender(tender_id)

        # 3. Instant Alerts
        should_alert, reason = AlertRulesEngine.evaluate(tender)
        if should_alert:
            slack_success = await self.slack.send_instant_alert(tender, reason)
            teams_success = await self.teams.send_instant_alert(tender, reason)
            if slack_success or teams_success:
                tender.instant_alert_sent = True

        return tender


if __name__ == "__main__":
    # For manual testing
    import sys
    from dotenv import load_dotenv
    load_dotenv()
    
    async def _once():
        await repository.init_schema()
        orchestrator = ScannerOrchestrator()
        relevant = await orchestrator.run_daily_scan()
        if relevant:
            await orchestrator.email.send_digest(relevant)

    asyncio.run(_once())
