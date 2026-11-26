"""
SEPLE Tender Connectors — Email Parser
Fallback ingestion mechanism if portal automation is restricted (O10).
Parses daily alert emails from TenderTiger / Tender247 via .eml bytes or IMAP.
"""
import asyncio
from datetime import datetime, timedelta, timezone
import email
from email import policy
from html.parser import HTMLParser
import imaplib
import logging
import os
import re
from typing import List, Optional
from urllib.parse import urlsplit

from database.models import RawTender

logger = logging.getLogger(__name__)

_SKIP_HREF_PARTS = (
    "unsubscribe",
    "login",
    "signup",
    "register",
    "privacy",
    "terms",
    "contact",
    "about",
    "facebook.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "youtube.com",
    "mailto:",
    "tel:",
)
_REF_RE = re.compile(
    r"(?:Tender\s*(?:No|ID|Ref(?:erence)?)|T247\s*ID)\s*[:#-]\s*([A-Za-z0-9/_-]{3,})",
    re.I,
)
_DEADLINE_RE = re.compile(
    r"(?:Closing|End|Last|Submission(?:\s*End)?|Due)\s*Date\s*[:#-]\s*([A-Za-z0-9,:/\s-]{6,35})",
    re.I,
)
_VALUE_RE = re.compile(
    r"(?:Estimated\s*(?:Cost|Value)|Tender\s*Value|Value|Amount)\s*[:#-]\s*([^\n|;]{2,40})",
    re.I,
)
_AUTH_RE = re.compile(
    r"(?:Organization|Authority|Department|Buyer|Company)\s*[:#-]\s*([^\n|;]{3,120})",
    re.I,
)
_LOC_RE = re.compile(
    r"(?:Location|City|State|Site)\s*[:#-]\s*([^\n|;]{2,80})",
    re.I,
)
_T247_URL_ID_RE = re.compile(r"/tender/(\d+)(?:/|$)", re.I)
_CONTAINER_TAGS = ("tr", "div", "td", "li", "table")


def _match_field(pattern: re.Pattern[str], text: str) -> Optional[str]:
    m = pattern.search(text or "")
    return m.group(1).strip(" :-|") if m else None


def _is_candidate_tender_link(href: str, text: str) -> bool:
    if not href:
        return False
    lower = href.lower()
    if any(part in lower for part in _SKIP_HREF_PARTS):
        return False
    parsed = urlsplit(href)
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    path = parsed.path or ""
    if "tender247.com" not in host:
        return False
    if _T247_URL_ID_RE.search(path):
        return True
    return len(path.strip("/")) >= 8 and len((text or "").strip()) >= 12


class _EmailHTMLParser(HTMLParser):
    """Stdlib HTML parser extracting structured `.tender-block` cards and link rows."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[dict] = []
        self.anchors: list[dict] = []
        self._block_depth: list[str] = []
        self._current_block: Optional[dict] = None
        self._active_span_class: Optional[str] = None
        self._span_parts: list[str] = []
        self._active_anchor: Optional[dict] = None
        self._containers: list[dict] = []

    def _enclosing_container(self) -> Optional[dict]:
        for container in reversed(self._containers):
            if container["tag"] == "tr":
                return container
        return self._containers[-1] if self._containers else None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        tag_l = tag.lower()
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        classes = set(attr_map.get("class", "").split())

        if self._current_block is not None:
            self._block_depth.append(tag_l)
        elif tag_l == "table" and "tender-block" in classes:
            self._current_block = {}
            self._block_depth = ["table"]

        if self._current_block is not None and tag_l == "span":
            for cls in ("value", "deadline", "authority"):
                if cls in classes:
                    self._active_span_class = cls
                    self._span_parts = []
                    break

        if tag_l in _CONTAINER_TAGS:
            self._containers.append({"tag": tag_l, "chunks": []})

        if tag_l == "a" and attr_map.get("href"):
            self._active_anchor = {
                "href": attr_map["href"].strip(),
                "classes": classes,
                "text_parts": [],
                "container": self._enclosing_container(),
            }

    def handle_endtag(self, tag: str) -> None:
        tag_l = tag.lower()

        if tag_l == "a" and self._active_anchor is not None:
            anchor = self._active_anchor
            self._active_anchor = None
            text = " ".join(anchor["text_parts"]).strip()
            if self._current_block is not None and "tender-title" in anchor["classes"]:
                self._current_block["title"] = text or "Unknown"
                self._current_block["url"] = anchor["href"]
            self.anchors.append(
                {
                    "href": anchor["href"],
                    "text": text,
                    "container": anchor["container"],
                }
            )

        if tag_l == "span" and self._active_span_class is not None:
            if self._current_block is not None:
                self._current_block[self._active_span_class] = " ".join(self._span_parts).strip()
            self._active_span_class = None
            self._span_parts = []

        if tag_l in _CONTAINER_TAGS:
            for idx in range(len(self._containers) - 1, -1, -1):
                if self._containers[idx]["tag"] == tag_l:
                    self._containers.pop(idx)
                    break

        if self._current_block is not None and self._block_depth:
            if self._block_depth[-1] == tag_l:
                self._block_depth.pop()
            if not self._block_depth:
                self.blocks.append(self._current_block)
                self._current_block = None

    def handle_data(self, data: str) -> None:
        cleaned = " ".join(data.split())
        if not cleaned:
            return
        if self._active_anchor is not None:
            self._active_anchor["text_parts"].append(cleaned)
        if self._active_span_class is not None:
            self._span_parts.append(cleaned)
        for container in self._containers:
            container["chunks"].append(cleaned)


class EmailParserConnector:
    """
    Parses structured alert emails sent by TenderTiger/Tender247.
    Supports raw RFC822 bytes (from webhook/.eml) as well as read-only IMAP polling.
    """

    def __init__(self, source_name: str = "Tender247", *, sender_filter: Optional[str] = None):
        self.source_name = source_name
        self.sender_filter = (sender_filter or source_name).lower()

    @staticmethod
    def _imap_config() -> Optional[dict]:
        """Resolve IMAP credentials from IMAP_* or fall back to SMTP_* env vars."""
        user = (os.getenv("IMAP_USER") or os.getenv("SMTP_USER") or "").strip()
        password = (os.getenv("IMAP_PASS") or os.getenv("SMTP_PASS") or "").strip()
        smtp_srv = (os.getenv("SMTP_SERVER") or "").strip().lower()
        host = (os.getenv("IMAP_SERVER") or "").strip()
        if not host and smtp_srv:
            if smtp_srv in ("smtp.office365.com", "smtp-mail.outlook.com"):
                host = "outlook.office365.com"
            elif smtp_srv.startswith("smtp."):
                host = smtp_srv.replace("smtp.", "imap.", 1)
        if not (host and user and password):
            return None
        return {
            "host": host,
            "port": int(os.getenv("IMAP_PORT", "993")),
            "user": user,
            "password": password,
            "folder": (os.getenv("IMAP_FOLDER") or "INBOX").strip() or "INBOX",
        }

    @staticmethod
    def _extract_html(raw_email_bytes: bytes) -> Optional[str]:
        """Extract HTML body from RFC822 bytes or raw HTML email export."""
        stripped = raw_email_bytes.lstrip()
        if stripped.startswith(b"<"):
            return raw_email_bytes.decode("utf-8", errors="replace")

        msg = email.message_from_bytes(raw_email_bytes, policy=policy.default)
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                content = part.get_content()
                if isinstance(content, bytes):
                    return content.decode("utf-8", errors="replace")
                return content
        return None

    def _parse_structured_blocks(self, parsed: _EmailHTMLParser, scraped_at: str) -> List[RawTender]:
        tenders: List[RawTender] = []
        for block in parsed.blocks:
            tenders.append(
                RawTender(
                    title=block.get("title") or "Unknown",
                    value=block.get("value"),
                    deadline=block.get("deadline"),
                    issuing_authority=block.get("authority"),
                    url=block.get("url"),
                    source=self.source_name,
                    scraped_at=scraped_at,
                )
            )
        return tenders

    def _parse_tender_links(self, parsed: _EmailHTMLParser, scraped_at: str) -> List[RawTender]:
        """Fallback parser for real-world Tender247 HTML alert rows without custom CSS classes."""
        tenders: List[RawTender] = []
        seen_keys: set[str] = set()

        for anchor in parsed.anchors:
            href = anchor["href"]
            link_text = anchor["text"]
            if not _is_candidate_tender_link(href, link_text):
                continue

            container = anchor["container"]
            block_text = " | ".join(container["chunks"]) if container and container["chunks"] else link_text
            url_id_match = _T247_URL_ID_RE.search(urlsplit(href).path)
            tender_ref = _match_field(_REF_RE, block_text) or (
                url_id_match.group(1) if url_id_match else None
            )

            dedup_key = tender_ref or href
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            title = link_text if len(link_text) >= 12 else block_text[:300]
            if (
                title.lower().startswith(("view ", "click ", "read more", "download"))
                and len(block_text) > len(link_text)
            ):
                title = block_text[:300]

            tenders.append(
                RawTender(
                    title=(title or tender_ref or "Tender247 Alert")[:300],
                    description=block_text[:1500] if block_text else None,
                    tender_reference=tender_ref,
                    value=_match_field(_VALUE_RE, block_text),
                    deadline=_match_field(_DEADLINE_RE, block_text),
                    issuing_authority=_match_field(_AUTH_RE, block_text),
                    location=_match_field(_LOC_RE, block_text),
                    url=href,
                    source=self.source_name,
                    search_term="(email digest)",
                    scraped_at=scraped_at,
                )
            )
        return tenders

    def parse_email_content(self, raw_email_bytes: bytes) -> List[RawTender]:
        """Parse raw RFC822 email bytes (or HTML body) into RawTenders."""
        try:
            html_content = self._extract_html(raw_email_bytes)
            if not html_content:
                logger.warning("No HTML content found in email for %s", self.source_name)
                return []

            parser = _EmailHTMLParser()
            parser.feed(html_content)
            parser.close()

            scraped_at = datetime.now(timezone.utc).isoformat()
            tenders = self._parse_structured_blocks(parser, scraped_at)
            if not tenders:
                tenders = self._parse_tender_links(parser, scraped_at)

            logger.info("Parsed %d tenders from %s email", len(tenders), self.source_name)
            return tenders
        except Exception as e:
            logger.error("Error parsing email for %s: %s", self.source_name, e)
            return []

    def fetch_from_imap(
        self, days_back: Optional[int] = None, max_emails: int = 20
    ) -> List[RawTender]:
        """Read recent matching alert emails via IMAP without marking them read."""
        cfg = self._imap_config()
        if cfg is None:
            logger.info("IMAP not configured; skipping %s email fetch", self.source_name)
            return []

        lookback = days_back if days_back is not None else int(os.getenv("TENDER247_EMAIL_DAYS_BACK", "2"))
        since_str = (datetime.now(timezone.utc) - timedelta(days=max(0, lookback))).strftime("%d-%b-%Y")

        all_tenders: List[RawTender] = []
        seen: set[str] = set()
        imap = imaplib.IMAP4_SSL(cfg["host"], cfg["port"], timeout=20)
        try:
            imap.login(cfg["user"], cfg["password"])
            status, _ = imap.select(cfg["folder"], readonly=True)
            if status != "OK":
                raise RuntimeError(f"Unable to open IMAP folder {cfg['folder']!r}")
            typ, data = imap.search(
                None, "SINCE", since_str, "OR", "FROM", self.sender_filter, "SUBJECT", self.sender_filter
            )
            if typ != "OK":
                return []
            ids = data[0].split() if data and data[0] else []
            for eid in ids[-max_emails:]:
                fetch_status, msg_data = imap.fetch(eid, "(BODY.PEEK[])")
                if fetch_status != "OK" or not msg_data:
                    continue
                raw_bytes = next(
                    (item[1] for item in msg_data if isinstance(item, tuple) and isinstance(item[1], bytes)),
                    None,
                )
                if not raw_bytes:
                    continue
                for tender in self.parse_email_content(raw_bytes):
                    key = tender.tender_reference or tender.url or tender.title
                    if key not in seen:
                        seen.add(key)
                        all_tenders.append(tender)
        finally:
            try:
                imap.logout()
            except Exception:
                pass

        logger.info("Fetched %d unique tenders from %s IMAP emails", len(all_tenders), self.source_name)
        return all_tenders

    async def scrape_tenders(self, keywords: List[str] = None, days_back: int = 2) -> List[RawTender]:
        """Async connector-compatible wrapper around fetch_from_imap()."""
        return await asyncio.to_thread(self.fetch_from_imap, days_back=days_back)

    async def close(self) -> None:
        return None
