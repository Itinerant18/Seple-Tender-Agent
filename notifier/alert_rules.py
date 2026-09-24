"""
SEPLE Tender Notifier — Alert Rules
Configurable engine to determine if a tender warrants an instant alert.
Implements PRD §8.2
"""
import logging
from typing import Optional
from datetime import datetime, date, timedelta
from database.models import Tender, FitLabel

logger = logging.getLogger(__name__)


class AlertRulesEngine:

    # A tender that states no deadline is treated as live only for this long
    # after it was created/scraped. Mirrors database.repository.STALE_DAYS —
    # kept as a literal here because alert rules must stay importable without
    # a database connection, and the two must never drift apart silently.
    # (The expiry test asserts the mirror; bump both together.)
    STALE_DAYS = 30
    # These would ideally come from config/DB
    STRATEGIC_CUSTOMERS = [
        "isro", "drdo", "indian navy", "indian army", "air force",
        "airport authority", "aai", "rbi", "reserve bank", "sbi",
        "ongc", "ntpc", "gail", "bhel", "hal", "bel", "aiims"
    ]
    
    CORE_CATEGORIES = [
        "Video Surveillance",
        "Security Alarm",
        "Public Address",
        "Access Control",
        "Security Screening",
        "Building Management Systems",
        "Fire Detection & Alarm",
        "Fire Suppression",
        "Security Manpower Services"
    ]
    
    HIGH_VALUE_THRESHOLD = 50_00_000  # 50 Lakh
    SHORT_DEADLINE_DAYS = 5
    
    @staticmethod
    def _is_expired(deadline: Optional[datetime]) -> bool:
        """Deadlines arrive naive from the scraper and tz-aware from Postgres
        (TIMESTAMP WITH TIME ZONE), so pick a matching 'now' for each."""
        if not deadline:
            return False
        now = datetime.now(deadline.tzinfo) if deadline.tzinfo else datetime.now()
        return deadline < now

    @classmethod
    def is_stale(cls, tender: Tender) -> bool:
        """True when the tender can no longer be acted on.

        A stated deadline in the past is expired. A tender with NO deadline is
        stale once its publication date (or, failing that, its created/scraped
        timestamp) is older than STALE_DAYS — without this branch,
        web-discovered rows with a NULL deadline lived outside every expiry
        check forever and could still fire alerts.
        """
        if tender.deadline is not None:
            return cls._is_expired(tender.deadline)
        anchor = (getattr(tender, "publication_date", None)
                  or tender.created_at or tender.scraped_at)
        if anchor is None:
            # No deadline and no timestamp to age from: treat as stale rather
            # than alert on something we know nothing about.
            return True
        if isinstance(anchor, date) and not isinstance(anchor, datetime):
            # publication_date is a plain date — give it midnight so the
            # comparison below has a datetime to work with.
            anchor = datetime(anchor.year, anchor.month, anchor.day)
        now = datetime.now(anchor.tzinfo) if anchor.tzinfo else datetime.now()
        return anchor < now - timedelta(days=cls.STALE_DAYS)

    @classmethod
    def evaluate(cls, tender: Tender) -> tuple[bool, Optional[str]]:
        """
        Evaluate if a tender should trigger an instant alert.
        Returns (should_alert, reason)
        """
        if cls.is_stale(tender):
            return False, None

        reasons = []
        has_core = any(cat in cls.CORE_CATEGORIES for cat in tender.product_categories)
        
        # Rule 1: Strong Fit in Core Category
        if tender.fit_classification == FitLabel.STRONG_FIT:
            if has_core:
                reasons.append("Strong Fit in Core Category")
                
        # Rule 2: High Value, scoped to core categories or relevant fits.
        if (
            tender.value_inr
            and tender.value_inr >= cls.HIGH_VALUE_THRESHOLD
            and (
                has_core
                or tender.fit_classification in (FitLabel.STRONG_FIT, FitLabel.POTENTIAL_FIT)
            )
        ):
            reasons.append(f"High Value (≥ ₹{cls.HIGH_VALUE_THRESHOLD/100000} Lakh)")
            
        # Rule 3: Strategic Customer
        if tender.issuing_authority:
            auth_lower = tender.issuing_authority.lower()
            if any(strat in auth_lower for strat in cls.STRATEGIC_CUSTOMERS):
                reasons.append("Strategic Customer")
                
        # Rule 4: Short Deadline (if we just discovered it)
        if tender.deadline:
            days_left = (tender.deadline.date() - datetime.now().date()).days
            # Only alert on short deadline if it's a Strong or Potential fit
            if 0 < days_left <= cls.SHORT_DEADLINE_DAYS and tender.fit_classification in (FitLabel.STRONG_FIT, FitLabel.POTENTIAL_FIT):
                reasons.append(f"Short Deadline ({days_left} days remaining)")
                
        # Rule 5: Corrigendum (This is normally checked differently, but included here for completeness)
        if tender.has_corrigendum and tender.fit_classification == FitLabel.STRONG_FIT:
            reasons.append("Corrigendum on Strong Fit tender")

        if reasons:
            return True, " | ".join(reasons)
            
        return False, None
