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
    #
    # Date forms covered by the capture group:
    #   15-03-2024 / 15/03/2024 / 15 Mar 2024 / 15-Aug-2026  (day-first)
    #   15.03.2024 / 15.03.26                                (Indian dot form)
    #   15th March 2024 / 1st April 2026                     (ordinals)
    #   2026-09-15 / 2026-09-15T14:30                        (ISO)
    # The middle component of the slash/dot forms is a month: digits or a name,
    # never a 4-digit year. Allowing [A-Za-z0-9]{2,9} there let "...06-2023 11..."
    # on a stripped page parse as a date, and a wrong deadline is worse than none
    # — the board would show a tender closing before it does. The dot form has
    # the same guard: "06.2023" alone (month.year) must not match, so a two-digit
    # day component is mandatory.
    # Label quality first. A wrong deadline is worse than none, and portals
    # print the tender-document SALE cutoff ("CLOSING DATE OF SALE FROM …"),
    # the clarification cutoff and the publication cutoff ABOVE the bid
    # deadline. search() takes the first hit, so accepting those labels stored
    # a date that is never later than the real bid close — which hides a
    # still-live tender from the board. Blocking them lets the same search walk
    # on to "CLOSING DATE OF SUBMISSION FORM …" and record the real deadline.
    DEADLINE_PATTERN = re.compile(
        r'(?i)(?:bid\s+submission\s+(?:end|closing)|last\s+date(?:\s*(?:&|and)\s*time)?'
        r'(?:\s+(?:of|for)\s+(?:bid\s+)?submission)?'
        r'|due\s+date'
        r'|closing\s+date(?!\s+(?:of|for)\s+(?:tender\s+|document\s+)?'
        r'(?:sale|clarification|publication))'
        r'|submission\s+(?:end\s+date|deadline)'
        r'|bids?\s+(?:close|closing)\s+on|end\s+date)'
        # Non-greedy bridge: greedy backtracking walks prefixes from the
        # longest down, so "…is 15-03-2024" settled on the prefix "…is 15"
        # and captured "5-03-2024" — the right shape, the wrong day. Shortest
        # first stops at "…is " and captures the full date.
        r'[^\n:]{0,40}?[:\-]?\s*'
        r'(\d{1,2}[-/\s](?:\d{1,2}|[A-Za-z]{3,9})[-/\s]\d{2,4}'
        r'(?:[\s,]+\d{1,2}:\d{2}(?:\s*[APap]\.?[Mm]\.?)?)?'
        r'|\d{1,2}\.\d{1,2}\.\d{2,4}'
        r'|\d{1,2}(?:st|nd|rd|th)\s+[A-Za-z]{3,9}\s*,?\s*\d{4}'
        r'(?:[\s,]+\d{1,2}:\d{2}(?:\s*[APap]\.?[Mm]\.?)?)?'
        r'|\d{4}-\d{2}-\d{2}(?:[T\s]\d{2}:\d{2})?)'
    )

    # A page that lists MANY tenders is a listing, not a notice. Its closing
    # dates belong to different tenders, so attributing any one of them to the
    # row being processed borrows a deadline — worse than none, because the
    # board then trusts a date that is not this tender's. Such rows used to
    # surface from mptenders.gov.in ("Tenders Archived") looking live with a
    # deadline that belonged to some other row of the portal's table.
    # Counting the labels is the shape test: a single notice states its
    # deadline once; a portal table prints one per row (mptenders' front page
    # alone shows ten rows with a Closing Date column). The count is computed
    # lazily at first use so re-compiling the pattern on import stays cheap.
    _LISTING_LABEL_THRESHOLD = 3

    @classmethod
    def _deadline_is_from_listing(cls, text: str) -> bool:
        """True when the text looks like a multi-tender listing page.

        Threshold 3 (not 2): a corrigendum notice may legitimately restate its
        deadline alongside a reference to the original notice.
        """
        return len(cls.DEADLINE_PATTERN.findall(text or "")) >= cls._LISTING_LABEL_THRESHOLD

    # Dates embedded in archive URLs — eprocurment portals stamp document paths
    # like .../230220241747/notice.pdf or /20240223/tender.pdf. Stands in as a
    # PROXY PUBLICATION DATE when the document body states none, which is what
    # lets the staleness window classify an old upload as old. Kept separate
    # from parse_datetime: parse_datetime is fed deadline labels, and its tests
    # promise None on unlabelled digit soup.
    _URL_DATE_PATTERNS = (
        # ddmmyyyy(+optional hhmm) run together: 230220241747, 15032024
        re.compile(r'(?:^|\D)([0-3]\d)([01]\d)((?:20)\d{2})(?:([0-2]\d)([0-5]\d))?(?:\D|$)'),
        # yyyymmdd run together: 20240223
        re.compile(r'(?:^|\D)((?:20)\d{2})([01]\d)([0-3]\d)(?:\D|$)'),
    )

    # Meetings
    PREBID_PATTERN = re.compile(r'(?i)pre[- ]?bid\s*meeting.*?(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}(?:\s+\d{1,2}:\d{2}\s*(?:AM|PM|hrs)?)?)')
    SITE_VISIT_PATTERN = re.compile(r'(?i)site\s*visit.*?(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})')

    def __init__(self):
        pass

    def extract_all(self, text: str) -> Dict[str, Any]:
        """Run all extraction patterns against a block of text.

        A multi-tender listing page yields nothing — its dates belong to other
        tenders, and a deadline borrowed from a table row would present an
        expired notice as live (or a live one as expired) on the board.
        """
        if not text:
            return {}
        if self._deadline_is_from_listing(text):
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
        if not clean:
            return None

        # "15.03.26" — a full dot form with a 2-digit year is unambiguous,
        # but the 4-digit-year guard below would reject it and drop the
        # deadline back to NULL (the exact bug this pattern was widened for).
        # Indian procurement has no pre-2000 notices: 26 → 2026.
        short_dot = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{2})(?:\s+(\d{1,2}):(\d{2}))?", clean)
        if short_dot:
            day, month, year = (int(short_dot.group(i)) for i in (1, 2, 3))
            hour = int(short_dot.group(4) or 0)
            minute = int(short_dot.group(5) or 0)
            try:
                return datetime(2000 + year, month, day, hour, minute)
            except ValueError:
                return None

        if not YEAR_PATTERN.search(clean):
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

    @staticmethod
    def parse_url_date(url: Optional[str]) -> Optional[datetime]:
        """Extract a proxy publication date from an archive-style URL.

        Government portals embed timestamps in document paths
        (.../230220241747/notice.pdf, /20240223/tender.pdf). Returns None when
        no plausible embedded date exists — a wrong proxy date would mislabel
        a live notice as archived, so sanity requires a real month (01-12)
        and a year in the recent past.
        """
        if not url:
            return None
        for pattern in FieldExtractor._URL_DATE_PATTERNS:
            m = pattern.search(url)
            if not m:
                continue
            groups = [g for g in m.groups() if g]
            try:
                if len(groups) >= 3:
                    if len(groups[0]) == 4:  # yyyymmdd
                        y, mo, d = int(groups[0]), int(groups[1]), int(groups[2])
                        hh = mm = 0
                    else:  # ddmmyyyy[hhmm]
                        d, mo, y = int(groups[0]), int(groups[1]), int(groups[2])
                        hh = int(groups[3]) if len(groups) > 3 else 0
                        mm = int(groups[4]) if len(groups) > 4 else 0
                    if 2000 <= y <= datetime.now().year and 1 <= mo <= 12 and 1 <= d <= 31:
                        return datetime(y, mo, d, hh, mm)
            except (ValueError, IndexError):
                continue
        return None
