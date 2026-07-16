"""
SEPLE Tender Connectors — Email Parser
Fallback ingestion mechanism if portal automation is restricted (O10).
Parses daily alert emails from TenderTiger / Tender247.
"""
import logging
import email
from email import policy
from bs4 import BeautifulSoup
from typing import List, Optional
from datetime import datetime
from database.models import RawTender

logger = logging.getLogger(__name__)

class EmailParserConnector:
    """
    Parses structured alert emails sent by TenderTiger/Tender247.
    Requires an IMAP connection or a webhook receiving the emails.
    """
    
    def __init__(self, source_name: str):
        self.source_name = source_name
        
    def parse_email_content(self, raw_email_bytes: bytes) -> List[RawTender]:
        """Parse raw RFC822 email bytes into RawTenders."""
        tenders = []
        try:
            msg = email.message_from_bytes(raw_email_bytes, policy=policy.default)
            
            # Find the HTML part
            html_content = None
            if msg.is_multipart():
                for part in msg.iter_parts():
                    if part.get_content_type() == 'text/html':
                        html_content = part.get_content()
                        break
            else:
                if msg.get_content_type() == 'text/html':
                    html_content = msg.get_content()
                    
            if not html_content:
                logger.warning(f"No HTML content found in email for {self.source_name}")
                return tenders
                
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Note: Selectors here depend heavily on the exact email format sent by the portals.
            # Assuming a table-based layout common in these emails:
            tender_rows = soup.find_all('table', class_='tender-block')
            
            for row in tender_rows:
                title_elem = row.find('a', class_='tender-title')
                val_elem = row.find('span', class_='value')
                date_elem = row.find('span', class_='deadline')
                auth_elem = row.find('span', class_='authority')
                
                title = title_elem.text.strip() if title_elem else "Unknown"
                url = title_elem['href'] if title_elem and 'href' in title_elem.attrs else None
                val = val_elem.text.strip() if val_elem else None
                deadline = date_elem.text.strip() if date_elem else None
                authority = auth_elem.text.strip() if auth_elem else None
                
                raw_tender = RawTender(
                    title=title,
                    value=val,
                    deadline=deadline,
                    issuing_authority=authority,
                    url=url,
                    source=self.source_name,
                    scraped_at=datetime.utcnow().isoformat()
                )
                tenders.append(raw_tender)
                
            logger.info(f"Parsed {len(tenders)} tenders from {self.source_name} email")
            return tenders
            
        except Exception as e:
            logger.error(f"Error parsing email for {self.source_name}: {e}")
            return tenders
