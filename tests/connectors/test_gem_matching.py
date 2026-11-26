import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

GEM_DIRECT_PATH = Path(__file__).resolve().parents[2] / "connectors" / "gem_direct.py"
spec = importlib.util.spec_from_file_location("gem_direct_module", GEM_DIRECT_PATH)
gem_direct_module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(gem_direct_module)

_to_raw_tender = gem_direct_module._to_raw_tender
_doc_to_raw_tender = gem_direct_module._doc_to_raw_tender
_bid_doc_url = gem_direct_module._bid_doc_url
_extract_csrf = gem_direct_module._extract_csrf
GeMConnector = gem_direct_module.GeMConnector

# Verbatim innerText of a bidplus.gem.gov.in listing card (Playwright fallback).
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


def _solr_doc(**overrides) -> dict:
    doc = {
        "id": "10156366",
        "b_id": [10156366],
        "b_bid_number": ["GEM/2026/B/8265817"],
        "b_bid_type": [1],
        "b_eval_type": [0],
        "b_status": [1],
        "b_is_inactive": [0],
        "b_category_name": ["Items1,Items2,Items3,Item"],
        "bd_category_name": ["Items1,Items2,Items3,Camera for CCTV System (V3)"],
        "bbt_title": ["PROVISION OF CCTV"],
        "b_total_quantity": [15057],
        "ba_official_details_minName": ["Ministry of Defence"],
        "ba_official_details_deptName": ["Department of Military Affairs"],
        "final_start_date_sort": ["2026-11-12T11:00:26Z"],
        "final_end_date_sort": ["2026-11-26T11:00:00Z"],
    }
    doc.update(overrides)
    return doc


def test_parses_every_labelled_field():
    tender = _to_raw_tender(_card())

    assert tender.tender_reference == "GEM/2026/B/7637412"
    assert tender.title == "Portable Fire Extinguishers (V4)"
    assert tender.issuing_authority == "Land and Land Reforms Department West Bengal"
    assert tender.deadline == "11-08-2026 5:47 PM"
    assert tender.publication_date == "09-08-2026 3:00 PM"
    assert tender.source == "GeM"


def test_description_carries_scope_beyond_the_title():
    description = _to_raw_tender(_card()).description

    assert "Portable Fire Extinguishers (V4)" in description
    assert "Quantity: 5191" in description


def test_card_without_a_bid_number_is_dropped():
    assert _to_raw_tender(_card(bid=None)) is None


def test_missing_dates_do_not_raise():
    tender = _to_raw_tender(_card(text="Bid No.: GEM/2026/B/1 Items: Fire pump Quantity: 2"))

    assert tender.deadline is None
    assert tender.title == "Fire pump"


def test_solr_doc_maps_all_fields_and_prefers_untruncated_category():
    tender = _doc_to_raw_tender(_solr_doc(), search_term="cctv")

    assert tender is not None
    assert tender.tender_reference == "GEM/2026/B/8265817"
    assert tender.title == "PROVISION OF CCTV"
    assert tender.category == "Items1,Items2,Items3,Camera for CCTV System (V3)"
    assert "Camera for CCTV System (V3)" in tender.description
    assert "Ministry of Defence — Department of Military Affairs" in tender.issuing_authority
    assert "Quantity: 15057" in tender.description
    assert tender.publication_date == "2026-11-12T11:00:26Z"
    assert tender.deadline == "2026-11-26T11:00:00Z"
    assert tender.url == "https://bidplus.gem.gov.in/showbidDocument/10156366"
    assert tender.source == "GeM"
    assert tender.search_term == "cctv"


def test_solr_doc_strips_items_placeholders_when_bbt_title_is_absent():
    doc = _solr_doc(
        bbt_title=None,
        bd_category_name=["Items1,Items2,Camera for CCTV System (V3),NVR 16 Ch"],
    )
    tender = _doc_to_raw_tender(doc)

    assert tender is not None
    assert tender.title == "Camera for CCTV System (V3),NVR 16 Ch"


def test_solr_doc_skips_cancelled_and_inactive_bids():
    assert _doc_to_raw_tender(_solr_doc(b_status=[3])) is None
    assert _doc_to_raw_tender(_solr_doc(b_status=[5])) is None
    assert _doc_to_raw_tender(_solr_doc(b_is_inactive=[1])) is None
    assert _doc_to_raw_tender(_solr_doc(b_bid_number=[])) is None


def test_bid_doc_url_matches_portal_bid_types():
    assert _bid_doc_url(_solr_doc(b_bid_type=[1])) == "https://bidplus.gem.gov.in/showbidDocument/10156366"
    assert _bid_doc_url(_solr_doc(b_bid_type=[5])) == "https://bidplus.gem.gov.in/showdirectradocumentPdf/10156366"
    assert _bid_doc_url(_solr_doc(b_bid_type=[2], b_eval_type=[0])) == "https://bidplus.gem.gov.in/showradocumentPdf/10156366"
    assert _bid_doc_url(_solr_doc(b_bid_type=[2], b_eval_type=[1])) == "https://bidplus.gem.gov.in/list-ra-schedules/10156366"


def test_extract_csrf_finds_js_assignment_or_cookie():
    html = "<script>data: {'payload': JSON.stringify(postdata), 'csrf_bd_gem_nk': '252f909c57f2830d492918f83272dde9'}</script>"
    assert _extract_csrf(html) == "252f909c57f2830d492918f83272dde9"
    assert _extract_csrf("<html></html>", {"csrf_gem_cookie": "abc123def4567890"}) == "abc123def4567890"
    assert _extract_csrf("<html></html>") is None


@pytest.mark.asyncio
async def test_scrape_tenders_falls_back_to_playwright_if_api_raises(monkeypatch):
    connector = GeMConnector()
    fallback_tender = _doc_to_raw_tender(_solr_doc())
    monkeypatch.setattr(connector, "_scrape_via_api", AsyncMock(side_effect=RuntimeError("WAF 403")))
    monkeypatch.setattr(connector, "_scrape_via_playwright", AsyncMock(return_value=[fallback_tender]))

    results = await connector.scrape_tenders(max_results=10)

    assert len(results) == 1
    assert results[0].tender_reference == "GEM/2026/B/8265817"
