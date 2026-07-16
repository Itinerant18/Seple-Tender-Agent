"""
SEPLE Tender Processor — Synopsis Generator
Generates the markdown synopsis (F9) for a tender based on its analysis.
"""
from database.models import Tender, TenderAnalysis

class SynopsisGenerator:
    """Generates Markdown synopses for tenders."""
    
    @staticmethod
    def generate(tender: Tender, analysis: TenderAnalysis) -> str:
        """Generate the standard PRD §F9 synopsis format."""
        
        # Format dates nicely if they exist
        pub_date = tender.publication_date.isoformat() if tender.publication_date else "Not specified"
        deadline = tender.deadline.strftime("%Y-%m-%d %H:%M") if tender.deadline else "Not specified"
        
        eligibility = analysis.eligibility_assessment
        el_turnover = eligibility.turnover_requirement if eligibility else "Not specified"
        el_exp = eligibility.experience_requirement if eligibility else "Not specified"
        el_oem = eligibility.oem_authorization if eligibility else "Not specified"
        el_certs = ", ".join(eligibility.certifications) if eligibility and eligibility.certifications else "None specified"
        el_other = ", ".join(eligibility.other_conditions) if eligibility and eligibility.other_conditions else "None specified"
        el_status = eligibility.eligibility_status if eligibility else "Unknown"
        el_gaps = "\n".join([f"- {gap}" for gap in eligibility.eligibility_gaps]) if eligibility and eligibility.eligibility_gaps else "None identified"

        mand = analysis.mandatory_activities or {}
        prebid = mand.get("pre_bid_meeting", {})
        prebid_str = prebid.get("date", "Not specified") if prebid else "Not specified"
        
        site = mand.get("site_visit", {})
        site_str = site.get("date", "Not specified") if site else "Not specified"
        
        fit = analysis.fit_classification.value if analysis.fit_classification else "Unknown"
        conf = analysis.confidence.value if analysis.confidence else "Unknown"
        
        md = f"""# Tender Synopsis

## Basic Information
| Field | Value |
|-------|-------|
| Tender Reference | {tender.tender_reference or 'Unknown'} |
| Authority | {tender.issuing_authority or 'Unknown'} |
| Location | {tender.location or 'Unknown'} |
| Publication Date | {pub_date} |
| Submission Deadline | {deadline} |
| Estimated Value | {tender.value_raw or 'Not stated'} |
| EMD | {tender.emd_amount or 'Not stated'} |
| Tender Fee | {tender.tender_fee or 'Not stated'} |
| Source | [{tender.source_url or 'Link'}]({tender.source_url or '#'}) |

## Scope of Work
{analysis.scope_summary or tender.description or 'No summary available.'}

## Technical Requirements
"""
        if analysis.key_requirements:
            for req in analysis.key_requirements:
                md += f"- {req}\n"
        else:
            md += "No specific technical requirements extracted.\n"

        md += f"""
## Eligibility Requirements
- **Turnover**: {el_turnover}
- **Experience**: {el_exp}
- **OEM Authorization**: {el_oem}
- **Certifications**: {el_certs}
- **Other**: {el_other}

## Eligibility Assessment
**Status**: {el_status}
**Identified Gaps**:
{el_gaps}

## Important Dates
| Milestone | Date |
|-----------|------|
| Pre-bid Meeting | {prebid_str} |
| Site Visit | {site_str} |
| Clarification Deadline | {mand.get("clarification_deadline", "Not specified")} |
| Submission Deadline | {deadline} |

## Classification
- **Fit**: {fit.upper()} (Confidence: {conf.title()})
- **Rationale**: {analysis.matching_rationale or 'None provided'}
- **Matched Categories**: {", ".join(analysis.matched_categories) if analysis.matched_categories else 'None'}
"""
        if analysis.uncertainty_notes:
            md += "\n**Concerns / Uncertainties**:\n"
            for note in analysis.uncertainty_notes:
                md += f"- {note}\n"
                
        # Simple recommendation heuristic
        rec = "REVIEW"
        if fit == "strong_fit" and el_status != "Gaps Identified":
            rec = "APPLY - Strong fit with no apparent eligibility gaps"
        elif fit == "low_fit":
            rec = "SKIP - Low fit"
            
        md += f"\n## Recommendation\n**{rec}**"
        
        return md
