"""
Test: Can Apify scrape GeM portal for CCTV tenders?
Run: python scripts/check_apify.py
"""
from dotenv import load_dotenv
load_dotenv()

from connectors.gem_direct import GeMConnector


def test_gem_scraper():
    connector = GeMConnector()

    print("Searching GeM for CCTV tenders...")
    results = connector.search_tenders(
        keywords=["CCTV", "surveillance", "fire alarm"],
        max_results=10
    )

    print(f"\nFound {len(results)} tenders from GeM")
    for i, tender in enumerate(results[:3]):
        print(f"\n--- Tender {i+1} ---")
        print(f"  Title: {tender.get('title', 'N/A')}")
        print(f"  Value: {tender.get('value', 'N/A')}")
        print(f"  Deadline: {tender.get('deadline', 'N/A')}")
        print(f"  URL: {tender.get('url', 'N/A')}")


if __name__ == "__main__":
    test_gem_scraper()
