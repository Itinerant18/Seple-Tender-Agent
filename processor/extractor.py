"""
SEPLE Tender Data Extractor
Extracts structured data from raw tender text and HTML content.
"""
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class TenderExtractor:
    """Extracts and normalizes structured fields from raw tender data."""

    # Common Indian tender value patterns
    VALUE_PATTERNS = [
        r"(?:Rs\.?|INR|₹)\s*([\d,]+(?:\.\d{2})?)\s*(?:Cr|Crore|crore)",
        r"(?:Rs\.?|INR|₹)\s*([\d,]+(?:\.\d{2})?)\s*(?:L|Lakh|lakh)",
        r"(?:Rs\.?|INR|₹)\s*([\d,]+(?:\.\d{2})?)",
    ]

    DATE_PATTERNS = [
        r"(\d{2}[-/]\d{2}[-/]\d{4})",  # DD-MM-YYYY or DD/MM/YYYY
        r"(\d{4}[-/]\d{2}[-/]\d{2})",  # YYYY-MM-DD
        r"(\d{2}\s+\w+\s+\d{4})",       # DD Month YYYY
    ]

    def extract_value(self, text: str) -> dict:
        """Extract tender value from text, normalized to INR."""
        for pattern in self.VALUE_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value_str = match.group(1).replace(",", "")
                value = float(value_str)

                if "cr" in text.lower():
                    value *= 10_000_000  # 1 Crore = 10M
                elif "lakh" in text.lower() or "lac" in text.lower():
                    value *= 100_000     # 1 Lakh = 100K

                return {
                    "raw": match.group(0),
                    "value_inr": value,
                    "formatted": f"₹{value:,.2f}",
                }

        return {"raw": text, "value_inr": None, "formatted": "Unknown"}

    def extract_deadline(self, text: str) -> str | None:
        """Extract submission deadline from tender text."""
        for pattern in self.DATE_PATTERNS:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None

    def extract_tender_fields(self, raw_tender: dict) -> dict:
        """
        Extract and normalize all fields from a raw tender.

        Args:
            raw_tender: Dict with raw scraped tender data

        Returns:
            Normalized tender dict with extracted fields
        """
        extracted = {
            "title": raw_tender.get("title", "").strip(),
            "source": raw_tender.get("source", "Unknown"),
            "url": raw_tender.get("url", ""),
            "scraped_at": raw_tender.get("scraped_at", datetime.utcnow().isoformat()),
        }

        # Extract value
        value_text = raw_tender.get("value", "")
        extracted["value"] = self.extract_value(value_text)

        # Extract deadline
        deadline_text = raw_tender.get("deadline", "")
        extracted["deadline"] = self.extract_deadline(deadline_text)

        # Extract category
        extracted["category"] = raw_tender.get("category", "Uncategorized").strip()

        # Generate a fingerprint for deduplication
        extracted["fingerprint"] = self._generate_fingerprint(extracted)

        return extracted

    def _generate_fingerprint(self, tender: dict) -> str:
        """Generate a unique fingerprint for deduplication."""
        import hashlib
        key = f"{tender['title']}|{tender['deadline']}|{tender['source']}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]
