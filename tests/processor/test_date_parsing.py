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

# Reuse the module already loaded by path above: importing `processor.extractor`
# runs processor/__init__.py, which pulls pdfplumber and is not installed in CI.
_FE = FieldExtractor
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


# --- multi-tender listing pages yield nothing ----------------------------------
# Attributing a portal table's closing dates to the row being processed borrows
# a deadline that is not this tender's — how mptenders.gov.in rows presented
# expired notices as live with a date belonging to some other row of the table.

_MP_HOME_TABLE = (
    "Tender Title Reference No Closing Date Bid Opening Date "
    "1. MP37WB02(BW)/Sheopur NIT-1301-Wb-Bw 06-Oct-2026 05:00 PM "
    "2. Work contract for Operation and Maintenance of Seepage water pumps "
    "WT-3143/MM-I 19-Oct-2026 03:30 PM "
    "3. Work contract for checking, calibration WT-3154/ETnI-II "
    "21-Oct-2026 03:30 PM "
    "4. Annual Repairing Hand Pumps Block Jaora NIT 12/26-27 PHE RTM HP "
    "05-Oct-2026 05:30 PM"
)


def test_a_portal_table_of_bare_dates_is_not_the_deadline():
    # The mptenders.gov.in home page shape: ONE "Closing Date" column header
    # and a bare date per row. No label sits near any single date, so none of
    # them may be captured as "the" deadline of the row being processed.
    assert _deadline(_MP_HOME_TABLE) is None


def test_a_snippet_list_with_a_label_per_entry_is_refused():
    # The shape the guard exists for: search fragments / list pages where each
    # entry carries its own "Closing Date" label. search() takes the first
    # hit, which would borrow a deadline belonging to a different tender.
    snippet_list = (
        "NIT for water supply NIT-1301 Closing Date : 06-Oct-2026 05:00 PM. "
        "Seepage pump O&M contract WT-3143 Closing Date : 19-Oct-2026 03:30 PM. "
        "Calibration work WT-3154 Closing Date : 21-Oct-2026 03:30 PM."
    )
    assert _deadline(snippet_list) is None


def test_listing_guard_threshold_is_three_labels():
    two = ("Tender A Closing Date : 01-Oct-2026. "
           "Tender B Closing Date : 02-Oct-2026.")
    three = two + " Tender C Closing Date : 03-Oct-2026."

    # two labels: still treated as a notice (a corrigendum may restate its
    # deadline alongside the original notice's)
    assert _deadline(two) == "01-Oct-2026"
    assert _deadline(three) is None


def test_a_single_notice_stating_its_deadline_once_is_unaffected():
    assert _deadline(
        "Supply of fire detection system. Closing Date : 30-Aug-2026 15:00"
    ) == "30-Aug-2026 15:00"


def test_listing_guard_refuses_the_whole_page():
    # extract_all() refuses a listing outright, not just the deadline — a
    # listing's value column would mis-attribute the same way its dates do.
    labelled = (
        "Tender A Closing Date : 01-Oct-2026. Estimated Cost Rs 10,00,000. "
        "Tender B Closing Date : 02-Oct-2026. Estimated Cost Rs 12,00,000. "
        "Tender C Closing Date : 03-Oct-2026. Estimated Cost Rs 14,00,000."
    )
    assert _extract.extract_all(labelled) == {}


def test_a_year_is_not_mistaken_for_a_month():
    # Stripping HTML collapses whitespace, so unrelated numbers end up adjacent.
    # "...End Date 06-2023 11..." on bhel.com parsed as a date when the month
    # slot accepted four digits. A wrong deadline is worse than none: the board
    # would show a tender closing before it really does.
    assert _deadline("Tender End Date 06-2023 11 Fire Alarm") is None


def test_month_names_and_numeric_months_both_still_work():
    assert _deadline("Closing Date: 09-12-2026") == "09-12-2026"
    assert _deadline("Closing Date: 09-December-2026") == "09-December-2026"


# --- label quality: sale/clarification cutoffs are not bid deadlines ---------
# Portals print the tender-document SALE cutoff above the bid deadline, and
# search() takes the first hit. The sale cutoff is never later than the real
# bid close, so storing it makes the board hide a tender that is still live —
# strictly worse than storing nothing.

def test_sale_clarification_and_publication_cutoffs_are_never_stored():
    assert _deadline("CLOSING DATE OF SALE FROM 29-02-2024 12:01:09 PM") is None
    assert _deadline("Closing Date of Clarification: 10-08-2026") is None
    assert _deadline("Closing Date of Publication: 01-08-2026") is None
    assert _deadline("Closing Date for Sale of Tender: 01-08-2026") is None


def test_bid_deadline_wins_when_the_sale_cutoff_is_printed_above_it():
    # The real BHEL notice layout — sale cutoff first, submission deadline
    # second, opening date last. Only the submission cutoff is the deadline.
    page = (
        "PUBLISH DATE 29-01-2024 "
        "CLOSING DATE OF SALE FROM 29-02-2024 12:01:09 PM "
        "CLOSING DATE OF SUBMISSION FORM 29-02-2024 06:00:09 PM "
        "TENDER OPENING DATE 01-03-2024 01:30:09 PM"
    )
    captured = _deadline(page)

    assert captured == "29-02-2024 06:00"
    parsed = _FE.parse_datetime(captured)
    assert (parsed.year, parsed.month, parsed.day) == (2024, 2, 29)
    assert parsed.hour == 6


def test_a_plain_closing_date_is_still_used_when_no_bid_wording_exists():
    # The blocklist must not swallow the ordinary label most portals use.
    assert _deadline("Closing Date : 30-Aug-2026") == "30-Aug-2026"
    assert _deadline("Closing Date of Submission : 30-Aug-2026") == "30-Aug-2026"


# --- dot-delimited, ordinal and prose deadline forms --------------------------
# Indian notices routinely word deadlines as "15.03.2024", "15th March 2024"
# or prose ("last date of submission is 15-03-2024"); the pattern missed all
# three, which is part of how a 2024-closed notice kept a NULL deadline.

def test_dot_delimited_indian_dates_are_extracted():
    assert _deadline("Last date of submission: 15.03.2024") == "15.03.2024"
    assert _deadline("Closing Date : 15.03.26") == "15.03.26"


def test_dot_delimited_dates_round_trip_through_the_parser():
    parsed = _FE.parse_datetime(_deadline("Bid Submission End: 15.03.2024"))
    assert (parsed.year, parsed.month, parsed.day) == (2024, 3, 15)
    # two-digit year: rejected by the 4-digit-year guard unless handled
    assert _FE.parse_datetime("15.03.26") == datetime(2026, 3, 15)
    assert _FE.parse_datetime("15.03.26 14:30") == datetime(2026, 3, 15, 14, 30)


def test_ordinal_dates_are_extracted_and_parsed():
    assert _deadline("Last date of submission: 15th March 2024") == "15th March 2024"
    assert _deadline("Bids close on 1st April 2026") == "1st April 2026"
    parsed = _FE.parse_datetime(_deadline("Submission Deadline: 15th March 2024"))
    assert (parsed.year, parsed.month, parsed.day) == (2024, 3, 15)


def test_prose_deadline_phrases_capture_the_whole_date():
    # Greedy bridge backtracking once captured "5-03-2024" here — right shape,
    # wrong day. The full date must survive.
    captured = _deadline("Last date of submission is 15-03-2024")
    assert captured == "15-03-2024"
    parsed = _FE.parse_datetime(captured)
    assert (parsed.year, parsed.month, parsed.day) == (2024, 3, 15)
    assert _deadline("Bids close on 25-08-2026") == "25-08-2026"


def test_dot_date_guards_still_hold():
    # The same false-positive class the slash forms guard against: a
    # month.year run must never become a deadline, nor a published date.
    assert _deadline("Tender End Date 06.2023 11 Fire Alarm") is None
    assert _deadline("Published Date: 01.08.2026") is None


# --- URL-embedded proxy publication dates -------------------------------------
# Government portals stamp archive timestamps into document paths; without
# one, an old upload that states no dates looks fresh forever.

def test_parse_url_date_extracts_embedded_archive_timestamps():
    assert FieldExtractor.parse_url_date(
        "https://eprocure.gov.in/doc/230220241747/notice.pdf"
    ) == datetime(2024, 2, 23, 17, 47)
    assert FieldExtractor.parse_url_date(
        "https://gov.in/files/20240223/tender.pdf"
    ) == datetime(2024, 2, 23)
    assert FieldExtractor.parse_url_date(
        "https://gov.in/tender_15032024.pdf"
    ) == datetime(2024, 3, 15)


def test_parse_url_date_rejects_non_dates_and_implausible_ones():
    assert FieldExtractor.parse_url_date("https://gov.in/notice?id=8412") is None
    assert FieldExtractor.parse_url_date("https://gov.in/2026/tender.pdf") is None
    assert FieldExtractor.parse_url_date("https://gov.in/20261399/x.pdf") is None
    assert FieldExtractor.parse_url_date("https://gov.in/99999999/x.pdf") is None
    assert FieldExtractor.parse_url_date(None) is None
    assert FieldExtractor.parse_url_date("") is None
