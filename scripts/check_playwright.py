"""
Test: Can Playwright reach Tender Tiger's login page, and what are the real form selectors?
Run: python scripts/check_playwright.py
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

HEADLESS = os.getenv("TEST_HEADLESS", "1") == "1"  # set TEST_HEADLESS=0 to watch


async def test_tender_tiger_login():
    from playwright.async_api import async_playwright

    print("Starting Playwright test...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        print("Navigating to Tender Tiger login...")
        await page.goto("https://www.tendertiger.com/Login.aspx", timeout=60000)
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            print("(networkidle timeout — page may still be loading trackers, continuing)")

        await page.screenshot(path="tests/screenshots/tt_login_page.png")
        print("Screenshot saved: tests/screenshots/tt_login_page.png")
        print(f"Final URL: {page.url}")

        inputs = await page.query_selector_all("input")
        print("\n--- INPUT FIELDS FOUND ON LOGIN PAGE ---")
        for inp in inputs:
            name = await inp.get_attribute("name")
            id_ = await inp.get_attribute("id")
            type_ = await inp.get_attribute("type")
            print(f"  name={name}  id={id_}  type={type_}")

        print("\n--- FORM ACTIONS FOUND ---")
        for form in await page.query_selector_all("form"):
            print(f"  action={await form.get_attribute('action')}")

        await browser.close()
        print("\nTest complete. Check screenshots folder.")


if __name__ == "__main__":
    os.makedirs("tests/screenshots", exist_ok=True)
    asyncio.run(test_tender_tiger_login())
