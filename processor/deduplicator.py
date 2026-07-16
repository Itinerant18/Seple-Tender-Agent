"""
SEPLE Tender Deduplicator
Deduplicates tenders across multiple sources using fingerprinting.
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class TenderDeduplicator:
    """Removes duplicate tenders using fingerprint matching and fuzzy title comparison."""

    def __init__(self, similarity_threshold: float = 0.85):
        self.similarity_threshold = similarity_threshold
        self._seen_fingerprints: set[str] = set()

    def deduplicate(self, tenders: list[dict]) -> list[dict]:
        """
        Remove duplicate tenders from a list.

        Uses exact fingerprint matching first, then falls back to
        fuzzy title similarity for near-duplicates.

        Args:
            tenders: List of tender dicts (must have 'fingerprint' and 'title' keys)

        Returns:
            Deduplicated list of tenders
        """
        unique = []
        duplicates_removed = 0

        for tender in tenders:
            fp = tender.get("fingerprint", "")

            # Exact fingerprint match
            if fp and fp in self._seen_fingerprints:
                duplicates_removed += 1
                continue

            # Fuzzy title match against existing unique tenders
            if self._is_near_duplicate(tender, unique):
                duplicates_removed += 1
                continue

            if fp:
                self._seen_fingerprints.add(fp)
            unique.append(tender)

        logger.info(
            f"Deduplication: {len(tenders)} input → {len(unique)} unique "
            f"({duplicates_removed} duplicates removed)"
        )
        return unique

    def _is_near_duplicate(self, tender: dict, existing: list[dict]) -> bool:
        """Check if a tender is a near-duplicate of any existing tender."""
        title = tender.get("title", "").lower().strip()
        if not title:
            return False

        for existing_tender in existing:
            existing_title = existing_tender.get("title", "").lower().strip()
            similarity = self._jaccard_similarity(title, existing_title)
            if similarity >= self.similarity_threshold:
                return True

        return False

    @staticmethod
    def _jaccard_similarity(text1: str, text2: str) -> float:
        """Compute Jaccard similarity between two strings (word-level)."""
        words1 = set(text1.split())
        words2 = set(text2.split())

        if not words1 or not words2:
            return 0.0

        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union)

    def reset(self):
        """Clear the fingerprint cache."""
        self._seen_fingerprints.clear()
