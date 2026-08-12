from datetime import date, datetime
import importlib.util
from pathlib import Path

EXTRACTOR_PATH = Path(__file__).resolve().parents[2] / "processor" / "extractor.py"
spec = importlib.util.spec_from_file_location("extractor_module", EXTRACTOR_PATH)
extractor_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extractor_module)
FieldExtractor = extractor_module.FieldExtractor


def test_parse_datetime_iso_z_returns_naive_datetime():
    parsed = FieldExtractor.parse_datetime("2026-08-11T10:30:00Z")

    assert parsed == datetime(2026, 8, 11, 10, 30)
    assert parsed.tzinfo is None


def test_parse_datetime_indian_portal_formats():
    assert FieldExtractor.parse_datetime("11-08-2026 05:45:00") == datetime(2026, 8, 11, 5, 45)
    assert FieldExtractor.parse_datetime("11-08-2026 05:45 PM") == datetime(2026, 8, 11, 17, 45)
    assert FieldExtractor.parse_datetime("11/Aug/2026") == datetime(2026, 8, 11)
    assert FieldExtractor.parse_datetime("11-Aug-2026 05:45 PM") == datetime(2026, 8, 11, 17, 45)
    assert FieldExtractor.parse_datetime("11 Aug 2026") == datetime(2026, 8, 11)


def test_parse_datetime_handles_labelled_portal_text():
    assert FieldExtractor.parse_datetime("Due Date : 11-08-2026") == datetime(2026, 8, 11)


def test_parse_datetime_rejects_text_without_a_year():
    # dateutil would read these as today's date — the year guard blocks that.
    assert FieldExtractor.parse_datetime("11") is None
    assert FieldExtractor.parse_datetime("Not specified") is None
    assert FieldExtractor.parse_datetime("—") is None


def test_parse_date_uses_datetime_parser():
    assert FieldExtractor.parse_date("11/08/2026") == date(2026, 8, 11)
    assert FieldExtractor.parse_date("not a date") is None
