import logging

import pytest

pytest.importorskip("playwright")

from scheduler.daily_scan import ScannerOrchestrator  # noqa: E402


def test_excluded_gem_is_logged(monkeypatch, caplog):
    monkeypatch.setenv("SCAN_SOURCES", "TenderTiger,Tender247,WebSearch")

    with caplog.at_level(logging.WARNING, logger="scheduler.daily_scan"):
        orchestrator = ScannerOrchestrator()

    assert "excludes GeM" in caplog.text
    assert orchestrator._enabled("GeM") is False
    assert orchestrator._enabled("TenderTiger") is True


def test_empty_scan_sources_scans_everything_without_warning(monkeypatch, caplog):
    monkeypatch.delenv("SCAN_SOURCES", raising=False)

    with caplog.at_level(logging.WARNING, logger="scheduler.daily_scan"):
        orchestrator = ScannerOrchestrator()

    assert not [r for r in caplog.records if r.name == "scheduler.daily_scan"]
    assert orchestrator._enabled("GeM") is True
