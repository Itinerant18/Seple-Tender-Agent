"""
SEPLE Tender Processor — Classifier
Orchestrates LLM-based classification of tenders using the OpenRouter API or Hermes Agent.
"""
import os
import json
import logging
from typing import Dict, Any, Optional
from database.models import RawTender, TenderAnalysis, FitLabel, ConfidenceLevel, EligibilityAssessment, DocumentReview
import httpx

logger = logging.getLogger(__name__)

class TenderClassifier:
    """Classifies tenders using LLM based on the SEPLE SKILL.md guidelines."""
    
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("LLM_MODEL", "gpt-5.5")
        self.system_prompt = self._load_skill()

    def _load_skill(self) -> str:
        """Load the Tender Intelligence skill document to use as the system prompt."""
        try:
            import pathlib
            skill_path = pathlib.Path(__file__).parent.parent / "skills" / "tender-intelligence" / "SKILL.md"
            if skill_path.exists():
                return skill_path.read_text()
        except Exception as e:
            logger.error(f"Failed to load SKILL.md: {e}")
            
        return "You are a tender classification agent for Security Engineers Pvt Ltd."

    async def classify(self, raw_tender: RawTender, document_text: str = None) -> TenderAnalysis:
        """Classify a tender using the LLM."""
        if not self.api_key:
            logger.warning("OPENAI_API_KEY not set. Returning dummy classification.")
            return self._fallback_classification(raw_tender)
            
        prompt = self._build_prompt(raw_tender, document_text)
        
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": self.system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        "response_format": {"type": "json_object"}
                    }
                )
                response.raise_for_status()
                result = response.json()
                
                content = result["choices"][0]["message"]["content"]
                
                # Parse the JSON response
                try:
                    data = json.loads(content)
                    return self._parse_llm_response(raw_tender, data)
                except json.JSONDecodeError:
                    logger.error("Failed to parse LLM response as JSON")
                    return self._fallback_classification(raw_tender)
                    
        except Exception as e:
            logger.error(f"LLM Classification failed: {e}")
            return self._fallback_classification(raw_tender)
            
    def _build_prompt(self, raw: RawTender, doc_text: str) -> str:
        prompt = f"""
        Please classify the following tender based on your guidelines.
        
        TITLE: {raw.title}
        AUTHORITY: {raw.issuing_authority or 'Unknown'}
        VALUE: {raw.value or 'Unknown'}
        DESCRIPTION: {raw.description or 'None'}
        """
        
        if doc_text:
            # Truncate doc text if it's too long (keep first 20k chars)
            truncated = doc_text[:20000]
            prompt += f"\n\nDOCUMENT EXTRACT:\n{truncated}"
            
        prompt += "\n\nProvide your analysis as a JSON object strictly matching the schema defined in your instructions."
        return prompt

    def _parse_llm_response(self, raw: RawTender, data: dict) -> TenderAnalysis:
        """Convert the LLM JSON output to a TenderAnalysis object."""
        try:
            # Handle enums safely
            fit_map = {
                "Strong Fit": FitLabel.STRONG_FIT,
                "Potential Fit": FitLabel.POTENTIAL_FIT,
                "Needs Human Review": FitLabel.POTENTIAL_FIT,
                "Low Fit": FitLabel.LOW_FIT
            }
            conf_map = {
                "High": ConfidenceLevel.HIGH,
                "Medium": ConfidenceLevel.MEDIUM,
                "Low": ConfidenceLevel.LOW
            }
            
            fit = fit_map.get(data.get("fit_classification"), FitLabel.POTENTIAL_FIT)
            conf = conf_map.get(data.get("confidence"), ConfidenceLevel.MEDIUM)
            
            eligibility_data = data.get("eligibility_assessment", {})
            eligibility = EligibilityAssessment(
                turnover_requirement=eligibility_data.get("turnover_requirement"),
                experience_requirement=eligibility_data.get("experience_requirement"),
                oem_authorization=eligibility_data.get("oem_authorization"),
                certifications=eligibility_data.get("certifications", []),
                local_office=eligibility_data.get("local_office"),
                other_conditions=eligibility_data.get("other_conditions", []),
                eligibility_gaps=eligibility_data.get("eligibility_gaps", []),
                eligibility_status=eligibility_data.get("eligibility_status", "Needs Verification")
            )
            
            docs_reviewed = []
            for doc in data.get("documents_reviewed", []):
                docs_reviewed.append(DocumentReview(
                    name=doc.get("name", "Unknown"),
                    reviewed=doc.get("reviewed", False),
                    reason=doc.get("reason")
                ))
            
            return TenderAnalysis(
                tender_id=None, # Will be set by repository
                fit_classification=fit,
                confidence=conf,
                matched_keywords=data.get("matched_keywords", []),
                matched_categories=data.get("matched_categories", []),
                matching_rationale=data.get("matching_rationale"),
                scope_summary=data.get("scope_summary"),
                key_requirements=data.get("key_requirements", []),
                eligibility_assessment=eligibility,
                mandatory_activities=data.get("mandatory_activities"),
                uncertainty_notes=data.get("uncertainty_notes", []),
                documents_reviewed=docs_reviewed,
                raw_analysis=data,
                analysis_model=self.model
            )
        except Exception as e:
            logger.error(f"Error parsing LLM response dict: {e}")
            return self._fallback_classification(raw)

    def _fallback_classification(self, raw: RawTender) -> TenderAnalysis:
        """Basic keyword-based fallback if LLM is unavailable."""
        from processor.keywords import SEARCH_KEYWORDS
        title_lower = raw.title.lower()

        matched = [k for k in SEARCH_KEYWORDS if k in title_lower]

        # PRD 6.5 recall-over-precision: LLM down = uncertain, never silently
        # drop to Low Fit. Surface for human review instead.
        return TenderAnalysis(
            tender_id=None,
            fit_classification=FitLabel.POTENTIAL_FIT,
            confidence=ConfidenceLevel.LOW,
            matched_keywords=matched,
            matching_rationale="LLM unavailable — keyword fallback only. Needs human review.",
            uncertainty_notes=["Classification not LLM-verified; fit and eligibility unassessed."],
            analysis_model="fallback-regex"
        )
