"""
Test: Can Firecrawl extract clean text from a tender page?
Run: python tests/test_firecrawl.py
"""
from dotenv import load_dotenv
load_dotenv()

from connectors.firecrawl_client import FirecrawlClient


def test_firecrawl():
    client = FirecrawlClient()

    # Public GeM bid search page (no login needed)
    test_url = "https://gem.gov.in/search/bid"

    print(f"Testing Firecrawl on: {test_url}")
    result = client.scrape_page(test_url)

    print("\n--- MARKDOWN PREVIEW (first 500 chars) ---")
    print(result["markdown"][:500] or "(empty — check FIRECRAWL_API_KEY)")

    print("\n--- LINKS FOUND ---")
    for link in result["links"][:10]:
        print(f"  {link}")


if __name__ == "__main__":
    test_firecrawl()
