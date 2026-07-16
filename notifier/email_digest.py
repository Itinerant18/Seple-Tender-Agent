"""
SEPLE Tender Notifier — Email Digest
Generates and sends the daily digest of discovered tenders.
Implements PRD §8.1
"""
import os
import logging
from typing import List, Dict
import smtplib
from email.message import EmailMessage
from datetime import datetime

from database.models import Tender, FitLabel

logger = logging.getLogger(__name__)

class EmailDigestSender:
    
    def __init__(self):
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER")
        self.smtp_pass = os.getenv("SMTP_PASS")
        self.sender_email = os.getenv("SENDER_EMAIL", self.smtp_user)
        self.recipient_emails = os.getenv("RECIPIENT_EMAILS", "").split(",")
        
    def generate_html(self, tenders: List[Tender]) -> str:
        """Generate the HTML body for the daily digest."""
        
        # Group tenders
        strong_fits = [t for t in tenders if t.fit_classification == FitLabel.STRONG_FIT]
        potential_fits = [t for t in tenders if t.fit_classification == FitLabel.POTENTIAL_FIT]
        
        # We don't send Low Fits in the digest per PRD
        
        date_str = datetime.now().strftime("%d %b %Y")
        total = len(strong_fits) + len(potential_fits)
        
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .header {{ background: #2c3e50; color: white; padding: 15px; text-align: center; }}
                .summary {{ padding: 15px; background: #ecf0f1; margin: 10px 0; border-radius: 5px; }}
                .section-title {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 5px; }}
                .tender-card {{ border: 1px solid #ddd; border-left: 5px solid #3498db; margin: 15px 0; padding: 15px; border-radius: 4px; }}
                .tender-card.strong {{ border-left-color: #27ae60; }}
                .tender-card.potential {{ border-left-color: #f39c12; }}
                .meta {{ color: #7f8c8d; font-size: 0.9em; }}
                .meta-table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
                .meta-table th, .meta-table td {{ padding: 5px; text-align: left; border-bottom: 1px solid #eee; }}
                .meta-table th {{ width: 25%; color: #555; }}
                .btn {{ display: inline-block; padding: 8px 15px; background: #3498db; color: white; text-decoration: none; border-radius: 3px; margin-top: 10px; }}
                .alert {{ color: #c0392b; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>SEPLE Tender Intelligence Report</h2>
                <p>{date_str}</p>
            </div>
            
            <div class="summary">
                <p><strong>{total}</strong> relevant tenders found today.</p>
                <p>✅ <strong>{len(strong_fits)}</strong> Strong Fits | ⚠️ <strong>{len(potential_fits)}</strong> Need Human Review</p>
            </div>
        """
        
        # Helper to render a tender card
        def render_card(tender: Tender, css_class: str) -> str:
            val = tender.value_inr / 100000 if tender.value_inr else 0
            val_str = f"₹{val:,.2f} Lakh" if val > 0 else (tender.value_raw or "Not specified")
            deadline = tender.deadline.strftime("%d-%m-%Y %H:%M") if tender.deadline else "Not specified"
            
            prebid = tender.pre_bid_meeting.date if tender.pre_bid_meeting and tender.pre_bid_meeting.date else "None"
            gaps = "None identified"
            if tender.eligibility_gaps:
                gaps = "<br>".join([f"• {g}" for g in tender.eligibility_gaps])
                
            return f"""
            <div class="tender-card {css_class}">
                <h3>{tender.title}</h3>
                <p class="meta">{tender.issuing_authority or 'Unknown Authority'} | {tender.location or 'Unknown Location'}</p>
                
                <table class="meta-table">
                    <tr><th>Estimated Value</th><td>{val_str}</td></tr>
                    <tr><th>Submission Deadline</th><td><strong>{deadline}</strong></td></tr>
                    <tr><th>Pre-bid Meeting</th><td>{prebid}</td></tr>
                    <tr><th>Categories</th><td>{", ".join(tender.product_categories) if tender.product_categories else 'Unknown'}</td></tr>
                    <tr><th>Eligibility Gaps</th><td><span class="{'alert' if tender.eligibility_gaps else ''}">{gaps}</span></td></tr>
                </table>
                
                <p style="margin-top: 15px;"><strong>Analysis:</strong> {tender.matching_rationale or 'No rationale provided.'}</p>
                
                <a href="{tender.source_url or '#'}" class="btn" target="_blank">View Original Document</a>
            </div>
            """

        if strong_fits:
            html += '<h2 class="section-title">✅ Strong Fits (Apply / Review)</h2>'
            for t in strong_fits:
                html += render_card(t, "strong")
                
        if potential_fits:
            html += '<h2 class="section-title">⚠️ Needs Human Review (Possible fit or gaps)</h2>'
            for t in potential_fits:
                html += render_card(t, "potential")
                
        if not strong_fits and not potential_fits:
            html += "<p>No relevant tenders found today.</p>"
            
        html += """
            <div style="margin-top: 30px; font-size: 0.8em; color: #999; text-align: center;">
                <p>This is an automated digest from the SEPLE Tender Intelligence Agent.</p>
                <p>Confidential - Internal Use Only</p>
            </div>
        </body>
        </html>
        """
        return html

    async def send_digest(self, tenders: List[Tender]) -> bool:
        """Send the daily digest via email."""
        if not tenders:
            logger.info("No tenders to send in digest.")
            return True
            
        if not self.smtp_user or not self.smtp_pass or not self.recipient_emails:
            logger.error("Email configuration missing. Cannot send digest.")
            return False
            
        try:
            html_content = self.generate_html(tenders)
            
            msg = EmailMessage()
            msg['Subject'] = f"SEPLE Tender Digest - {datetime.now().strftime('%d %b %Y')}"
            msg['From'] = self.sender_email
            msg['To'] = ", ".join([e for e in self.recipient_emails if e])
            
            msg.set_content("Please view this email in an HTML-compatible client.")
            msg.add_alternative(html_content, subtype='html')
            
            # Using synchronous smtplib inside async function (acceptable for background task)
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_pass)
                server.send_message(msg)
                
            logger.info("Successfully sent daily email digest.")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email digest: {e}")
            return False
