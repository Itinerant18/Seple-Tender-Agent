"""
SEPLE Tender Processor — PDF Parser
Extracts text and structured data (like BOQ) from tender PDFs.
"""
import logging
import io
import re
from typing import Optional, List, Dict
import pdfplumber

logger = logging.getLogger(__name__)

class PDFParser:
    """Parses tender documents to extract text and tables."""
    
    def __init__(self):
        # Common section headers in Indian tenders
        self.SCOPE_HEADERS = re.compile(r'(?i)^(?:Scope\s*of\s*Work|Brief\s*Description|Technical\s*Specifications|Scope\s*of\s*Supply)')
        self.ELIGIBILITY_HEADERS = re.compile(r'(?i)^(?:Eligibility\s*Criteria|Pre[- ]?Qualification|Minimum\s*Qualification)')
        self.BOQ_HEADERS = re.compile(r'(?i)^(?:Bill\s*of\s*Quantities|BOQ|Price\s*Bid|Schedule\s*of\s*Rates|Price\s*Schedule)')
        
    def extract_text(self, file_path: str, max_pages: int = 50) -> Optional[str]:
        """Extract all text from a PDF, up to max_pages."""
        try:
            full_text = []
            with pdfplumber.open(file_path) as pdf:
                # Some govt PDFs have hundreds of boilerplate pages, so we limit
                pages_to_read = min(len(pdf.pages), max_pages)
                for i in range(pages_to_read):
                    page = pdf.pages[i]
                    text = page.extract_text()
                    if text:
                        full_text.append(text)
                        
            return "\n\n".join(full_text)
        except Exception as e:
            logger.error(f"Failed to extract text from {file_path}: {e}")
            return None

    def extract_sections(self, text: str) -> Dict[str, str]:
        """
        Attempt to split text into logical sections based on headers.
        Since PDFs don't preserve semantic structure perfectly, this uses heuristics.
        """
        sections = {
            "scope": "",
            "eligibility": "",
            "boq": ""
        }
        
        if not text:
            return sections
            
        lines = text.split('\n')
        current_section = None
        
        for line in lines:
            line_clean = line.strip()
            if not line_clean:
                continue
                
            # Heuristic: headers are usually short
            if len(line_clean) < 60:
                if self.SCOPE_HEADERS.match(line_clean):
                    current_section = "scope"
                    continue
                elif self.ELIGIBILITY_HEADERS.match(line_clean):
                    current_section = "eligibility"
                    continue
                elif self.BOQ_HEADERS.match(line_clean):
                    current_section = "boq"
                    continue
                    
            if current_section:
                sections[current_section] += line_clean + "\n"
                
        return sections
        
    def extract_tables(self, file_path: str, max_pages: int = 20) -> List[List[List[str]]]:
        """Extract tables from the PDF, useful for BOQ extraction."""
        tables = []
        try:
            with pdfplumber.open(file_path) as pdf:
                pages_to_read = min(len(pdf.pages), max_pages)
                for i in range(pages_to_read):
                    page = pdf.pages[i]
                    # Extract tables with default settings
                    page_tables = page.extract_tables()
                    for table in page_tables:
                        # Clean up None values
                        clean_table = [[cell if cell else "" for cell in row] for row in table]
                        tables.append(clean_table)
            return tables
        except Exception as e:
            logger.error(f"Failed to extract tables from {file_path}: {e}")
            return []
