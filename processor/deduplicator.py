"""
SEPLE Tender Processor — Deduplicator
Handles generating unique fingerprints for tenders to prevent duplicates
across multiple sources (e.g. same tender on TenderTiger and Tender247).
"""
import hashlib
import re
from database.models import RawTender

class Deduplicator:
    
    @staticmethod
    def generate_fingerprint(tender: RawTender) -> str:
        """
        Generate a unique hash for a tender to enable cross-source deduplication.
        Strategy:
        1. If a strong reference number (GeM, CPPP) exists, use that.
        2. Otherwise, hash a combination of title (normalized), authority, and deadline.
        """
        
        # 1. Use strong reference if available
        if tender.tender_reference:
            # Clean up the reference (remove spaces, uppercase)
            clean_ref = re.sub(r'[^A-Z0-9/_-]', '', tender.tender_reference.upper())
            # If it looks like a real reference (not just a generic internal ID), use it
            if len(clean_ref) > 5:
                return hashlib.md5(clean_ref.encode('utf-8')).hexdigest()
                
        # 2. Fallback to heuristic composite key
        components = []
        
        # Normalize title: lowercase, remove punctuation, remove extra spaces
        if tender.title:
            clean_title = re.sub(r'[^\w\s]', '', tender.title.lower())
            clean_title = re.sub(r'\s+', ' ', clean_title).strip()
            # Only use the first 50 chars to avoid minor variations breaking the hash
            components.append(clean_title[:50])
            
        # Add Authority
        if tender.issuing_authority:
            clean_auth = re.sub(r'[^\w\s]', '', tender.issuing_authority.lower())
            components.append(clean_auth.strip())
            
        # Add deadline date (ignore time to avoid timezone/format differences)
        if tender.deadline:
            # Extract just the date part (YYYY-MM-DD) if possible
            date_match = re.search(r'(\d{4}[-/]\d{2}[-/]\d{2}|\d{2}[-/]\d{2}[-/]\d{4})', tender.deadline)
            if date_match:
                components.append(date_match.group(1).replace('/', '-'))
            else:
                components.append(tender.deadline.split()[0])
                
        # If we have nothing, fallback to URL
        if not components and tender.url:
            components.append(tender.url)
            
        # Combine and hash
        fingerprint_str = "|".join(components)
        return hashlib.md5(fingerprint_str.encode('utf-8')).hexdigest()
