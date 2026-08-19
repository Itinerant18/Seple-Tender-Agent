import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("playwright")

GEM_DIRECT_PATH = Path(__file__).resolve().parents[2] / "connectors" / "gem_direct.py"
spec = importlib.util.spec_from_file_location("gem_direct_module", GEM_DIRECT_PATH)
gem_direct_module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(gem_direct_module)
_to_raw_tender = gem_direct_module._to_raw_tender

# Verbatim innerText of a bidplus.gem.gov.in listing card (captured 11-08-2026).
CARD_TEXT = (
    "Bid No.: GEM/2026/B/7637412 RA NO: GEM/2026/R/712874 "
    "View Corrigendum/Representation Items: Portable Fire Extinguishers (V4) "
    "Quantity: 5191 Department Name And Address: Land and Land Reforms Department West Bengal "
    "Start Date: 09-08-2026 3:00 PM End Date: 11-08-2026 5:47 PM"
)


def _card(**overrides) -> dict:
    card = {
        "bid": "GEM/2026/B/7637412",
        "url": "https://bidplus.gem.gov.in/showbidDocument/1234",
        "text": CARD_TEXT,
    }
    card.update(overrides)
    return card


def test_parses_every_labelled_field():
    tender = _to_raw_tender(_card())

    assert tender.tender_reference == "GEM/2026/B/7637412"
    assert tender.title == "Portable Fire Extinguishers (V4)"
    assert tender.issuing_authority == "Land and Land Reforms Department West Bengal"
    assert tender.deadline == "11-08-2026 5:47 PM"
    assert tender.publication_date == "09-08-2026 3:00 PM"
    assert tender.source == "GeM"


def test_description_carries_scope_beyond_the_title():
    # The classifier saw DESCRIPTION: None for every GeM row under the old
    # connector, so it judged fit on the title alone.
    description = _to_raw_tender(_card()).description

    assert "Portable Fire Extinguishers (V4)" in description
    assert "Quantity: 5191" in description


def test_card_without_a_bid_number_is_dropped():
    assert _to_raw_tender(_card(bid=None)) is None


def test_missing_dates_do_not_raise():
    tender = _to_raw_tender(_card(text="Bid No.: GEM/2026/B/1 Items: Fire pump Quantity: 2"))

    assert tender.deadline is None
    assert tender.title == "Fire pump"


_mirror_row_to_tender = gem_direct_module._mirror_row_to_tender

# Verbatim row from the CPPP GeM mirror (captured 12-08-2026).
MIRROR_ROW = [
    "3.", "29-Jun-2026 11:34 AM", "13-Aug-2026 12:00 PM",
    "GEM/2026/B/7646952/1",
    "HD IP High Capability day night surveillance camera,16 Channel NVR",
    "Prasar Bharati Broadcasting Corporation",
    "Ministry of Information and Broadcasting",
]


def test_mirror_row_parses_and_splits_quantity_off_the_bid_number():
    tender = _mirror_row_to_tender(MIRROR_ROW, "/cppp/tenderdetail/1")

    assert tender.tender_reference == "GEM/2026/B/7646952"  # trailing quantity dropped
    assert tender.deadline == "13-Aug-2026 12:00 PM"
    assert tender.publication_date == "29-Jun-2026 11:34 AM"
    assert "Prasar Bharati" in tender.issuing_authority
    assert tender.source == "GeM"


def test_mirror_row_without_a_matching_token_is_dropped():
    row = list(MIRROR_ROW)
    row[4], row[5], row[6] = "Tyres and batteries", "Some Org", "Some Dept"

    assert _mirror_row_to_tender(row, None) is None


def test_mirror_ignores_non_bid_rows():
    assert _mirror_row_to_tender(["header", "row"], None) is None


_mirror_page_url = gem_direct_module._mirror_page_url


def test_mirror_page_1_is_the_bare_url():
    assert _mirror_page_url(1) == gem_direct_module.MIRROR_URL


def test_mirror_pagination_encodes_the_page_url_in_base64():
    # A bare ?page=N is silently ignored and re-serves page 1, so the url=
    # token is the only thing that actually pages.
    import base64
    from urllib.parse import parse_qs, urlsplit

    token = parse_qs(urlsplit(_mirror_page_url(7)).query)["url"][0]
    assert base64.b64decode(token).decode() == f"{gem_direct_module.MIRROR_URL}?page=7"


def test_organisation_name_alone_is_not_a_match():
    # "Border Security Force" in the org column used to pull in its tyre and
    # battery bids.
    row = list(MIRROR_ROW)
    row[4], row[5], row[6] = "TYRE-1,BATTERY-2", "Border Security Force (BSF)", "CAPF"

    assert _mirror_row_to_tender(row, None) is None
