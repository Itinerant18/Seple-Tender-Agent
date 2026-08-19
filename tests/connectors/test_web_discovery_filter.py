"""WebSearch result filtering.

Web search returns far more index pages than tender notices. Storing them anyway
grew this source to 1,670 rows with a NULL deadline on every one — 49% of the
database, none of it biddable. This is the cheap pre-filter that keeps us from
paying the scrape chain to fetch pages we already know are listings; the real
quality gate is in daily_scan, which drops a page that states no deadline.
"""
from connectors.web_discovery import _is_tender_page


def keeps(url, title=""):
    return _is_tender_page(url, title)


# --- aggregators and resellers -------------------------------------------------

def test_our_own_aggregators_are_redundant_here():
    # TenderTiger and Tender247 have dedicated connectors; their listing pages
    # arriving a second time via search added nothing but NULL deadlines.
    assert not keeps("https://www.tender247.com/keyword/cctv+systems+tenders",
                     "Cctv Systems Government Tenders")
    assert not keeps("https://www.tendertiger.com/TenderAI/TenderAIList?se=1",
                     "Latest 2026 Housekeeping Tenders In India")


def test_third_party_aggregator_hosts_are_dropped():
    for url in (
        "https://www.tenderdetail.com/Indian-tender/cctv-amc-tenders",
        "https://www.meghalayatenders.com/quicksearch.aspx?st=fire",
        "https://tenderkart.in/tenders/facility-management/gujarat",
        "https://www.tendersontime.com/india/telangana-tenders",
        "https://tenders.infralens.in/gem/security-manpower-services",
    ):
        assert not keeps(url, "Some Tenders Listing"), url


def test_government_hosts_keep_the_word_tender_legitimately():
    # The hostname rule must not fire on gov portals, or we would drop the only
    # sites this connector exists to cover.
    assert keeps("https://eprocure.gov.in/eprocure/app?notice=123",
                 "Supply and installation of fire hydrant system")
    assert keeps("https://tenders.karnataka.gov.in/notice/4412",
                 "AMC of CCTV surveillance system")


# --- listing / index shapes ----------------------------------------------------

def test_counted_listing_titles_are_dropped():
    assert not keeps("https://example.gov.in/x", "62 Cctv Amc Tenders In India 2026")


def test_latest_and_live_listing_titles_are_dropped():
    assert not keeps("https://example.gov.in/x", "Latest 2026 Cctv Maintenance Tenders In India")
    assert not keeps("https://example.gov.in/x", "Live Cooling Towers online Tenders in India")


def test_search_and_site_name_listing_titles_are_dropped():
    assert not keeps("https://example.gov.in/x", "Search Tenders For Rittal In India")
    assert not keeps("https://www.investindia.gov.in/request-for-proposal",
                     "Tenders - Invest India")


def test_rfp_roundup_titles_are_dropped():
    assert not keeps("https://example.gov.in/x", "Telangana Facility Management Tenders & RFPs 2026")


# --- already decided -----------------------------------------------------------

def test_awarded_and_contract_pages_are_dropped():
    # An awarded contract is not an opportunity.
    assert not keeps("https://bnpdewas.spmcil.com/en/awarded-tender/amc-cmc-fire",
                     "AMC / CMC of Fire Detection, Fire Alarm")
    assert not keeps("https://fulfilment.gem.gov.in/contract/slafds?fileDoc=1",
                     "Package: AMC of Security cum Fire Alarm System")


# --- genuine notices survive ---------------------------------------------------

def test_individual_notices_are_kept():
    assert keeps("https://www.aiimsraipur.edu.in/upload/civilquotation/tender.pdf",
                 "ALL INDIA INSTITUTE OF MEDICAL SCIENCES, RAIPUR")
    assert keeps("https://excise.cg.nic.in/csmcl/FileCS.ashx?Id=8213",
                 "Tender Document - Excise Department Chhattisgarh")


# --- degenerate input ----------------------------------------------------------

def test_missing_or_unparseable_url_is_rejected_not_raised():
    assert not keeps("", "Some tender")
    assert not keeps(None, "Some tender")
    assert not keeps("not-a-url", "Some tender")
