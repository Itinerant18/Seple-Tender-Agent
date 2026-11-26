"""Tests for Office365 SMTP handshake, Tender247 unblock email, and 7-day cooldown."""

from email.message import EmailMessage
from unittest.mock import AsyncMock

import pytest

from notifier.email_digest import EmailDigestSender


def test_smtp_connect_performs_ehlo_around_starttls(monkeypatch):
    calls = []

    class _FakeSMTP:
        def __init__(self, host, port, timeout=None):
            calls.append(("init", host, port, timeout))

        def ehlo(self):
            calls.append(("ehlo",))

        def starttls(self):
            calls.append(("starttls",))

        def login(self, user, pwd):
            calls.append(("login", user, pwd))

    monkeypatch.setenv("SMTP_SERVER", "smtp.office365.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "info@seple.in")
    monkeypatch.setenv("SMTP_PASS", "app-secret")
    monkeypatch.setattr("notifier.email_digest.smtplib.SMTP", _FakeSMTP)

    sender = EmailDigestSender()
    sender._smtp_connect()

    assert calls == [
        ("init", "smtp.office365.com", 587, 20),
        ("ehlo",),
        ("starttls",),
        ("ehlo",),
        ("login", "info@seple.in", "app-secret"),
    ]


@pytest.mark.asyncio
async def test_unblock_request_emails_support_with_cc_when_configured(monkeypatch):
    monkeypatch.setenv("SMTP_USER", "info@seple.in")
    monkeypatch.setenv("SMTP_PASS", "app-secret")
    monkeypatch.setenv("SENDER_EMAIL", "info@seple.in")
    monkeypatch.setenv("RECIPIENT_EMAILS", "team@seple.in")
    monkeypatch.setenv("TENDER247_SUPPORT_EMAIL", "support@tender247.example")
    monkeypatch.setenv("TENDER247_EMAIL", "info@seple.in")

    sent_msgs: list[EmailMessage] = []
    sender = EmailDigestSender()
    monkeypatch.setattr(sender, "_send_message_sync", sent_msgs.append)

    ok = await sender.send_tender247_unblock_request(
        error_detail="Cloudflare anti-bot challenge (403)",
        egress_ip="52.76.118.147",
    )

    assert ok is True
    assert len(sent_msgs) == 1
    msg = sent_msgs[0]
    assert msg["From"] == "info@seple.in"
    assert msg["To"] == "support@tender247.example"
    assert msg["Cc"] == "team@seple.in"
    assert "52.76.118.147" in msg.get_content()
    assert "info@seple.in" in msg.get_content()


@pytest.mark.asyncio
async def test_unblock_request_alerts_internal_team_if_support_email_unset(monkeypatch):
    monkeypatch.setenv("SMTP_USER", "info@seple.in")
    monkeypatch.setenv("SMTP_PASS", "app-secret")
    monkeypatch.setenv("SENDER_EMAIL", "info@seple.in")
    monkeypatch.setenv("RECIPIENT_EMAILS", "team@seple.in")
    monkeypatch.delenv("TENDER247_SUPPORT_EMAIL", raising=False)

    sent_msgs: list[EmailMessage] = []
    sender = EmailDigestSender()
    monkeypatch.setattr(sender, "_send_message_sync", sent_msgs.append)

    ok = await sender.send_tender247_unblock_request(
        error_detail="Cloudflare 403",
        egress_ip="52.76.118.147",
    )

    assert ok is True
    assert sent_msgs[0]["To"] == "team@seple.in"
    assert "Action Needed" in sent_msgs[0]["Subject"]


@pytest.mark.asyncio
async def test_orchestrator_unblock_notification_respects_7_day_cooldown(monkeypatch):
    pytest.importorskip("playwright")
    from scheduler import daily_scan

    orch = daily_scan.ScannerOrchestrator.__new__(daily_scan.ScannerOrchestrator)
    orch.email = AsyncMock()
    orch.email.send_tender247_unblock_request = AsyncMock(return_value=True)

    monkeypatch.setattr(
        daily_scan.repository, "was_audit_action_logged_recently", AsyncMock(return_value=True)
    )
    record_mock = AsyncMock()
    monkeypatch.setattr(daily_scan.repository, "record_audit_event", record_mock)

    await orch._maybe_notify_tender247_block(RuntimeError("Cloudflare 403"))
    orch.email.send_tender247_unblock_request.assert_not_awaited()
    record_mock.assert_not_awaited()

    monkeypatch.setattr(
        daily_scan.repository, "was_audit_action_logged_recently", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(daily_scan, "_detect_egress_ip", AsyncMock(return_value="52.76.118.147"))

    await orch._maybe_notify_tender247_block(RuntimeError("Cloudflare 403"))
    orch.email.send_tender247_unblock_request.assert_awaited_once()
    record_mock.assert_awaited_once()
