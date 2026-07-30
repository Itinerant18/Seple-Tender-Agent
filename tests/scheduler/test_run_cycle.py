from datetime import datetime
from uuid import uuid4

import pytest

from scheduler import run as scheduler_run


class _FakeEmail:
    def __init__(self, *, send_result: bool = True):
        self.send_result = send_result
        self.sent_tenders = []

    async def send_digest(self, tenders):
        self.sent_tenders = tenders
        return self.send_result


class _FakeOrchestrator:
    def __init__(self, *, send_result: bool = True):
        self.email = _FakeEmail(send_result=send_result)
        self.scan_calls = 0

    async def run_daily_scan(self):
        self.scan_calls += 1
        return []


class _FakeTracker:
    def __init__(self):
        self.check_calls = 0

    async def run_checks(self):
        self.check_calls += 1


@pytest.mark.asyncio
async def test_working_day_sends_and_marks_the_durable_digest_queue(monkeypatch):
    notification_id = uuid4()
    tender_id = uuid4()
    orchestrator = _FakeOrchestrator()
    tracker = _FakeTracker()
    marked_ids = []

    monkeypatch.setattr(scheduler_run, "ScannerOrchestrator", lambda: orchestrator)
    monkeypatch.setattr(scheduler_run, "MilestoneTracker", lambda: tracker)

    async def list_pending():
        return [
            {
                "digest_notification_id": notification_id,
                "id": tender_id,
                "title": "Railway signalling tender",
                "fit_classification": "strong_fit",
            }
        ]

    async def mark_sent(notification_ids):
        marked_ids.extend(notification_ids)

    monkeypatch.setattr(
        scheduler_run.repository,
        "list_pending_digest_tenders",
        list_pending,
    )
    monkeypatch.setattr(
        scheduler_run.repository,
        "mark_digest_notifications_sent",
        mark_sent,
    )

    result = await scheduler_run.run_cycle(now=datetime(2026, 7, 27, 6, 0))

    assert result == {"scan_succeeded": True, "digest_count": 1}
    assert orchestrator.scan_calls == 1
    assert tracker.check_calls == 1
    assert [tender.id for tender in orchestrator.email.sent_tenders] == [tender_id]
    assert marked_ids == [notification_id]


@pytest.mark.asyncio
async def test_non_working_day_leaves_digest_queue_for_next_cycle(monkeypatch):
    orchestrator = _FakeOrchestrator()
    tracker = _FakeTracker()
    list_calls = 0

    monkeypatch.setattr(scheduler_run, "ScannerOrchestrator", lambda: orchestrator)
    monkeypatch.setattr(scheduler_run, "MilestoneTracker", lambda: tracker)

    async def list_pending():
        nonlocal list_calls
        list_calls += 1
        return []

    monkeypatch.setattr(
        scheduler_run.repository,
        "list_pending_digest_tenders",
        list_pending,
    )

    result = await scheduler_run.run_cycle(now=datetime(2026, 8, 2, 6, 0))

    assert result == {"scan_succeeded": True, "digest_count": 0}
    assert list_calls == 0
    assert orchestrator.email.sent_tenders == []
    assert tracker.check_calls == 1


@pytest.mark.asyncio
async def test_failed_delivery_keeps_notifications_pending(monkeypatch):
    notification_id = uuid4()
    orchestrator = _FakeOrchestrator(send_result=False)
    tracker = _FakeTracker()
    mark_calls = 0

    monkeypatch.setattr(scheduler_run, "ScannerOrchestrator", lambda: orchestrator)
    monkeypatch.setattr(scheduler_run, "MilestoneTracker", lambda: tracker)

    async def list_pending():
        return [
            {
                "digest_notification_id": notification_id,
                "id": uuid4(),
                "title": "Airport security tender",
                "fit_classification": "potential_fit",
            }
        ]

    async def mark_sent(_notification_ids):
        nonlocal mark_calls
        mark_calls += 1

    monkeypatch.setattr(
        scheduler_run.repository,
        "list_pending_digest_tenders",
        list_pending,
    )
    monkeypatch.setattr(
        scheduler_run.repository,
        "mark_digest_notifications_sent",
        mark_sent,
    )

    result = await scheduler_run.run_cycle(now=datetime(2026, 7, 27, 6, 0))

    assert result == {"scan_succeeded": True, "digest_count": 0}
    assert mark_calls == 0
    assert len(orchestrator.email.sent_tenders) == 1
