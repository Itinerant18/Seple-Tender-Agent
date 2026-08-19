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
from connectors import TenderTigerConnector, Tender247Connector, GeMConnector, WebDiscoveryConnector
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
        # Reset per run; defined here so _process_raw works when called directly.
        self._web_gate_drops = 0
        # SCAN_SOURCES=GeM,Tender247 limits the run to those sources. Empty (the
        # default) scans everything. TenderTiger alone returns ~2700 raw rows,
        # each costing an LLM classification call, so a targeted re-scan of one
        # source is otherwise unaffordable.
        selected = os.getenv("SCAN_SOURCES", "").strip()
        self.sources = {s.strip().lower() for s in selected.split(",") if s.strip()}

    def _enabled(self, source: str) -> bool:
        if not self.sources:
            return True
        if source.lower() in self.sources:
            return True
        logger.info("Skipping %s (not in SCAN_SOURCES)", source)
        return False

    async def run_daily_scan(self):
        """Run the full daily scan pipeline. Returns relevant (digest-worthy) tenders."""
        logger.info("Starting Daily Tender Scan Pipeline")

        # 1. Scrape Tenders. Each source is isolated: one failing scraper is
        # recorded on its own scrape run and never aborts the others.
        raw_tenders = []

        connectors = (
            ("TenderTiger", TenderTigerConnector),
            ("Tender247", Tender247Connector),
            # GeM: direct Playwright scrape of bidplus.gem.gov.in, no login
            ("GeM", GeMConnector),
            # Open-web discovery — dept/PSU/bank/newspaper sites the
            # aggregators miss (PRD §5). Recall-first; dedup drops overlaps.
            ("WebSearch", WebDiscoveryConnector),
        )

        for name, factory in connectors:
            if not self._enabled(name):
                continue
            run_id = await repository.start_scrape_run(name, self.keywords)
            connector = factory()
            try:
                found = await connector.scrape_tenders(self.keywords)
                raw_tenders.extend(found)
                await repository.complete_scrape_run(run_id, tenders_found=len(found))
            except Exception as e:
                logger.error("%s scan failed: %s", name, e)
                await repository.complete_scrape_run(run_id, error=str(e))
            finally:
                await connector.close()

        logger.info(f"Total raw tenders scraped: {len(raw_tenders)}")
        
        new_tenders_today = []
        self._web_gate_drops = 0

        # 2. Process and Classify — one bad row must never discard the batch.
        for raw in raw_tenders:
            try:
                tender = await self._process_raw(raw)
            except Exception:
                logger.exception("Failed to process tender: %s", getattr(raw, "title", "?"))
                continue
            if tender is not None:
                new_tenders_today.append(tender)

        # The web gate can legitimately reject every candidate, and a source that
        # quietly stores nothing has already cost this project days of
        # misdiagnosis. Say so out loud.
        web_found = sum(1 for r in raw_tenders if r.source in ("WebDiscovery", "WebSearch"))
        if web_found and self._web_gate_drops >= web_found:
            logger.warning(
                "WebSearch: all %d candidates were dropped for having no deadline "
                "and no tender reference. If this repeats, suspect the scrape chain "
                "failing to read the pages rather than the pages being listings.",
                web_found,
            )
        elif self._web_gate_drops:
            logger.info(
                "WebSearch: %d of %d candidates dropped by the deadline gate",
                self._web_gate_drops, web_found,
            )

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

        deadline = FieldExtractor.parse_datetime(raw.deadline)
        if raw.deadline and deadline is None:
            # A silently dropped deadline is what let alerts fire on closed
            # tenders — surface the raw text so the format can be added.
            logger.warning("Unparsed %s deadline: %r", raw.source, raw.deadline)

        existing = await repository.find_by_fingerprint(fingerprint)
        if existing:
            await repository.patch_missing_fields(
                fingerprint,
                deadline=deadline,
                category=raw.category,
                location=raw.location,
            )
            logger.debug(f"Skipping duplicate tender: {raw.title}")
            return None

        # Web-discovered rows carry only a search snippet — pull the full page
        # text via the scrape chain (Firecrawl→context.dev→Zyte) so the
        # classifier and extractor see the real scope, not just the title.
        doc_text = None
        if raw.source in ("WebDiscovery", "WebSearch") and raw.url:
            doc_text = await asyncio.to_thread(lambda: scrape_page(raw.url)["markdown"]) or None

        extracted = self.extractor.extract_all(doc_text or raw.description or raw.title)

        # Web-discovered rows have no deadline field of their own, so fall back to
        # whatever the fetched page states. Without this the extractor's deadline
        # was computed and thrown away, and every WebSearch row stored a NULL.
        if deadline is None:
            deadline = FieldExtractor.parse_datetime(extracted.get("deadline"))

        # A tender notice says when bids close. An index page, a product listing,
        # a staff page or a news article about a tender does not — and after the
        # URL filter those are still most of what a web search returns. Gate on
        # the evidence rather than on the shape of the URL: guessing from the URL
        # is an arms race, and this is the check that actually holds.
        # Placed before classify() so a rejected page costs no LLM call.
        if raw.source in ("WebDiscovery", "WebSearch") and deadline is None and not (
            raw.tender_reference or extracted.get("gem_ref") or extracted.get("cppp_ref")
        ):
            self._web_gate_drops += 1
            logger.info(
                "Dropping web result with no deadline and no tender reference: %s",
                raw.url,
            )
            return None

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
            category=raw.category or (analysis.matched_categories[0] if analysis.matched_categories else None),
            product_categories=analysis.matched_categories,
            tender_type="SITC",  # Default or extract
            value_raw=raw.value or extracted.get("value"),
            value_inr=FieldExtractor.parse_indian_currency(raw.value or extracted.get("value")),
            emd_amount=extracted.get("emd"),
            tender_fee=extracted.get("fee"),
            deadline=deadline,
            publication_date=FieldExtractor.parse_date(raw.publication_date),
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
