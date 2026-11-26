"""
SEPLE Tender Notifier — Email Digest
Generates and sends the daily digest of discovered tenders.
Implements PRD §8.1
"""
import asyncio
from datetime import datetime
from email.message import EmailMessage
import logging
import os
import smtplib
from typing import List, Optional

from database.models import Tender, FitLabel

logger = logging.getLogger(__name__)


class EmailDigestSender:
    
    def __init__(self):
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER")
        self.smtp_pass = os.getenv("SMTP_PASS")
        self.sender_email = os.getenv("SENDER_EMAIL", self.smtp_user)
        self.recipient_emails = [e.strip() for e in os.getenv("RECIPIENT_EMAILS", "").split(",") if e.strip()]
        
    def _smtp_connect(self):
        """Create and return an authenticated TLS SMTP server connection."""
        server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=20)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(self.smtp_user, self.smtp_pass)
        return server

    def _send_message_sync(self, msg: EmailMessage) -> None:
        server = self._smtp_connect()
        try:
            server.send_message(msg)
        finally:
            try:
                server.quit()
            except Exception:
                pass
    
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
            logger.error("Email configuration missing. Cannot send digest. "
                        "Set SMTP_USER, SMTP_PASS, and RECIPIENT_EMAILS in environment. "
                        "Pending email notifications will retry on the next scan cycle.")
            return False
            
        # Filter to only relevant tenders (strong + potential fit)
        relevant = [t for t in tenders if t.fit_classification in (FitLabel.STRONG_FIT, FitLabel.POTENTIAL_FIT)]
        
        if not relevant:
            logger.info("No relevant (strong/potential fit) tenders to send in digest.")
            return True
        
        try:
            html_content = self.generate_html(relevant)
            
            msg = EmailMessage()
            msg['Subject'] = f"SEPLE Tender Digest - {datetime.now().strftime('%d %b %Y')}"
            msg['From'] = self.sender_email
            msg['To'] = ", ".join(self.recipient_emails)
            
            msg.set_content("Please view this email in an HTML-compatible client.")
            msg.add_alternative(html_content, subtype='html')
            
            await asyncio.to_thread(self._send_message_sync, msg)
            
            logger.info("Successfully sent daily email digest to %d recipients.", len(self.recipient_emails))
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email digest: {e}")
            return False

    async def send_plain_email(
        self,
        recipients: List[str],
        subject: str,
        body_text: str,
        *,
        cc: Optional[List[str]] = None,
    ) -> bool:
        """Send a plain-text email using the configured SMTP sender."""
        clean_to = [addr.strip() for addr in recipients if addr and addr.strip()]
        clean_cc = [addr.strip() for addr in (cc or []) if addr and addr.strip() and addr.strip() not in clean_to]
        if not clean_to:
            logger.warning("No recipients provided for email %r", subject)
            return False
        if not self.smtp_user or not self.smtp_pass:
            logger.error("SMTP credentials missing; cannot send email %r", subject)
            return False

        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = self.sender_email or self.smtp_user
            msg["To"] = ", ".join(clean_to)
            if clean_cc:
                msg["Cc"] = ", ".join(clean_cc)
            msg.set_content(body_text)

            await asyncio.to_thread(self._send_message_sync, msg)
            logger.info("Sent email %r to %s", subject, ", ".join(clean_to))
            return True
        except Exception as e:
            logger.error("Failed to send email %r: %s", subject, e)
            return False

    async def send_tender247_unblock_request(
        self,
        *,
        error_detail: str,
        egress_ip: Optional[str] = None,
        account_email: Optional[str] = None,
    ) -> bool:
        """Email Tender247 support to unblock our IP, or notify internal team if unset."""
        support_emails = [
            e.strip() for e in os.getenv("TENDER247_SUPPORT_EMAIL", "").split(",") if e.strip()
        ]
        acct = account_email or os.getenv("TENDER247_EMAIL") or self.sender_email or "info@seple.in"
        ip_line = f"Server / Egress Public IP: {egress_ip}\n" if egress_ip else ""

        if support_emails:
            subject = f"Request to Unblock / Whitelist IP for Tender247 Account ({acct})"
            body = (
                "Hello Tender247 Support Team,\n\n"
                f"Our automated daily tender sync for subscribed account {acct} is currently blocked "
                "with a Cloudflare 403 / access block.\n\n"
                f"Account Email: {acct}\n"
                f"{ip_line}"
                f"Observed Error: {error_detail}\n\n"
                "Could you please whitelist / unblock access for our account and IP?\n\n"
                "Thanks & Regards,\n"
                "SEPLE Team\n"
                f"{self.sender_email or self.smtp_user or ''}\n"
            )
            return await self.send_plain_email(
                support_emails, subject, body, cc=self.recipient_emails
            )

        if not self.recipient_emails:
            return False
        subject = "[Action Needed] Tender247 IP Blocked — Email Support to Unblock"
        body = (
            "Tender247 automated login/scraping appears blocked (Cloudflare / IP block).\n\n"
            f"Account Email: {acct}\n"
            f"{ip_line}"
            f"Error: {error_detail}\n\n"
            "Set TENDER247_SUPPORT_EMAIL in environment/Secrets Manager to email Tender247 support "
            "automatically next time, or email them manually with the IP above to unblock.\n"
        )
        return await self.send_plain_email(self.recipient_emails, subject, body)
