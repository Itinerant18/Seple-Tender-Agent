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


# --- deadline extraction from fetched page text --------------------------------
#
# Web-discovered pages carry no deadline field, so the only deadline available is
# whatever the page states in prose. Every WebSearch row stored a NULL before this
# pattern existed.

from processor.extractor import FieldExtractor as _FE

_extract = _FE()


def _deadline(text):
    return _extract.extract_all(text).get("deadline")


def test_common_deadline_phrasings_are_extracted():
    cases = {
        "Bid Submission End Date : 25-08-2026 15:00": "25-08-2026 15:00",
        "Last Date & Time for Receipt of Bids : 01-Sep-2026 03:00 PM": "01-Sep-2026 03:00 PM",
        "Due Date: 25/08/2026": "25/08/2026",
        "Closing Date : 30-Aug-2026": "30-Aug-2026",
        "Tender End Date: 2026-09-15": "2026-09-15",
        "Bid Submission Closing Date - 05 Sep 2026": "05 Sep 2026",
    }
    for text, expected in cases.items():
        assert _deadline(text) == expected, text


def test_extracted_deadlines_round_trip_through_the_parser():
    parsed = _FE.parse_datetime(_deadline("Last Date of Submission : 02-09-2026"))

    assert (parsed.year, parsed.month, parsed.day) == (2026, 9, 2)


def test_other_dates_on_the_page_are_not_mistaken_for_the_deadline():
    # Storing a publication date or a pre-bid meeting as the deadline would be
    # worse than storing nothing: the board would show a date that closes early.
    assert _deadline("Published Date: 01-08-2026") is None
    assert _deadline("Pre-bid meeting 12-08-2026") is None


def test_page_with_no_deadline_yields_none():
    assert _deadline("62 Cctv Amc Tenders In India 2026 - browse listings") is None
    assert _deadline("") is None


def test_a_year_is_not_mistaken_for_a_month():
    # Stripping HTML collapses whitespace, so unrelated numbers end up adjacent.
    # "...End Date 06-2023 11..." on bhel.com parsed as a date when the month
    # slot accepted four digits. A wrong deadline is worse than none: the board
    # would show a tender closing before it really does.
    assert _deadline("Tender End Date 06-2023 11 Fire Alarm") is None


def test_month_names_and_numeric_months_both_still_work():
    assert _deadline("Closing Date: 09-12-2026") == "09-12-2026"
    assert _deadline("Closing Date: 09-December-2026") == "09-December-2026"
