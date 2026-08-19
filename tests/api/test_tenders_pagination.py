"""The tenders endpoint over-fetches one row to detect a next page.

Off-by-one here is silently wrong in both directions: leak the extra row and the
board shows 201 rows on a 200-row page, drop has_more and Next greys out with
2800 tenders still unseen.
"""
import asyncio

import pytest

# api.main imports scheduler.daily_scan, which imports every connector.
pytest.importorskip("playwright")

from api import main


def _call(monkeypatch, total_rows, limit, offset=0):
    """Fake a table of `total_rows` and ask the endpoint for one page of it."""
    seen = {}

    async def fake_list_tenders(**kwargs):
        seen.update(kwargs)
        start = kwargs["offset"]
        return [{"id": i} for i in range(start, min(total_rows, start + kwargs["limit"]))]

    monkeypatch.setattr(main.repository, "list_tenders", fake_list_tenders)
    result = asyncio.run(main.get_tenders(limit=limit, offset=offset))
    return result, seen


def test_full_page_with_more_rows_behind_it(monkeypatch):
    result, seen = _call(monkeypatch, total_rows=500, limit=200)

    assert seen["limit"] == 201, "must ask for one extra row to know a next page exists"
    assert result["count"] == 200, "the extra row must not reach the client"
    assert len(result["data"]) == 200
    assert result["has_more"] is True


def test_exactly_one_full_page_reports_no_more(monkeypatch):
    # The boundary: 200 rows and limit 200 asks for 201, gets 200, so Next is off.
    result, _ = _call(monkeypatch, total_rows=200, limit=200)

    assert result["count"] == 200
    assert result["has_more"] is False


def test_last_partial_page(monkeypatch):
    result, _ = _call(monkeypatch, total_rows=250, limit=200, offset=200)

    assert result["count"] == 50
    assert result["has_more"] is False
    assert result["offset"] == 200


def test_offset_past_the_end_is_empty_not_an_error(monkeypatch):
    result, _ = _call(monkeypatch, total_rows=10, limit=200, offset=400)

    assert result["data"] == []
    assert result["has_more"] is False
