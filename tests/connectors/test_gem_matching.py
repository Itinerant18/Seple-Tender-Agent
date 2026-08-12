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
