"""WebSearch result filtering.

Web search returns far more index pages than tender notices. Storing them anyway
grew this source to 1,670 rows with a NULL deadline on every one — 49% of the
database, none of it biddable. This is the cheap pre-filter that keeps us from
paying the scrape chain to fetch pages we already know are listings; the real
quality gate is in daily_scan, which drops a page that states no deadline.
"""
import importlib.util
from pathlib import Path

# Load the module directly: importing `connectors.web_discovery` runs
# connectors/__init__.py, which imports every connector and needs playwright.
WEB_DISCOVERY_PATH = Path(__file__).resolve().parents[2] / "connectors" / "web_discovery.py"
spec = importlib.util.spec_from_file_location("web_discovery_module", WEB_DISCOVERY_PATH)
web_discovery_module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(web_discovery_module)
_is_tender_page = web_discovery_module._is_tender_page


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


# --- archival year filtering -----------------------------------------------------
# Government sites keep tender PDFs forever under year-bearing paths and search
# engines surface them years later — this is where pre-2026 notices came from.

def test_prior_year_paths_are_dropped():
    assert not keeps("https://sbi.co.in/webfiles/tenders/files_2024/cash-van.pdf",
                     "Notice for supply of cash vans")
    assert not keeps("https://dept.gov.in/archive/2023/fire-alarm/tender.pdf",
                     "Fire alarm system tender")
    assert not keeps("https://gem.gov.in/docs/tenders2023.pdf",
                     "CCTV AMC tender")


def test_current_year_paths_are_kept():
    year = web_discovery_module._current_procurement_year()
    assert keeps(f"https://dept.gov.in/tenders/{year}/fire-alarm.pdf",
                 "Fire alarm system tender")


def test_title_can_veto_an_archival_path_when_it_claims_the_live_year():
    # An archival path under a title that asserts the current procurement year
    # is ambiguous — leave it for the deadline gate rather than drop it.
    year = web_discovery_module._current_procurement_year()
    assert keeps("https://sbi.co.in/files_2024/cash-van.pdf",
                 f"Cash van tender {year}")


def test_title_years_alone_never_drop():
    # Titles quote old years for all sorts of reasons (rate contracts,
    # references); only a year-bearing path triggers the drop.
    assert keeps("https://dept.gov.in/notice/8812",
                 "AMC as per 2023 rate contract")


def test_fiscal_year_boundary(monkeypatch):
    # Before ~April the previous calendar year is still the live procurement
    # year (April–March cycle); freezing January must not drop FY pages.
    from datetime import datetime as real_datetime

    class FrozenDatetime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 1, 15)

    monkeypatch.setattr(web_discovery_module, "datetime", FrozenDatetime)

    assert web_discovery_module._current_procurement_year() == 2025
    assert keeps("https://dept.gov.in/tenders/2025/fire.pdf", "Fire alarm tender")
    assert not keeps("https://dept.gov.in/tenders/2024/fire.pdf", "Fire alarm tender")


def test_bare_slafds_urls_are_dropped():
    # The /contract/ marker already caught the known GeM shape; a bare SLA
    # document URL (no /contract/ segment) was still reaching the scrape chain.
    assert not keeps("https://fulfilment.gem.gov.in/slafds?fileDoc=1",
                     "Security package")


# --- NIC eProcurement portals (mptenders.gov.in et al) --------------------------
# This portal defeats every other filter: a .gov.in host (exempt from the
# aggregator rule), no year-bearing path (so the archival filter never fires),
# and a static title matching no listing pattern — while its data pages are
# table listings, its per-tender view renders shell content behind an opaque
# session handle, and its archive listing is captcha-gated. Storing any of it
# produced deadline-less or borrowed-deadline rows: expired MP tenders reading
# as live notices on the board.

def test_mptenders_nicgep_pages_are_dropped():
    for url, title in (
        # the archive listing, indexed by search engines under a title that
        # reads like a live category ("Tenders Archived")
        ("https://mptenders.gov.in/nicgep/app?page=FrontEndTendersInArchive&service=page",
         "Tenders Archived"),
        # a per-tender view with an opaque session handle
        ("https://mptenders.gov.in/nicgep/app?component=%24DirectLink"
         "&page=FrontEndViewTender&service=direct&sp=SiQ426ObMXsMs%2B9439BXlyw%3D%3D",
         "eProcurement System Government of Madhya Pradesh"),
        # the active-tenders listing
        ("https://mptenders.gov.in/nicgep/app?component=%24DirectLink"
         "&page=FrontEndLatestActiveTenders&service=direct&sp=SdBqIC%2FX9oilteXktKIfA8g%3D%3D",
         "eProcurement System Government of Madhya Pradesh"),
        # the app root
        ("https://mptenders.gov.in/nicgep/app",
         "eProcurement System Government of Madhya Pradesh"),
    ):
        assert not keeps(url, title), url


def test_nicgep_app_is_dropped_on_any_host():
    # the app path is the fingerprint, not just the MP domain
    assert not keeps(
        "https://someothertender.gov.in/nicgep/app?page=FrontEndTendersInArchive&service=page",
        "Tenders Archived",
    )


def test_tapestry_page_markers_catch_proxy_hosts_without_the_nicgep_marker():
    assert not keeps(
        "https://tenders.example.gov.in/app?page=FrontEndViewTender&service=direct&sp=X",
        "Tender Details",
    )


def test_archive_title_on_a_gov_host_is_dropped():
    assert not keeps("https://mptenders.gov.in/some/index", "Tenders in Archive")


def test_the_nicgep_rule_does_not_swallow_ordinary_gov_notices():
    assert keeps("https://mp.gov.in/tenders/notice/8812", "Supply of fire alarm system")
    assert keeps("https://dept.nic.in/files/notice.pdf", "AMC of CCTV surveillance system")


# --- what actually leaked onto the board (2026-09-29 audit) ---------------------
# 105 undated live rows, every one from WebSearch: 52 were eprocure/etenders
# per-organisation listings under counted titles, the rest archive/index pages,
# EOI boards and social posts. None had a deadline of its own to expire on.

def test_eprocure_organisation_listings_are_dropped_on_non_nicgep_hosts():
    for url, title in (
        ("https://eprocure.gov.in/eprocure/app?component=%24DirectLink"
         "&page=FrontEndTendersByOrganisation&service=direct&sp=SoF6",
         "68 - eProcurement System Government of India"),
        ("https://etenders.gov.in/eprocure/app?component=%24DirectLink"
         "&page=FrontEndTendersByOrganisation&service=direct",
         "156 - Government eProcurement System"),
        ("https://eproc.punjab.gov.in/nicgep/app?page=FrontEndTendersByLocation&service=direct",
         "47 - eProcurement System Government of Punjab"),
    ):
        assert not keeps(url, title), url


def test_counted_portal_titles_are_dropped_even_without_the_word_tender():
    assert not keeps("https://eprocure.gov.in/eprocure/app?x=1", "98 - eProcurement System Government of India")
    assert not keeps("https://eprocurentpc.nic.in/x", "553 - NTPC Limited eProcurement Portal")


def test_archive_open_and_alert_index_titles_are_dropped():
    for url, title in (
        ("https://spmnarmadapuram.spmcil.com/en/tenders-archived/", "Tenders Archived"),
        ("https://vmmc-sjh.mohfw.gov.in/archive-tenders",
         "Archive Tenders | Official Website of VMMC & Safdarjung Hospital"),
        ("https://bcplonline.co.in/tender/index",
         "Open Tenders - Brahmaputra Cracker and Polymer Limited"),
        ("https://vmmc-sjh.mohfw.gov.in/tenders", "Tenders / Procurement | Safdarjung"),
        ("https://www.nhpcindia.com/welcome/tender?classification=2", "Tender Title - NHPC"),
        ("https://gil.gujarat.gov.in/tenders", "Manpower Tender Alerts Are Live! Government Departments"),
    ):
        assert not keeps(url, title), url


def test_social_posts_are_dropped():
    assert not keeps("https://www.instagram.com/p/DZjktqwk29M/",
                     "GeMBidNotification NIC invites bids via #GeM for AMC of CCTV")
    assert not keeps("https://www.linkedin.com/posts/someone_tender-activity-1",
                     "Supply of fire alarm system tender")


def test_single_notices_on_the_same_hosts_survive():
    assert keeps("https://www.nhpcindia.com/welcome/tender_detail/7841.html",
                 "NIT No.:2025_NHPC_849236_1 - NHPC")
    assert keeps("https://newmangaloreport.gov.in/procurement-vehicle-rfid-cards-nmpa",
                 "Procurement of Vehicle RFID Cards for NMPA.")
    assert keeps("https://www.mcgm.gov.in/irj/go/km/docs/documents/Tenders-New/ETH/ETH_8000114697_010926.pdf",
                 "GEM/2026/B/7914536")
    assert keeps("https://eprocure.gov.in/eprocure/app?notice=123",
                 "Supply and installation of fire hydrant system")
