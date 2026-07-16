"""
SEPLE Tender Processor — Eligibility Checker
Rule-based evaluation of extracted eligibility criteria against SEPLE's capabilities.
Provides a second layer of verification on top of the LLM classification.
"""
import re
from typing import Dict, List, Any
from database.models import EligibilityAssessment

class EligibilityChecker:
    """Evaluates tender requirements against company profile."""
    
    # These would ideally come from a config or database
    SEPLE_PROFILE = {
        "turnover_cr": 25.0,  # Example: 25 Cr
        "certifications": ["iso 9001", "iso 14001", "iso 27001"],
        "oem_partners": ["notifier", "morley", "apollo", "esser", "hikvision", "dahua", "bosch", "honeywell"],
        "locations": ["delhi", "ncr", "mumbai", "kolkata"]
    }
    
    @classmethod
    def evaluate(cls, assessment: EligibilityAssessment) -> EligibilityAssessment:
        """
        Evaluate an LLM-generated assessment against the hardcoded company profile
        to catch obvious gaps the LLM might have missed.
        """
        if not assessment:
            return assessment
            
        gaps = assessment.eligibility_gaps.copy()
        
        # Check Turnover
        if assessment.turnover_requirement:
            # Try to extract Cr value
            match = re.search(r'([\d\.]+)\s*(?:cr|crore)', assessment.turnover_requirement, re.IGNORECASE)
            if match:
                try:
                    req_val = float(match.group(1))
                    if req_val > cls.SEPLE_PROFILE["turnover_cr"]:
                        gaps.append(f"Turnover requirement ({req_val} Cr) exceeds company profile ({cls.SEPLE_PROFILE['turnover_cr']} Cr)")
                except ValueError:
                    pass
                    
        # Check Certifications
        for cert in assessment.certifications:
            # Simplified check
            clean_cert = cert.lower().replace(":", "").replace("-", " ")
            found = False
            for company_cert in cls.SEPLE_PROFILE["certifications"]:
                if company_cert.replace("-", " ") in clean_cert or clean_cert in company_cert.replace("-", " "):
                    found = True
                    break
            if not found:
                gaps.append(f"Required certification '{cert}' not found in company profile")
                
        # Check OEM
        if assessment.oem_authorization:
            auth_text = assessment.oem_authorization.lower()
            # If specific brands are mentioned, check if we partner with them
            mentioned_brands = [brand for brand in cls.SEPLE_PROFILE["oem_partners"] if brand in auth_text]
            # This is a soft check - if they ask for MAF but don't specify brand, we assume we can get it for our brands
            if "specific" in auth_text and not mentioned_brands:
                # E.g. "MAF required from CISCO"
                gaps.append("OEM authorization required for brands outside our stated partnerships")
                
        # Update the assessment
        assessment.eligibility_gaps = list(set(gaps)) # dedup
        
        if assessment.eligibility_gaps:
            assessment.eligibility_status = "Gaps Identified"
        elif assessment.eligibility_status != "Needs Verification":
            assessment.eligibility_status = "Likely Eligible"
            
        return assessment
