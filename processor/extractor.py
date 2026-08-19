"""
SEPLE Tender Processor — Extractor
Extracts structured fields from raw tender text using regex and heuristics.
"""
import re
import logging
from datetime import date, datetime
from typing import Dict, Any, Optional

from dateutil import parser as date_parser

logger = logging.getLogger(__name__)

YEAR_PATTERN = re.compile(r"(19|20)\d{2}")

class FieldExtractor:
    """Extracts standard fields (EMD, Value, Dates) from raw text."""
    
    # Common regex patterns for Indian tenders
    EMD_PATTERN = re.compile(r'(?i)(?:EMD|Earnest\s*Money\s*Deposit).*?(?:(?:Rs\.?|INR|₹)\s*)([\d,]+(?:\.\d{2})?(?:\s*(?:Lakh|Crore|Lacs|Cr))?)')
    VALUE_PATTERN = re.compile(r'(?i)(?:Estimated\s*Cost|Tender\s*Value|Project\s*Cost).*?(?:(?:Rs\.?|INR|₹)\s*)([\d,]+(?:\.\d{2})?(?:\s*(?:Lakh|Crore|Lacs|Cr))?)')
    FEE_PATTERN = re.compile(r'(?i)(?:Tender\s*Fee|Cost\s*of\s*Tender).*?(?:(?:Rs\.?|INR|₹)\s*)([\d,]+(?:\.\d{2})?)')
    
    # GeM / CPPP references
    GEM_REF_PATTERN = re.compile(r'(?i)(GEM/\d{4}/[B|R]/\d{7})')
    CPPP_REF_PATTERN = re.compile(r'(?i)(20\d{2}_[A-Z0-9]+_\d+_1)')
    
    # Submission deadline, however the page words it. Web-discovered pages carry
    # no deadline field of their own, so without this every WebSearch row landed
    # with a NULL deadline: 1,670 rows, 100% of that source, permanently exempt
    # from the board's expiry filter and showing an em dash in the UI.
    # Only the date text is captured — parse_datetime owns the format zoo.
    DEADLINE_PATTERN = re.compile(
        r'(?i)(?:bid\s+submission\s+(?:end|closing)|last\s+date(?:\s*(?:&|and)\s*time)?'
        r'|due\s+date|closing\s+date|submission\s+(?:end\s+date|deadline)|end\s+date)'
        r'[^\n:]{0,40}[:\-]\s*'
        # The middle component is a month: digits or a name, never a 4-digit
        # year. Allowing [A-Za-z0-9]{2,9} there let "...06-2023 11..." on a
        # stripped page parse as a date, and a wrong deadline is worse than none
        # — the board would show a tender closing before it does.
        r'(\d{1,2}[-/\s](?:\d{1,2}|[A-Za-z]{3,9})[-/\s]\d{2,4}'
        r'(?:[\s,]+\d{1,2}:\d{2}(?:\s*[APap]\.?[Mm]\.?)?)?'
        r'|\d{4}-\d{2}-\d{2}(?:[T\s]\d{2}:\d{2})?)'
    )

    # Meetings
    PREBID_PATTERN = re.compile(r'(?i)pre[- ]?bid\s*meeting.*?(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}(?:\s+\d{1,2}:\d{2}\s*(?:AM|PM|hrs)?)?)')
    SITE_VISIT_PATTERN = re.compile(r'(?i)site\s*visit.*?(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})')

    def __init__(self):
        pass

    def extract_all(self, text: str) -> Dict[str, Any]:
        """Run all extraction patterns against a block of text."""
        if not text:
            return {}
            
        return {
            'emd': self._extract_first(self.EMD_PATTERN, text),
            'value': self._extract_first(self.VALUE_PATTERN, text),
            'fee': self._extract_first(self.FEE_PATTERN, text),
            'gem_ref': self._extract_first(self.GEM_REF_PATTERN, text),
            'cppp_ref': self._extract_first(self.CPPP_REF_PATTERN, text),
            'deadline': self._extract_first(self.DEADLINE_PATTERN, text),
            'pre_bid': self._extract_first(self.PREBID_PATTERN, text),
            'site_visit': self._extract_first(self.SITE_VISIT_PATTERN, text),
        }
        
    def _extract_first(self, pattern: re.Pattern, text: str) -> Optional[str]:
        """Return the first capture group match for a pattern."""
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
        return None
        
    @staticmethod
    def parse_indian_currency(text_value: str) -> Optional[float]:
        """Convert '1.5 Crore' or '50,000' to numeric float (INR)."""
        if not text_value:
            return None
            
        try:
            # Clean string
            clean = text_value.upper().replace(',', '').replace('RS.', '').replace('INR', '').replace('₹', '').strip()
            
            # Find multiplier
            multiplier = 1
            if 'CR' in clean or 'CRORE' in clean:
                multiplier = 10_000_000
                clean = clean.replace('CRORE', '').replace('CR', '').strip()
            elif 'LAKH' in clean or 'LACS' in clean or 'LAC' in clean:
                multiplier = 100_000
                clean = clean.replace('LAKHS', '').replace('LAKH', '').replace('LACS', '').replace('LAC', '').strip()
                
            return float(clean) * multiplier
        except ValueError:
            return None

    @staticmethod
    def parse_datetime(text: str) -> Optional[datetime]:
        """Parse tender portal date text into a naive datetime.

        Each portal renders dates differently ("16-08-2026 05:45 PM",
        "Due Date : 16 Aug 2026", ISO from GeM), so this defers to dateutil
        with dayfirst=True for Indian ordering. A 4-digit year is required
        because dateutil would otherwise read a bare number or a stray label
        as today's date.
        """
        if not text:
            return None

        clean = str(text).strip()
        if not clean or not YEAR_PATTERN.search(clean):
            return None

        # ISO first: dayfirst=True would read GeM's "2026-08-11" as 8 November.
        try:
            return datetime.fromisoformat(clean.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            pass

        try:
            parsed = date_parser.parse(clean, dayfirst=True, fuzzy=True)
        except (ValueError, OverflowError):
            logger.debug("Unparsed date string: %r", clean)
            return None

        return parsed.replace(tzinfo=None)

    @staticmethod
    def parse_date(text: str) -> Optional[date]:
        """Parse common tender portal date formats into dates."""
        parsed = FieldExtractor.parse_datetime(text)
        return parsed.date() if parsed else None
